"""Relational, paged port-volume rehearsal independent of the precision world."""
from __future__ import annotations

import copy
import importlib
import uuid
from datetime import datetime

from fastapi import APIRouter, Header, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, case, func, insert, select, update
from sqlalchemy.orm import Mapped, mapped_column

from .api import ApiError, authorized_workspace, check_revision, envelope, increment_request_revision, job_data, respond, retry_receipt, save_receipt
from .db import Base, Job, Workspace, get_database, utcnow

router = APIRouter(prefix="/api/v1", tags=["relational synthetic port scale"])
TERMINALS = ("terminal-fenix", "terminal-apm", "terminal-everport", "terminal-trapac", "terminal-yusen", "terminal-wbct-cs", "terminal-wbct-latil")
STATUSES = ("scheduled", "queued", "blocked", "in_service", "completed")
WINDOW_LIMIT = 2000


class ScaleRun(Base):
    __tablename__ = "wb_scale_runs"
    __table_args__ = (CheckConstraint("clock_min >= 0 AND clock_min <= horizon_minutes", name="ck_wb_scale_clock"), CheckConstraint("status IN ('queued','running','ready','failed')", name="ck_wb_scale_run_status"), CheckConstraint("total_records >= 0 AND expected_records > 0", name="ck_wb_scale_record_counts"))
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(40), ForeignKey("wb_workspaces.id", ondelete="CASCADE"), index=True)
    profile: Mapped[str] = mapped_column(String(40))
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    clock_min: Mapped[int] = mapped_column(Integer, default=0)
    horizon_minutes: Mapped[int] = mapped_column(Integer)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    expected_records: Mapped[int] = mapped_column(Integer)
    resource_state: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    next_sequence: Mapped[int] = mapped_column(Integer, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    job_id: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScaleMovement(Base):
    __tablename__ = "wb_scale_movements"
    __table_args__ = (UniqueConstraint("run_id", "number", name="uq_wb_scale_number"), CheckConstraint("teu IN (1,2)", name="ck_wb_scale_teu"), CheckConstraint("arrival_min >= 0 AND ready_min >= arrival_min AND service_min > 0", name="ck_wb_scale_timing"), CheckConstraint("status IN ('scheduled','queued','blocked','in_service','completed')", name="ck_wb_scale_movement_status"), CheckConstraint("completed_min IS NULL OR (started_min IS NOT NULL AND completed_min >= started_min)", name="ck_wb_scale_completion"), Index("ix_wb_scale_terminal_status", "run_id", "terminal_id", "status"), Index("ix_wb_scale_arrival", "run_id", "arrival_min", "id"), Index("ix_wb_scale_ready", "run_id", "ready_min"))
    run_id: Mapped[str] = mapped_column(String(40), ForeignKey("wb_scale_runs.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    number: Mapped[str] = mapped_column(String(30))
    terminal_id: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(40))
    teu: Mapped[int] = mapped_column(Integer)
    arrival_min: Mapped[int] = mapped_column(Integer)
    ready_min: Mapped[int] = mapped_column(Integer)
    service_min: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer)
    blocked: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(24))
    started_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    last_event_sequence: Mapped[int] = mapped_column(Integer, default=0)


class ScaleEvent(Base):
    __tablename__ = "wb_scale_events"
    __table_args__ = (CheckConstraint("sequence > 0 AND at_min >= 0 AND record_count >= 0", name="ck_wb_scale_event_counts"),)
    run_id: Mapped[str] = mapped_column(String(40), ForeignKey("wb_scale_runs.id", ondelete="CASCADE"), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    at_min: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(60))
    terminal_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScaleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    profile: str = Field(default="la_average_day", max_length=40)
    seed: int = Field(default=17, ge=0, le=2147483647)


class ScaleAdvance(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    minutes: int = Field(default=15, ge=1, le=120)


def model():
    return importlib.import_module("gate_triage.workbench.scale_simulation")


def profiles() -> list[dict]:
    return model().profile_catalog()


def profile_for(identifier: str) -> dict:
    item = next((item for item in profiles() if item.get("id", item.get("profile")) == identifier), None)
    if item is None:
        raise ApiError(422, "PROFILE_NOT_FOUND", "Choose a registered port-volume profile.")
    return item


def latest_run(session, workspace_id: str, *, required: bool = False) -> ScaleRun | None:
    run = session.scalar(select(ScaleRun).where(ScaleRun.workspace_id == workspace_id).order_by(ScaleRun.created_at.desc(), ScaleRun.id).limit(1))
    if required and (run is None or run.status != "ready"):
        raise ApiError(409, "SCALE_NOT_READY", "Generate a port-volume dataset and wait for its job to finish.")
    return run


def run_data(run: ScaleRun | None) -> dict | None:
    if run is None:
        return None
    return {"id": run.id, "profile": run.profile, "seed": run.seed, "status": run.status, "clock_min": run.clock_min, "horizon_minutes": run.horizon_minutes, "total_records": run.total_records, "expected_records": run.expected_records, "revision": run.revision, "job_id": run.job_id, "calibration": run.metadata_json.get("calibration", {}), "assumptions": run.metadata_json.get("assumptions", []), "created_at": run.created_at.isoformat(), "updated_at": run.updated_at.isoformat()}


def summary(session, run: ScaleRun | None) -> dict:
    if run is None or run.status != "ready":
        return {"total_records": 0, "counts_by_status": {}, "teu_total": 0, "completed_movements": 0, "terminals": []}
    groups = session.execute(select(ScaleMovement.terminal_id, ScaleMovement.status, func.count(), func.sum(ScaleMovement.teu)).where(ScaleMovement.run_id == run.id).group_by(ScaleMovement.terminal_id, ScaleMovement.status)).all()
    totals, terminals, total_teu = {}, {}, 0
    for terminal, status, count, teu in groups:
        totals[status] = totals.get(status, 0) + count
        entry = terminals.setdefault(terminal, {"terminal_id": terminal, "name": terminal.removeprefix("terminal-").replace("-", " ").upper(), "total_records": 0, "teu_total": 0, "completed_movements": 0, "counts_by_status": {}})
        entry["counts_by_status"][status] = count
        entry["total_records"] += count
        entry["teu_total"] += teu or 0
        entry["completed_movements"] += count if status == "completed" else 0
        total_teu += teu or 0
    return {"total_records": sum(totals.values()), "counts_by_status": totals, "teu_total": total_teu, "completed_movements": totals.get("completed", 0), "terminals": [terminals[key] for key in TERMINALS if key in terminals], "scope": "synthetic_movement_cohort_not_concurrent_inventory", "decision_window_limit_per_terminal": WINDOW_LIMIT}


@router.get("/workspaces/{workspace_id}/scale")
def get_scale(workspace_id: str, x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        run = latest_run(session, workspace_id)
        return respond(envelope({"profiles": profiles(), "run": run_data(run), "summary": summary(session, run), "mode": "SYNTHETIC_SCALE", "decision_window_limit": WINDOW_LIMIT, "clock_independent_from_precision": True, "notice": "Official annual TEU calibrates synthetic movement volume; allocation, dwell and service capacity are assumptions. No whole-port CP-SAT plan or real inventory is claimed."}, workspace))


@router.post("/workspaces/{workspace_id}/scale", status_code=202)
def create_scale(workspace_id: str, body: ScaleCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    payload = body.model_dump()
    scope = f"{workspace_id}:scale:create"
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        replay = retry_receipt(session, scope, idempotency_key, payload)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Port-volume generation requires a synthetic simulation workspace.")
        prior_run = latest_run(session, workspace_id)
        incident_rows = workspace.state.get("emergency_incidents", {})
        active_incidents = incident_rows.values() if isinstance(incident_rows, dict) else incident_rows
        if prior_run and any(item.get("status") != "resolved" and item.get("scale_run_id") == prior_run.id and item.get("scale_assessment", {}).get("applicable") for item in active_incidents):
            raise ApiError(409, "SCALE_INCIDENT_ACTIVE", "Resolve the current run's modeled incidents before generating a replacement dataset, or create a separate workspace.")
        config = profile_for(body.profile)
        if session.scalar(select(Job.id).where(Job.workspace_id == workspace_id, Job.kind == "scale_seed", Job.status.in_(["queued", "running"]))):
            raise ApiError(429, "JOB_ALREADY_RUNNING", "A volume generation job is already running.", True)
        now = utcnow()
        run_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
        expected = int(config.get("record_count", config.get("total_records", 0)))
        if not 1 <= expected <= 200000:
            raise ApiError(422, "PROFILE_NOT_SUPPORTED", "This profile exceeds the local rehearsal size limit.")
        run = ScaleRun(id=run_id, workspace_id=workspace_id, profile=body.profile, seed=body.seed, status="queued", clock_min=0, horizon_minutes=int(config["horizon_minutes"]), total_records=0, expected_records=expected, resource_state={}, metadata_json=config, next_sequence=1, revision=1, job_id=job_id, created_at=now, updated_at=now)
        session.add(run)
        workspace.state = {**workspace.state, "scale_run_id": run_id, "scale_clock_min": 0}
        increment_request_revision(session, workspace, "scale.generation_queued", {"run_id": run_id, "profile": body.profile, "expected_records": expected, "separate_from_precision_world": True})
        job = Job(id=job_id, workspace_id=workspace_id, kind="scale_seed", status="queued", input_revision=workspace.revision, payload={"run_id": run_id, **payload}, state_snapshot={}, progress=0, attempts=0, created_at=now)
        session.add(job)
        result = envelope({**job_data(job), "run_id": run_id, "profile": body.profile, "expected_records": expected}, workspace)
        save_receipt(session, scope, idempotency_key, payload, result, 202)
    from .worker import notify_worker
    notify_worker()
    return respond(result, 202)


def seed_scale(job: dict) -> dict:
    """Stream the cohort into one transaction; completed retries reuse the run."""
    database = get_database()
    run_id = job["payload"]["run_id"]
    try:
        with database.session() as session:
            session.execute(update(ScaleRun).where(ScaleRun.id == run_id, ScaleRun.status != "ready").values(status="running", updated_at=utcnow()))
        with database.session() as session:
            run = session.scalar(select(ScaleRun).where(ScaleRun.id == run_id).with_for_update())
            if run is None or run.workspace_id != job["workspace_id"]:
                raise ValueError("Scale run is not in the job workspace")
            if run.status == "ready":
                return {"run_id": run.id, "total_records": run.total_records, "status": "ready", "reused": True}
            count = 0
            for batch in model().iter_movement_batches(run.profile, seed=run.seed, batch_size=1000):
                values = []
                for row in batch:
                    values.append({"run_id": run.id, "id": row["id"], "number": row["number"], "terminal_id": row["terminal_id"], "category": row["category"], "teu": row["teu"], "arrival_min": row["arrival_min"], "ready_min": row["ready_min"], "service_min": row["service_min"], "priority": row["priority"], "blocked": bool(row["blocked"]), "status": "scheduled", "started_min": None, "completed_min": None, "payload": row.get("payload", {}), "last_event_sequence": 0})
                session.execute(insert(ScaleMovement), values)
                count += len(values)
                if database.engine.dialect.name == "postgresql":
                    with database.session() as progress:
                        progress.execute(update(Job).where(Job.id == job["id"], Job.status == "running").values(progress=min(90, 10 + int(80 * count / run.expected_records))))
            if count != run.expected_records:
                raise ValueError("Generated movement count differs from the calibrated profile")
            run.total_records = count
            run.status = "ready"
            run.revision += 1
            run.updated_at = utcnow()
            session.add(ScaleEvent(run_id=run.id, sequence=run.next_sequence, at_min=0, event_type="cohort.seeded", terminal_id=None, record_count=count, payload={"profile": run.profile, "seed": run.seed, "synthetic": True, "scope": "movement_flow_not_inventory"}, created_at=utcnow()))
            run.next_sequence += 1
            return {"run_id": run.id, "total_records": count, "status": "ready", "scope": "synthetic_movement_cohort_not_concurrent_inventory"}
    except Exception:
        with database.session() as session:
            session.execute(update(ScaleRun).where(ScaleRun.id == run_id, ScaleRun.status != "ready").values(status="failed", updated_at=utcnow()))
        raise


def movement_data(row: ScaleMovement) -> dict:
    return {key: getattr(row, key) for key in ("id", "number", "terminal_id", "category", "teu", "arrival_min", "ready_min", "service_min", "priority", "blocked", "status", "started_min", "completed_min", "last_event_sequence", "payload")}


@router.get("/workspaces/{workspace_id}/scale/containers")
def get_scale_containers(workspace_id: str, offset: int = Query(0, ge=0, le=200000), limit: int = Query(50, ge=1, le=100), terminal_id: str | None = None, status: str | None = None, query: str = Query("", max_length=100), x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        run = latest_run(session, workspace_id, required=True)
        if terminal_id is not None and terminal_id not in TERMINALS or status is not None and status not in STATUSES:
            raise ApiError(422, "VALIDATION_ERROR", "Choose a registered terminal and movement status.")
        filters = [ScaleMovement.run_id == run.id]
        if terminal_id:
            filters.append(ScaleMovement.terminal_id == terminal_id)
        if status:
            filters.append(ScaleMovement.status == status)
        if query:
            filters.append(ScaleMovement.number.contains(query, autoescape=True))
        count = session.scalar(select(func.count()).select_from(ScaleMovement).where(*filters))
        items = session.scalars(select(ScaleMovement).where(*filters).order_by(ScaleMovement.arrival_min, ScaleMovement.id).offset(offset).limit(limit))
        return respond(envelope({"items": [movement_data(row) for row in items], "total": count, "offset": offset, "limit": limit, "run_id": run.id}, workspace))


@router.get("/workspaces/{workspace_id}/scale/events")
def get_scale_events(workspace_id: str, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        run = latest_run(session, workspace_id, required=True)
        count = session.scalar(select(func.count()).select_from(ScaleEvent).where(ScaleEvent.run_id == run.id))
        rows = session.scalars(select(ScaleEvent).where(ScaleEvent.run_id == run.id).order_by(ScaleEvent.sequence.desc()).offset(offset).limit(limit))
        items = [{"sequence": row.sequence, "at_min": row.at_min, "event_type": row.event_type, "terminal_id": row.terminal_id, "record_count": row.record_count, "details": {key: value for key, value in row.payload.items() if key != "updates"}} for row in rows]
        return respond(envelope({"items": items, "total": count, "offset": offset, "limit": limit, "run_id": run.id}, workspace))


def incident_targets(scenario: str, scope: str) -> tuple[str, ...]:
    """Only compatible scopes can restrict the bulk model's phase resources."""
    compatible_zones = {
        "battery_access_2024": {"zone-gate-east", "zone-gate-west", "corridor-road-exit"},
        "storm_wind": {"zone-vessel-load", "zone-vessel-unload"},
        "channel_obstruction_2024": {"corridor-main-channel"},
        "exit_congestion": {"zone-gate-east", "zone-gate-west", "corridor-road-exit"},
        "cyber_data_2017": set(),
        # A single yard/reefer/asset zone is not the whole terminal's coarse
        # service pool. Precision effects handle mapped individual assets.
        "earthquake_asset_inspection": set(),
    }
    if scenario not in compatible_zones:
        return ()
    if scope == "port-la":
        return TERMINALS
    if scope in TERMINALS:
        return (scope,)
    if scope not in compatible_zones[scenario]:
        return ()
    return TERMINALS if scope.startswith("corridor-") else ("terminal-fenix",)


def scale_incident_assessment(session, workspace: Workspace, scenario: str, scope: str, severity: str) -> dict:
    run = latest_run(session, workspace.id)
    targets = incident_targets(scenario, scope)
    active = run is not None and run.status == "ready" and bool(targets) and severity != "watch"
    return {"applicable": active, "run_id": run.id if run and run.status == "ready" else None, "clock_min": run.clock_min if run and run.status == "ready" else 0, "affected_terminal_ids": list(targets) if active else [], "mode": "synthetic_phase_flow", "precision_world_unchanged": True, "limitation": "Bulk phase-level resource assumptions; no real terminal equipment, live inventory or global whole-port schedule."}


def scale_restrictions(state: dict, run_id: str | None = None) -> dict:
    restrictions = {terminal: {"closed": False, "capacity": 12} for terminal in TERMINALS}
    incident_rows = state.get("emergency_incidents", {})
    for incident in incident_rows.values() if isinstance(incident_rows, dict) else incident_rows:
        if incident.get("status") == "resolved" or incident.get("severity") == "watch" or not incident.get("scale_assessment", {}).get("applicable"):
            continue
        if incident.get("scale_run_id") != (run_id or state.get("scale_run_id")):
            continue
        scenario = incident.get("scenario_id")
        targets = incident_targets(scenario, incident.get("scope_id", ""))
        for terminal in targets:
            rule = restrictions[terminal]
            rule.setdefault("phase_incidents", []).append({"scenario_id": scenario, "started_at_min": incident.get("scale_created_at_min", 0)})
            if scenario == "cyber_data_2017":
                rule["source_offline"] = True
    return restrictions


@router.post("/workspaces/{workspace_id}/scale/advance")
def advance_scale(workspace_id: str, body: ScaleAdvance, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    payload = body.model_dump()
    scope = f"{workspace_id}:scale:advance"
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        replay = retry_receipt(session, scope, idempotency_key, payload)
        if replay:
            return replay
        check_revision(workspace, if_match)
        run = latest_run(session, workspace_id, required=True)
        run = session.scalar(select(ScaleRun).where(ScaleRun.id == run.id).with_for_update())
        if run.clock_min >= run.horizon_minutes:
            raise ApiError(409, "SCALE_HORIZON_REACHED", "The movement-flow rehearsal has reached its horizon. Generate a new dataset to restart.")
        target = min(run.horizon_minutes, run.clock_min + body.minutes)
        restrictions = scale_restrictions(workspace.state, run.id)
        input_rows = []
        for terminal in TERMINALS:
            candidates = session.scalars(select(ScaleMovement).where(ScaleMovement.run_id == run.id, ScaleMovement.terminal_id == terminal, ScaleMovement.status != "completed", ScaleMovement.arrival_min <= target).order_by(case((ScaleMovement.status == "in_service", 0), else_=1), ScaleMovement.blocked, ScaleMovement.arrival_min, ScaleMovement.id).limit(WINDOW_LIMIT))
            input_rows.extend(movement_data(row) for row in candidates)
        computed = model().schedule_window(input_rows, from_min=run.clock_min, to_min=target, resource_state=copy.deepcopy(run.resource_state), restrictions=restrictions)
        updates = computed["updates"]
        allowed = {row["id"] for row in input_rows}
        if len({change["id"] for change in updates}) != len(updates):
            raise ApiError(409, "SCALE_GUARD_REJECTED", "A movement cannot be updated twice in one decision window.")
        for change in updates:
            if change["id"] not in allowed or change["status"] not in STATUSES:
                raise ApiError(409, "SCALE_GUARD_REJECTED", "The bounded movement scheduler returned an invalid record.")
            if change.get("completed_min") is not None and change["completed_min"] > target:
                raise ApiError(409, "SCALE_GUARD_REJECTED", "Future completions cannot count as completed movements.")
        sequence = run.next_sequence
        mappings = [{"run_id": run.id, "id": change["id"], "status": change["status"], "started_min": change.get("started_min"), "completed_min": change.get("completed_min"), "last_event_sequence": sequence} for change in updates]
        if mappings:
            session.execute(update(ScaleMovement), mappings, execution_options={"synchronize_session": False})
        session.add(ScaleEvent(run_id=run.id, sequence=sequence, at_min=target, event_type="simulation.window_advanced", terminal_id=None, record_count=len(updates), payload={"from_min": run.clock_min, "to_min": target, "updates": updates, "restrictions": restrictions, "metrics": computed.get("metrics", {}), "decision_window_limit_per_terminal": WINDOW_LIMIT, "synthetic": True}, created_at=utcnow()))
        run.next_sequence += 1
        run.clock_min = target
        run.resource_state = computed["resource_state"]
        run.revision += 1
        run.updated_at = utcnow()
        updated_world = {**workspace.state, "scale_clock_min": target, "scale_run_id": run.id}
        workspace.state = updated_world
        increment_request_revision(session, workspace, "scale.advanced", {"run_id": run.id, "clock_min": target, "changed_records": len(updates), "separate_precision_clock": True})
        result = envelope({"run": run_data(run), "summary": summary(session, run), "changed_records": len(updates), "restrictions": restrictions}, workspace)
        save_receipt(session, scope, idempotency_key, payload, result, 200)
        return respond(result)
