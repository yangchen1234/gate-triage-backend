"""Workspace-scoped API for the new rehearsal product.

All state-changing requests commit the event, projection and retry receipt in
one database transaction. A workspace capability is required even in the local
anonymous demo, preventing accidental access to another visitor's workspace.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import importlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, text, update
from sqlalchemy.orm.attributes import set_committed_value

from .db import AuditEvent, CoordinationRequest, CoordinationTask, Evidence, IdempotencyRecord, Job, Workspace, get_database, utcnow
from .schemas import CoordinationRequestCreate, CoordinationRequestUpdate, ExperimentCreate, ExportCreate, PlanCreate, PlanSelection, PlaybackChange, SimulationCreate, TaskEventCreate, WorkspaceCreate

router = APIRouter(prefix="/api/v1")
RULE_VERSION = "readiness-1.0"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable, "field_errors": []}, "meta": {"request_id": str(uuid.uuid4())}})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Check the request fields and try again.", "retryable": False, "field_errors": [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]}, "meta": {"request_id": str(uuid.uuid4())}})


def engine():
    return importlib.import_module("gate_triage.workbench.engine")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def serializable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def metadata(workspace: Workspace | None = None, *, revision: int | None = None) -> dict:
    return {"workspace_id": workspace.id if workspace else None, "mode": workspace.mode if workspace else None, "revision": revision if revision is not None else workspace.revision if workspace else 0, "as_of": utcnow().isoformat(), "rule_version": RULE_VERSION}


def envelope(data: Any, workspace: Workspace | None = None, *, revision: int | None = None) -> dict:
    return {"data": serializable(data), "meta": metadata(workspace, revision=revision)}


def respond(payload: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers={"ETag": f'"{payload.get("meta", {}).get("revision", 0)}"', "Cache-Control": "no-store"})


def authorized_workspace(session, workspace_id: str, token: str | None, *, lock: bool = False) -> Workspace:
    statement = select(Workspace).where(Workspace.id == workspace_id)
    if lock:
        statement = statement.with_for_update()
    workspace = session.scalar(statement)
    if workspace is None or token is None or not hmac.compare_digest(workspace.token_hash, token_digest(token)):
        raise ApiError(404, "WORKSPACE_NOT_FOUND", "This workspace is unavailable or its access token is missing.")
    return workspace


def check_revision(workspace: Workspace, if_match: str | None) -> None:
    if if_match is None:
        raise ApiError(428, "REVISION_REQUIRED", "Refresh the workspace and include its current version.")
    try:
        expected = int(if_match.removeprefix("W/").strip('"'))
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", "If-Match must contain the workspace revision.")
    if expected != workspace.revision:
        raise ApiError(412, "REVISION_CONFLICT", "The workspace changed. Refresh before submitting this action.", True)


def retry_receipt(session, scope: str, key: str | None, body: dict):
    if not key or len(key) > 200:
        raise ApiError(428, "IDEMPOTENCY_KEY_REQUIRED", "Include a unique Idempotency-Key and reuse it when retrying.")
    if session.bind.dialect.name == "postgresql":
        # Creation has no existing workspace row to lock. Serialize the retry
        # key in PostgreSQL too, so multiple API processes cannot both accept
        # the same first request before its unique receipt is committed.
        lock_id = int.from_bytes(hashlib.sha256(f"{scope}:{key}".encode()).digest()[:8], "big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
    receipt = session.scalar(select(IdempotencyRecord).where(IdempotencyRecord.scope == scope, IdempotencyRecord.key == key))
    if receipt:
        if receipt.body_hash != digest(body):
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "This retry key was already used for a different request.")
        return respond(receipt.response, receipt.status_code)
    return None


def save_receipt(session, scope: str, key: str, body: dict, payload: dict, status: int):
    session.add(IdempotencyRecord(id=str(uuid.uuid4()), scope=scope, key=key, body_hash=digest(body), response=payload, status_code=status))


def workspace_data(workspace: Workspace, *, token: str | None = None) -> dict:
    result = {"id": workspace.id, "workspace_id": workspace.id, "name": workspace.name, "mode": workspace.mode, "revision": workspace.revision, "created_at": workspace.created_at.isoformat(), "snapshot": engine().snapshot(copy.deepcopy(workspace.state)), "playback": workspace.playback or {"playing": False, "speed": 1, "tick_minutes": 1}}
    if token:
        result.update(token=token, workspace_token=token)
    return result


def audit(session, workspace: Workspace, action: str, payload: dict, actor: str = "workspace-owner") -> None:
    session.add(AuditEvent(id=str(uuid.uuid4()), workspace_id=workspace.id, revision=workspace.revision, action=action, actor=actor, payload=serializable(payload)))


def sync_projections(session, workspace: Workspace) -> None:
    """Queryable tasks plus append-only evidence; state JSON remains replayable."""
    snapshot = engine().snapshot(copy.deepcopy(workspace.state))
    tasks = snapshot.get("tasks", [])
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    existing_tasks = {row.source_id: row for row in session.scalars(select(CoordinationTask).where(CoordinationTask.workspace_id == workspace.id))}
    current_task_ids: set[str] = set()
    for task in tasks:
        source_id = str(task.get("id", task.get("task_id", "")))
        if not source_id:
            continue
        current_task_ids.add(source_id)
        row = existing_tasks.get(source_id)
        if row is None:
            row = CoordinationTask(id=str(uuid.uuid4()), workspace_id=workspace.id, source_id=source_id)
            session.add(row)
        row.status = str(task.get("status", "open"))
        row.owner_role = task.get("owner_role")
        row.revision = workspace.revision
        row.payload = serializable(task)
    for source_id, row in existing_tasks.items():
        if source_id not in current_task_ids:
            row.status = "superseded"
            row.revision = workspace.revision
            row.payload = {**row.payload, "status": "superseded", "historical": True}
    evidence = list(snapshot.get("evidence", []))
    for container in snapshot.get("containers", []):
        for item in container.get("evidence", []):
            if isinstance(item, dict):
                evidence.append({"subject_id": container.get("id"), **item})
    existing = set(session.scalars(select(Evidence.source_id).where(Evidence.workspace_id == workspace.id)))
    for item in evidence:
        if not isinstance(item, dict):
            continue
        # A source can reuse a field identifier for a newer observation. Keep
        # every distinct observation rather than overwriting or silently
        # dropping it merely because the descriptive field ID is unchanged.
        original_id = str(item.get("id", item.get("evidence_id", "observation")))
        source_id = f"{original_id[:130]}:{digest(item)[:20]}"
        if source_id in existing:
            continue
        session.add(Evidence(id=str(uuid.uuid4()), workspace_id=workspace.id, source_id=source_id, subject_id=item.get("subject_id", item.get("container_id")), payload=serializable(item)))
        existing.add(source_id)


def commit_state(session, workspace: Workspace, state: dict, action: str, payload: dict, actor: str = "workspace-owner"):
    previous_revision = workspace.revision
    state = serializable(state)
    updated_at = utcnow()
    changed = session.execute(update(Workspace).where(Workspace.id == workspace.id, Workspace.revision == previous_revision).values(state=state, revision=previous_revision + 1, updated_at=updated_at), execution_options={"synchronize_session": False})
    if changed.rowcount != 1:
        raise ApiError(412, "REVISION_CONFLICT", "The workspace changed. Refresh before submitting this action.", True)
    # The CAS already wrote these columns. Mark them committed in the identity
    # map instead of generating a second unguarded, full-JSON ORM UPDATE.
    set_committed_value(workspace, "state", state)
    set_committed_value(workspace, "revision", previous_revision + 1)
    set_committed_value(workspace, "updated_at", updated_at)
    sync_projections(session, workspace)
    audit(session, workspace, action, payload, actor)


def capabilities(workspace: Workspace | None = None) -> dict:
    from .connector import Terminal49Connector
    simulation = workspace is not None and workspace.mode == "SIMULATION"
    return {"simulation": simulation, "resource_scheduling": simulation, "experiments": simulation, "physical_execution": False, "live_sync": False, "terminal49_configured": Terminal49Connector().configured, "live_access_enabled": False, "replay": workspace is not None and workspace.mode == "REPLAY_T49", "scope": "Synthetic tracked cohort; no live operational control", "unavailable_fields": ["live_reefer_temperature", "independent_scale_weight", "actual_lane_capacity", "actual_crane_positions", "road_safety_clearance"], "access": {"role": "workspace_owner", "scope": "this_workspace", "authentication": "anonymous_workspace_capability"}}


@router.get("/scenarios")
def get_scenarios():
    return respond(envelope({"items": engine().scenario_catalog()}))


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    scenario = next((item for item in engine().scenario_catalog() if item["id"] == scenario_id), None)
    if not scenario:
        raise ApiError(404, "SCENARIO_NOT_FOUND", "This scenario is not registered.")
    return respond(envelope(scenario))


@router.post("/workspaces", status_code=201)
def create_workspace(body: WorkspaceCreate, idempotency_key: str | None = Header(None)):
    database = get_database()
    payload = body.model_dump()
    with database.write_lock, database.session() as session:
        replay = retry_receipt(session, "workspace-create", idempotency_key, payload)
        if replay:
            return replay
        if body.mode == "LIVE_T49":
            raise ApiError(503, "SOURCE_NOT_CONFIGURED", "Live Terminal49 access is not enabled. Create a synthetic replay or simulation workspace.")
        if body.scenario_id not in {item["id"] for item in engine().scenario_catalog()}:
            raise ApiError(422, "VALIDATION_ERROR", "Choose a registered scenario.")
        token = secrets.token_urlsafe(32)
        workspace = Workspace(id=str(uuid.uuid4()), name=body.name, mode=body.mode, revision=1, token_hash=token_digest(token), state=serializable(engine().create_state(body.scenario_id, body.seed, body.mode)), playback={"playing": False, "speed": 1, "tick_minutes": 1}, created_at=utcnow(), updated_at=utcnow())
        session.add(workspace)
        session.flush()
        sync_projections(session, workspace)
        audit(session, workspace, "workspace.created", {"scenario_id": body.scenario_id, "seed": body.seed, "mode": body.mode})
        result = envelope(workspace_data(workspace, token=token), workspace)
        save_receipt(session, "workspace-create", idempotency_key, payload, result, 201)
        return respond(result, 201)


@router.get("/workspaces/{workspace_id}")
@router.get("/workspaces/{workspace_id}/overview")
def get_workspace(workspace_id: str, x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        return respond(envelope(workspace_data(workspace), workspace))


@router.get("/workspaces/{workspace_id}/capabilities")
def get_capabilities(workspace_id: str, x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        return respond(envelope(capabilities(workspace), workspace))


def paginate(items: list[dict], cursor: str | None, limit: int) -> dict:
    try:
        start = int(cursor or "0")
        if start < 0:
            raise ValueError()
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", "The list cursor is invalid.")
    return {"items": items[start:start + limit], "next_cursor": str(start + limit) if start + limit < len(items) else None, "total": len(items)}


@router.get("/workspaces/{workspace_id}/containers")
def get_containers(workspace_id: str, search: str = "", pickup_state: str | None = None, issue_kind: str | None = None, terminal: str | None = None, cursor: str | None = None, limit: int = Query(50, ge=1, le=200), x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        items = engine().snapshot(workspace.state).get("containers", [])
        if search:
            items = [item for item in items if search.lower() in json.dumps(item).lower()]
        if pickup_state:
            items = [item for item in items if item.get("pickup_state", item.get("readiness")) == pickup_state]
        if issue_kind:
            items = [item for item in items if issue_kind in json.dumps(item.get("issues", []))]
        if terminal:
            items = [item for item in items if terminal.lower() in str(item.get("terminal", "")).lower()]
        return respond(envelope(paginate(items, cursor, limit), workspace))


@router.get("/workspaces/{workspace_id}/containers/{container_id}")
def get_container(workspace_id: str, container_id: str, x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        snapshot = engine().snapshot(workspace.state)
        container = next((item for item in snapshot.get("containers", []) if container_id in {str(item.get("id")), str(item.get("number")), str(item.get("container_number"))}), None)
        if not container:
            raise ApiError(404, "CONTAINER_NOT_FOUND", "This container is not in the workspace.")
        detail = dict(container)
        detail.setdefault("tasks", [task for task in snapshot.get("tasks", []) if task.get("container_id") == container.get("id")])
        return respond(envelope(detail, workspace))


@router.get("/workspaces/{workspace_id}/tasks")
def get_tasks(workspace_id: str, status: str | None = None, owner_role: str | None = None, cursor: str | None = None, limit: int = Query(50, ge=1, le=200), x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        statement = select(CoordinationTask).where(CoordinationTask.workspace_id == workspace_id)
        if status:
            statement = statement.where(CoordinationTask.status == status)
        if owner_role:
            statement = statement.where(CoordinationTask.owner_role == owner_role)
        tasks = [row.payload for row in session.scalars(statement.order_by(CoordinationTask.source_id))]
        return respond(envelope(paginate(tasks, cursor, limit), workspace))


def coordination_request_data(row: CoordinationRequest) -> dict:
    def timestamp(value):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.isoformat()
    return {"id": row.id, "workspace_id": row.workspace_id, "status": row.status, "owner_role": row.owner_role, "service_kind": row.service_kind, "title": row.title, "comment": row.comment, "container_ids": row.container_ids, "provenance": row.payload.get("provenance", {}), "status_history": row.payload.get("status_history", []), "revision": row.revision, "created_at": timestamp(row.created_at), "updated_at": timestamp(row.updated_at), "resolved_at": timestamp(row.resolved_at)}


def increment_request_revision(session, workspace: Workspace, action: str, payload: dict) -> None:
    """Record a coordination change without touching any provider/world fact."""
    previous_revision = workspace.revision
    updated_at = utcnow()
    changed = session.execute(update(Workspace).where(Workspace.id == workspace.id, Workspace.revision == previous_revision).values(revision=previous_revision + 1, updated_at=updated_at), execution_options={"synchronize_session": False})
    if changed.rowcount != 1:
        raise ApiError(412, "REVISION_CONFLICT", "The workspace changed. Refresh before submitting this request.", True)
    set_committed_value(workspace, "revision", previous_revision + 1)
    set_committed_value(workspace, "updated_at", updated_at)
    audit(session, workspace, action, payload)


@router.get("/workspaces/{workspace_id}/requests")
def get_coordination_requests(workspace_id: str, status: str | None = None, owner_role: str | None = None, cursor: str | None = None, limit: int = Query(50, ge=1, le=200), x_workspace_token: str | None = Header(None)):
    if status is not None and status not in {"open", "in_progress", "resolved"}:
        raise ApiError(422, "VALIDATION_ERROR", "Request status must be open, in_progress or resolved.")
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        statement = select(CoordinationRequest).where(CoordinationRequest.workspace_id == workspace_id)
        if status:
            statement = statement.where(CoordinationRequest.status == status)
        if owner_role:
            statement = statement.where(CoordinationRequest.owner_role == owner_role)
        rows = session.scalars(statement.order_by(CoordinationRequest.created_at.desc(), CoordinationRequest.id))
        return respond(envelope(paginate([coordination_request_data(row) for row in rows], cursor, limit), workspace))


@router.post("/workspaces/{workspace_id}/requests", status_code=201)
def create_coordination_request(workspace_id: str, body: CoordinationRequestCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    request_body = body.model_dump()
    scope = f"{workspace_id}:coordination-requests:create"
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        replay = retry_receipt(session, scope, idempotency_key, request_body)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if workspace.mode not in {"SIMULATION", "REPLAY_T49"}:
            raise ApiError(409, "MODE_NOT_ALLOWED", "Internal requests are currently enabled only for synthetic workspaces.")
        aliases = {}
        for number, container in workspace.state.get("containers", {}).items():
            aliases[str(number)] = str(number)
            if container.get("id"):
                aliases[str(container["id"])] = str(number)
            if container.get("container_id"):
                aliases[str(container["container_id"])] = str(number)
        container_ids = []
        for identifier in body.container_ids:
            canonical = aliases.get(identifier)
            if canonical is None:
                raise ApiError(422, "CONTAINER_NOT_IN_WORKSPACE", "Select containers that belong to this workspace.")
            if canonical not in container_ids:
                container_ids.append(canonical)
        now = utcnow()
        provenance = {"origin_kind": "synthetic_internal_request", "workspace_mode": workspace.mode, "external_delivery": False, "physical_execution": False, "provider_fact_change": False, "authority": "internal_coordination_only"}
        history = [{"status": "open", "comment": body.comment, "actor": "workspace-owner", "at": now.isoformat()}]
        row = CoordinationRequest(id=str(uuid.uuid4()), workspace_id=workspace_id, status="open", owner_role=body.owner_role, service_kind=body.service_kind, title=body.title, comment=body.comment, container_ids=container_ids, payload={"provenance": provenance, "status_history": history}, revision=workspace.revision + 1, created_at=now, updated_at=now, resolved_at=None)
        session.add(row)
        increment_request_revision(session, workspace, "coordination_request.created", {"request_id": row.id, "title": row.title, "service_kind": row.service_kind, "owner_role": row.owner_role, "container_ids": container_ids, "provenance": provenance})
        result = envelope(coordination_request_data(row), workspace)
        save_receipt(session, scope, idempotency_key, request_body, result, 201)
        return respond(result, 201)


@router.patch("/workspaces/{workspace_id}/requests/{coordination_request_id}")
def update_coordination_request(workspace_id: str, coordination_request_id: str, body: CoordinationRequestUpdate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    request_body = body.model_dump(exclude_unset=True)
    scope = f"{workspace_id}:coordination-request:{coordination_request_id}"
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        replay = retry_receipt(session, scope, idempotency_key, request_body)
        if replay:
            return replay
        check_revision(workspace, if_match)
        row = session.get(CoordinationRequest, coordination_request_id)
        if row is None or row.workspace_id != workspace_id:
            raise ApiError(404, "REQUEST_NOT_FOUND", "This coordination request is not in the workspace.")
        now = utcnow()
        previous_status = row.status
        row.status = body.status
        if body.comment is not None:
            row.comment = body.comment
        row.updated_at = now
        row.resolved_at = (row.resolved_at or now) if body.status == "resolved" else None
        row.revision = workspace.revision + 1
        row.payload = {**row.payload, "status_history": [*row.payload.get("status_history", []), {"status": body.status, "comment": body.comment, "actor": "workspace-owner", "at": now.isoformat()}]}
        increment_request_revision(session, workspace, "coordination_request.updated", {"request_id": row.id, "previous_status": previous_status, "status": body.status, "comment": body.comment, "provider_fact_change": False, "external_delivery": False})
        result = envelope(coordination_request_data(row), workspace)
        save_receipt(session, scope, idempotency_key, request_body, result, 200)
        return respond(result)


def execute_command(workspace_id: str, command: dict, token: str | None, if_match: str | None, idempotency_key: str | None, route: str):
    database = get_database()
    original_command = copy.deepcopy(command)
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, token, lock=True)
        scope = f"{workspace_id}:{route}"
        replay = retry_receipt(session, scope, idempotency_key, original_command)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if command.get("command") not in {"task", "pause", "step", "seek", "advance", "reset"} and workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Operational changes require a simulation workspace.")
        try:
            name = command.get("command")
            if name == "pause":
                workspace.playback = {**(workspace.playback or {}), "playing": False, "status": "paused", "paused_reason": "operator_paused"}
                new_state = copy.deepcopy(workspace.state)
            elif name == "reset":
                workspace.playback = {**(workspace.playback or {}), "playing": False, "status": "paused", "paused_reason": "run_reset"}
                new_state = engine().create_state(command.get("scenario_id", workspace.state["scenario_id"]), command.get("seed", workspace.state["seed"]), workspace.mode)
            else:
                if name == "advance" and (type(command.get("minutes")) is not int or not 1 <= command["minutes"] <= 120):
                    raise ValueError("Advance must be 1–120 integer minutes per request")
                if name == "select_plan":
                    submitted = command.get("plan") or {}
                    plan_id = command.get("plan_id") or submitted.get("plan_id")
                    stored = session.get(Job, plan_id) if isinstance(plan_id, str) else None
                    if not stored or stored.workspace_id != workspace.id or stored.kind != "plan" or stored.status != "succeeded":
                        raise ApiError(404, "PLAN_NOT_FOUND", "Choose a completed plan from this workspace.")
                    if stored.input_revision != workspace.revision:
                        raise ApiError(412, "PLAN_STALE", "The workspace changed after this plan was computed. Generate a new plan.", True)
                    command = {"command": "select_plan", "plan": copy.deepcopy(stored.result)}
                new_state = engine().apply_command(copy.deepcopy(workspace.state), command)
        except (ValueError, KeyError, TypeError) as exc:
            raise ApiError(422, "VALIDATION_ERROR", str(exc)[:300])
        commit_state(session, workspace, new_state, f"command.{command.get('command', 'unknown')}", command)
        result = envelope(workspace_data(workspace), workspace)
        save_receipt(session, scope, idempotency_key, original_command, result, 200)
        return respond(result)


@router.post("/workspaces/{workspace_id}/commands")
def post_command(workspace_id: str, body: dict, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    return execute_command(workspace_id, body, x_workspace_token, if_match, idempotency_key, "commands")


@router.post("/workspaces/{workspace_id}/task-events")
def post_task_event(workspace_id: str, body: TaskEventCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    status = {"acknowledge": "acknowledged", "start": "in_progress", "wait": "waiting_external", "record_contact": "waiting_external", "record_result": "waiting_external"}[body.action]
    return execute_command(workspace_id, {"command": "task", "status": status, **body.model_dump(exclude_none=True)}, x_workspace_token, if_match, idempotency_key, "task-events")


@router.get("/workspaces/{workspace_id}/timeline")
def get_timeline(workspace_id: str, cursor: str | None = None, limit: int = Query(50, ge=1, le=200), x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        rows = list(session.scalars(select(AuditEvent).where(AuditEvent.workspace_id == workspace_id).order_by(AuditEvent.created_at.desc(), AuditEvent.id)))
        items = [{"id": row.id, "revision": row.revision, "action": row.action, "actor": row.actor, "payload": row.payload, "created_at": row.created_at.isoformat()} for row in rows]
        return respond(envelope(paginate(items, cursor, limit), workspace))


def job_data(job: Job) -> dict:
    return {"id": job.id, "job_id": job.id, "type": job.kind, "kind": job.kind, "status": job.status, "progress": job.progress, "input_revision": job.input_revision, "attempts": job.attempts, "result": job.result, "error": job.error, "retryable": bool(job.error and job.error.get("retryable")), "created_at": job.created_at.isoformat(), "finished_at": job.finished_at.isoformat() if job.finished_at else None, "result_resource": {"type": job.kind, "id": job.id} if job.status == "succeeded" else None}


def enqueue(workspace_id: str, kind: str, payload: dict, token: str | None, if_match: str | None, key: str | None):
    database = get_database()
    request_body = copy.deepcopy(payload)
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, token, lock=True)
        scope = f"{workspace_id}:{kind}-jobs"
        replay = retry_receipt(session, scope, key, payload)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if kind in {"plan", "experiment"} and workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Resource planning and experiments require a simulation workspace.")
        if payload.get("input_revision") not in {None, workspace.revision}:
            raise ApiError(412, "REVISION_CONFLICT", "This plan request references an older workspace version.", True)
        active = session.scalar(select(Job).where(Job.workspace_id == workspace_id, Job.kind == kind, Job.status.in_(["queued", "running"])))
        if active:
            raise ApiError(429, "JOB_ALREADY_RUNNING", "A job of this type is already running. Wait for its result.", True)
        if kind == "export" and payload.get("subject_type") != "handoff":
            referenced = session.get(Job, payload.get("subject_id"))
            if not referenced or referenced.workspace_id != workspace_id or referenced.kind != payload.get("subject_type") or referenced.status != "succeeded":
                raise ApiError(404, "RESULT_NOT_FOUND", "Choose a completed result from this workspace.")
            payload = {**payload, "subject_result": referenced.result}
        if kind == "experiment":
            scenario_id = payload.get("scenario_id") or workspace.state.get("scenario_id")
            if scenario_id not in {item["id"] for item in engine().scenario_catalog()}:
                raise ApiError(422, "VALIDATION_ERROR", "Choose a registered experiment scenario.")
            payload = {**payload, "scenario_id": scenario_id}
        if kind in {"plan", "experiment"} and (workspace.playback or {}).get("playing"):
            workspace.playback = {**workspace.playback, "playing": False, "status": "paused", "paused_reason": "computation_requested"}
            commit_state(session, workspace, workspace.state, "playback.paused", {"reason": "computation_requested"}, "system")
        job = Job(id=str(uuid.uuid4()), workspace_id=workspace.id, kind=kind, status="queued", input_revision=workspace.revision, payload=serializable(payload), state_snapshot=copy.deepcopy(workspace.state), progress=0, attempts=0, created_at=utcnow())
        session.add(job)
        audit(session, workspace, f"{kind}.queued", {"job_id": job.id, "parameters": {k: v for k, v in payload.items() if k != "subject_result"}})
        result = envelope(job_data(job), workspace)
        # Bind to the original browser body, not the enriched internal payload.
        save_receipt(session, scope, key, request_body, result, 202)
    from .worker import notify_worker
    notify_worker()
    return respond(result, 202)


@router.post("/workspaces/{workspace_id}/plan-jobs", status_code=202)
def post_plan(workspace_id: str, body: PlanCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    payload = body.model_dump()
    return enqueue(workspace_id, "plan", payload, x_workspace_token, if_match, idempotency_key)


@router.post("/workspaces/{workspace_id}/experiments", status_code=202)
def post_experiment(workspace_id: str, body: ExperimentCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    payload = body.model_dump()
    return enqueue(workspace_id, "experiment", payload, x_workspace_token, if_match, idempotency_key)


@router.post("/workspaces/{workspace_id}/exports", status_code=202)
def post_export(workspace_id: str, body: ExportCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    payload = body.model_dump()
    return enqueue(workspace_id, "export", payload, x_workspace_token, if_match, idempotency_key)


@router.get("/workspaces/{workspace_id}/jobs/{job_id}")
@router.get("/workspaces/{workspace_id}/plans/{job_id}")
@router.get("/workspaces/{workspace_id}/experiments/{job_id}")
@router.get("/workspaces/{workspace_id}/exports/{job_id}")
def get_job(workspace_id: str, job_id: str, x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        job = session.get(Job, job_id)
        if job is None or job.workspace_id != workspace_id:
            raise ApiError(404, "JOB_NOT_FOUND", "This result is not in the workspace.")
        return respond(envelope(job_data(job), workspace))


@router.post("/workspaces/{workspace_id}/playback")
def post_playback(workspace_id: str, body: PlaybackChange, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    payload = body.model_dump()
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        scope = f"{workspace_id}:playback"
        replay = retry_receipt(session, scope, idempotency_key, payload)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Server playback currently requires a simulation workspace.")
        workspace.playback = {**payload, "last_tick_at": utcnow().isoformat(), "status": "playing" if body.playing else "paused", "paused_reason": None}
        commit_state(session, workspace, workspace.state, "playback.changed", payload)
        result = envelope(workspace_data(workspace), workspace)
        save_receipt(session, scope, idempotency_key, payload, result, 200)
    from .worker import notify_worker
    notify_worker()
    return respond(result)


def stream_version(workspace_id: str, token: str | None) -> dict:
    with get_database().session() as session:
        row = session.execute(select(Workspace.revision, Workspace.playback, Workspace.token_hash).where(Workspace.id == workspace_id)).one_or_none()
        if not row or not token or not hmac.compare_digest(row.token_hash, token_digest(token)):
            raise ApiError(404, "WORKSPACE_NOT_FOUND", "This workspace is unavailable or its access token is missing.")
        return {"revision": row.revision, "workspace_id": workspace_id, "playback": row.playback}


@router.get("/workspaces/{workspace_id}/stream")
async def workspace_stream(workspace_id: str, request: Request, x_workspace_token: str | None = Header(None)):
    await asyncio.to_thread(stream_version, workspace_id, x_workspace_token)

    async def events():
        last_revision = -1
        heartbeat = 0
        while not await request.is_disconnected():
            event = await asyncio.to_thread(stream_version, workspace_id, x_workspace_token)
            if event["revision"] != last_revision:
                last_revision = event["revision"]
                yield f"event: revision\ndata: {json.dumps(event)}\n\n"
            heartbeat += 1
            if heartbeat % 15 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/workspaces/{workspace_id}/simulation-runs")
def create_simulation_run(workspace_id: str, body: SimulationCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        if workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Creating a simulation run requires a simulation workspace.")
    if body.parameter_overrides:
        raise ApiError(422, "VALIDATION_ERROR", "Parameter overrides are not enabled for this scenario version.")
    return execute_command(workspace_id, {"command": "reset", "scenario_id": body.scenario_id, "seed": body.seed}, x_workspace_token, if_match, idempotency_key, "simulation-runs")


@router.get("/workspaces/{workspace_id}/simulation-runs/{run_id}")
def get_simulation_run(workspace_id: str, run_id: str, x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        if workspace.mode != "SIMULATION" or run_id not in {workspace.id, str(workspace.state.get("run_id"))}:
            raise ApiError(404, "RUN_NOT_FOUND", "This simulation run is not available.")
        return respond(envelope(workspace_data(workspace), workspace))


@router.post("/workspaces/{workspace_id}/simulation-runs/{run_id}/commands")
def post_run_command(workspace_id: str, run_id: str, body: dict, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        if workspace.mode != "SIMULATION" or run_id not in {workspace.id, str(workspace.state.get("run_id"))}:
            raise ApiError(404, "RUN_NOT_FOUND", "This simulation run is not available.")
    return execute_command(workspace_id, body, x_workspace_token, if_match, idempotency_key, "run-commands")


@router.post("/workspaces/{workspace_id}/simulation-runs/{run_id}/plan-selections")
def post_plan_selection(workspace_id: str, run_id: str, body: PlanSelection, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        if workspace.mode != "SIMULATION" or run_id not in {workspace.id, str(workspace.state.get("run_id"))}:
            raise ApiError(404, "RUN_NOT_FOUND", "This simulation run is not available.")
        job = session.get(Job, body.plan_id)
        if not job or job.workspace_id != workspace_id or job.kind != "plan" or job.status != "succeeded":
            raise ApiError(404, "PLAN_NOT_FOUND", "Choose a completed plan from this workspace.")
        if job.input_revision != body.input_revision:
            raise ApiError(412, "PLAN_STALE", "New evidence arrived after this plan was computed. Generate a new plan.", True)
        plan_result = copy.deepcopy(job.result)
    return execute_command(workspace_id, {"command": "select_plan", "plan": plan_result}, x_workspace_token, if_match, idempotency_key, "plan-selections")


@router.get("/health/live")
def health_live():
    return respond(envelope({"status": "ok", "service": "gate-triage-workbench"}))


@router.get("/health/ready")
def health_ready():
    from .worker import worker_status
    database = get_database()
    ready = database.ready()
    worker = worker_status()
    return respond(envelope({"status": "ready" if ready and worker["running"] else "degraded", "database": "postgresql" if database.engine.dialect.name == "postgresql" else "sqlite", "database_ready": ready, "worker": worker, "live_terminal49": False}), 200 if ready and worker["running"] else 503)


# Provider ingress is deliberately separate from anonymous workspace writes.
from .connector import install_webhook
install_webhook(router)
