"""Inspectable emergency coordination for the synthetic spatial workbench.

The workflow calls real local assessment, retrieval, validation and database
tools. It does not simulate an LLM call, contact a stakeholder, or turn a human
acknowledgement into external movement authority.
"""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .api import ApiError, authorized_workspace, check_revision, commit_state, envelope, respond, retry_receipt, save_receipt, workspace_data
from .db import CoordinationRequest, get_database, utcnow
from .knowledge import passages, search_sources

router = APIRouter(prefix="/api/v1", tags=["synthetic emergency coordination"])


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    scenario_id: str = Field(min_length=1, max_length=100)
    scope_id: str = Field(min_length=1, max_length=100)
    severity: Literal["critical", "restricted", "watch"] = "critical"
    note: str = Field(default="", max_length=4000)


class IncidentResolve(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    acknowledged: StrictBool
    note: str = Field(min_length=1, max_length=4000)


class IncidentAcknowledge(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str = Field(default="", max_length=4000)


def spatial():
    return importlib.import_module("gate_triage.workbench.spatial")


def effect_engine():
    return importlib.import_module("gate_triage.workbench.spatial_simulation")


def records(state: dict) -> dict:
    value = state.get("emergency_incidents", {})
    return value if isinstance(value, dict) else {row["id"]: row for row in value}


def incident_view(incident: dict, clock_min: int, scale_clock_min: int | None = None, scale_run_id: str | None = None) -> dict:
    result = copy.deepcopy(incident)
    if result.get("scale_assessment", {}).get("applicable") and result.get("status") != "resolved":
        result["proposal"]["summary"] = "Apply the recorded phase restrictions in this synthetic scale run. Precision-world resource permissions remain independent; coordinate human-led recovery."
        for stage in result.get("workflow", []):
            if stage.get("stage") == "validate":
                stage.update(status="complete", summary="The synthetic scale run and affected phases are validated. Fine-grained precision resources and external permissions remain independent.")
    escalation = result.setdefault("escalation", {})
    due = int(escalation.get("due_at_min", result.get("created_at_min", 0) + 10))
    acknowledged = bool(escalation.get("acknowledged"))
    precision_elapsed = max(0, clock_min - int(result.get("created_at_min", 0)))
    scale_elapsed = max(0, (scale_clock_min or 0) - int(result.get("scale_created_at_min", 0))) if result.get("scale_run_id") and (scale_run_id is None or result["scale_run_id"] == scale_run_id) else 0
    elapsed = max(precision_elapsed, scale_elapsed)
    overdue = result.get("status") != "resolved" and not acknowledged and elapsed >= 10
    escalation.update(overdue=overdue, due_at_min=due, elapsed_minutes=elapsed, precision_elapsed_minutes=precision_elapsed, scale_elapsed_minutes=scale_elapsed, effective_severity="critical" if overdue else result.get("severity", "watch"), policy="synthetic-escalation-10min", automatic_external_dispatch=False)
    if overdue:
        escalation["status"] = "overdue"
        escalation["overdue_reason"] = "No simulated human ownership acknowledgement within 10 virtual minutes."
    elif result.get("status") == "resolved":
        escalation["status"] = "resolved"
    elif acknowledged:
        escalation["status"] = "acknowledged"
    return result


def event(state: dict, incident: dict, action: str, detail: str) -> None:
    state.setdefault("timeline", []).append({"id": "emergency-event-" + str(uuid.uuid4()), "at_min": state.get("clock_min", 0), "type": f"incident.{action}", "title": f"{incident['title']} · {action}", "detail": detail, "source": "Synthetic emergency coordinator", "incident_id": incident["id"], "scope_id": incident["scope_id"]})


def lookup_scenario(scenario_id: str) -> dict:
    scenario = next((item for item in spatial().incident_catalog() if item.get("id", item.get("scenario_id")) == scenario_id), None)
    if scenario is None:
        raise ApiError(422, "SCENARIO_NOT_FOUND", "Choose a registered emergency scenario.")
    return scenario


def source_retrieval(scenario: dict) -> dict:
    query = " ".join(str(scenario.get(key, "")) for key in ("name", "title", "description", "retrieval_query"))
    retrieved = search_sources(query or "incident scoped recovery", limit=10)
    by_id = {item["source_id"]: item for item in passages()}
    sources = []
    for reference in [*scenario.get("source_refs", []), *scenario.get("sources", [])]:
        item = by_id.get(reference) if isinstance(reference, str) else reference
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if url:
            sources.append({"title": item.get("source_title", item.get("title", "Historical reference")), "url": url, "scope": item.get("scope", item.get("supported_background", "Historical background; not a current incident notification.")), "kind": "historical_background"})
    allowed_urls = {item["url"] for item in sources}
    # A year/name token may rank an unrelated disaster highly. The scenario's
    # curated sources define historical scope; local product policy is separate.
    selected = [item for item in retrieved["items"] if item["url"] in allowed_urls or item["kind"] == "product_policy" and (item["source_id"] == "local_contract" or item["id"] in {"departure", "feed", "optimization", "rag"})]
    for item in selected:
        sources.append({"title": item.get("source_title", item["title"]), "url": item["url"], "scope": item["scope"], "kind": item["kind"]})
    unique = {}
    for item in sources:
        unique.setdefault(item["url"], item)
    return {"method": retrieved["method"], "llm_used": False, "query": query, "source_guard": {"policy": "scenario_historical_urls_or_relevant_product_policy", "allowed_source_ids": [item["source_id"] for item in selected], "excluded_count": len(retrieved["items"]) - len(selected)}, "sources": list(unique.values()), "passages": [{key: item[key] for key in ("id", "title", "passage", "url", "scope", "kind")} for item in selected]}


def workflow_and_proposal(state: dict, scenario: dict, assessment: dict, body: IncidentCreate) -> dict:
    retrieval = source_retrieval(scenario)
    known = bool(assessment.get("known_scope"))
    modeled = bool(assessment.get("modeled_scope"))
    effects = assessment.get("effects", [])
    supported = isinstance(effects, list) and all(isinstance(effect, dict) and effect.get("kind") in {"resource_capacity", "feed_offline", "marine_channel"} for effect in effects)
    apply_effects = known and modeled and bool(assessment.get("applicable", effects)) and body.severity != "watch" and supported
    owner = scenario.get("owner_role", "terminal_operations")
    if not known:
        owner = "terminal_operations"
    if not isinstance(owner, str):
        owner = "terminal_operations"
    limitations = list(assessment.get("limitations", []))
    if not known:
        limitations.append("The reported scope is unknown. Confirm its location before applying operational restrictions.")
    elif not modeled:
        limitations.append("This scope is outside the executable terminal model. Report impact and escalate without inventing gate throughput changes.")
    if body.severity == "watch":
        limitations.append("A warning is recorded for monitoring; it does not automatically close a route or resource.")
    limitations.append("All site effects are synthetic. Historical sources do not establish current closure or grant release authority.")
    type_specific = [{"id": f"{body.scenario_id}-step-{index + 1}", "title": step, "owner_role": owner, "execution": "internal_coordination", "status": "proposed", "type_specific": True} for index, step in enumerate(scenario.get("response_steps", []))]
    actions = [*type_specific,
        {"id": "confirm-scope", "title": "Confirm the affected area and current incident report", "owner_role": owner, "execution": "internal_coordination", "status": "needs_human"},
        {"id": "protect-scope", "title": "Apply only the validated modeled restrictions" if apply_effects else "Monitor and validate before changing modeled capacity", "owner_role": "terminal_operations", "execution": "simulation_only", "status": "recorded" if apply_effects else "proposed"},
        {"id": "continue-feasible", "title": "Continue eligible work outside the affected scope under existing guards", "owner_role": "terminal_operations", "execution": "simulation_only", "status": "proposed"},
        {"id": "preserve-authority", "title": "Keep customs, source availability and independent blockers intact", "owner_role": "customs_broker", "execution": "internal_coordination", "status": "recorded"},
        {"id": "recovery-review", "title": "Require human acknowledgement for staged recovery", "owner_role": owner, "execution": "internal_coordination", "status": "needs_human"},
    ]
    trace = [
        {"stage": "observe", "status": "complete", "tool": "workspace.snapshot", "summary": f"Recorded a synthetic {body.severity} report for {body.scope_id} at virtual minute {state.get('clock_min', 0)}.", "input": {"scenario_id": body.scenario_id, "scope_id": body.scope_id, "note": body.note}},
        {"stage": "impact", "status": "complete" if known else "needs_human", "tool": "spatial.assess_incident", "summary": f"Located {len(assessment.get('affected_container_ids', []))} affected tracked records; modeled scope: {modeled}.", "output": assessment},
        {"stage": "retrieve", "status": "complete", "tool": "knowledge.search_sources", "summary": f"Retrieved {len(retrieval['sources'])} inspectable source references using local search.", "method": retrieval["method"], "passages": retrieval["passages"], "source_guard": retrieval["source_guard"]},
        {"stage": "validate", "status": "complete" if apply_effects else "needs_human", "tool": "simulation.permission_guard", "summary": "Scope and modeled effects validated; independent permission guards stay active." if apply_effects else "No operational effect applied until scope/model conditions permit it.", "checks": {"simulation_mode": state.get("mode") == "SIMULATION", "known_scope": known, "modeled_scope": modeled, "supported_effects": supported, "watch_only": body.severity == "watch", "external_dispatch": False, "provider_clearance": False}},
        {"stage": "escalate", "status": "needs_human", "tool": "db.coordination_requests", "summary": f"Create a durable internal follow-up for {owner}; no outside message is sent.", "owner_role": owner},
    ]
    return {"workflow": trace, "sources": retrieval["sources"], "effects": copy.deepcopy(effects) if apply_effects else [], "proposed_effects": copy.deepcopy(effects), "status": "active" if apply_effects and effects else "monitoring", "owner_role": owner, "proposal": {"summary": "Restrict the affected modeled scope, preserve independent holds, and coordinate human-led recovery." if apply_effects else "Monitor, confirm scope and escalate; avoid unsupported changes to operations.", "strategy": copy.deepcopy(scenario.get("dispatcher_strategy", {})), "actions": actions, "requires_human": True, "limitations": limitations}, "orchestrator": {"kind": "deterministic_policy_workflow", "version": "emergency-workflow-1", "llm_used": False, "external_dispatch": False}}


def permission_guard(before: dict, after: dict, *, allow_queued_reconciliation: bool = False) -> None:
    expected = {number: copy.deepcopy(container.get("provider", {})) for number, container in before.get("containers", {}).items()}
    if allow_queued_reconciliation:
        # A recovery acknowledgement cannot fabricate a clearance. It may
        # release already-persisted source envelopes through the normal inbox
        # path. Independently reconstruct only those authorized field updates.
        queued = {item["id"]: item for item in before.get("feed_queue", [])}
        watermarks = {number: copy.deepcopy(container.get("source_watermarks", {})) for number, container in before.get("containers", {}).items()}
        for received in after.get("feed_inbox", []):
            original = queued.get(received.get("id"))
            if original is None or original != received:
                continue
            body_hash = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            if after.get("feed_processed", {}).get(original["id"]) != body_hash:
                continue
            for record in original["records"]:
                number = record["container_id"]
                for field, value in record["patch"].items():
                    if original["published_min"] < watermarks[number].get(field, 0):
                        continue
                    expected[number][field] = {**(expected[number].get(field) or {}), **copy.deepcopy(value)} if field == "import_deadlines" and isinstance(value, dict) else copy.deepcopy(value)
                    watermarks[number][field] = original["published_min"]
    for number, container in before.get("containers", {}).items():
        updated = after.get("containers", {}).get(number)
        if updated is None or updated.get("provider") != expected[number] or updated.get("site") != container.get("site"):
            raise ApiError(409, "INCIDENT_GUARD_REJECTED", "The proposed incident action would change unsubstantiated evidence. No changes were committed.")
    if before.get("clock_min") != after.get("clock_min") or before.get("completed", []) != after.get("completed", []):
        raise ApiError(409, "INCIDENT_GUARD_REJECTED", "Incident reporting cannot advance time or invent completed handoffs.")


@router.get("/workspaces/{workspace_id}/incidents")
def get_incidents(workspace_id: str, x_workspace_token: str | None = Header(None)):
    with get_database().session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token)
        items = sorted(records(workspace.state).values(), key=lambda item: (item.get("created_at", ""), item["id"]), reverse=True)
        return respond(envelope({"items": [incident_view(item, workspace.state.get("clock_min", 0), workspace.state.get("scale_clock_min"), workspace.state.get("scale_run_id")) for item in items], "catalog": spatial().incident_catalog(), "scopes": spatial().scope_catalog(), "escalation_policy": {"version": "synthetic-escalation-10min", "ownership_acknowledgement_due_minutes": 10, "automatic_external_dispatch": False, "elapsed_clock": "max_of_precision_and_current_scale_context"}}, workspace))


@router.post("/workspaces/{workspace_id}/incidents", status_code=201)
def create_incident(workspace_id: str, body: IncidentCreate, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    request_body = body.model_dump()
    scope = f"{workspace_id}:emergency-incidents:create"
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        replay = retry_receipt(session, scope, idempotency_key, request_body)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Emergency injections require a synthetic simulation workspace.")
        scenario = lookup_scenario(body.scenario_id)
        assessment = spatial().assess_incident(copy.deepcopy(workspace.state), body.scenario_id, body.scope_id, body.severity)
        prepared = workflow_and_proposal(workspace.state, scenario, assessment, body)
        from .scale import scale_incident_assessment
        scale_assessment = scale_incident_assessment(session, workspace, body.scenario_id, body.scope_id, body.severity)
        if scale_assessment["applicable"]:
            prepared["status"] = "active"
            prepared["proposal"]["summary"] = "Apply the recorded phase restrictions in this synthetic scale run. Precision-world resource permissions remain independent; coordinate human-led recovery."
            prepared["workflow"][1]["scale_output"] = scale_assessment
            prepared["workflow"][3]["checks"]["bulk_phase_scope_validated"] = True
            prepared["proposal"]["limitations"].append(scale_assessment["limitation"])
        now = utcnow()
        incident_id, request_id = str(uuid.uuid4()), str(uuid.uuid4())
        incident = {"id": incident_id, "scenario_id": body.scenario_id, "title": scenario.get("name", scenario.get("title", body.scenario_id)), "scope_id": body.scope_id, "severity": body.severity, "note": body.note, "created_at": now.isoformat(), "updated_at": now.isoformat(), "created_at_min": workspace.state.get("clock_min", 0), "impact": assessment, "assessment": assessment, **prepared, "escalation": {"request_id": request_id, "owner_role": prepared["owner_role"], "status": "open", "acknowledged": False, "due_at_min": workspace.state.get("clock_min", 0) + 10, "reason": "An operator must confirm scope, review the proposed response and own the internal follow-up.", "policy": "synthetic-escalation-10min"}, "provenance": {"origin_kind": "synthetic_incident_report", "historical_background": scenario.get("historical_facts", scenario.get("historical_background", [])), "synthetic_parameters": scenario.get("synthetic_parameters"), "physical_execution": False, "external_dispatch": False}}
        incident.update(scale_assessment=scale_assessment, scale_created_at_min=scale_assessment["clock_min"], scale_run_id=scale_assessment["run_id"])
        state = copy.deepcopy(workspace.state)
        current = records(state)
        current[incident_id] = incident
        state["emergency_incidents"] = current
        if incident["effects"]:
            state = effect_engine().apply_incident_effects(state, incident, [item for item in current.values() if item["status"] != "resolved"])
        permission_guard(workspace.state, state)
        state["emergency_incidents"] = current
        event(state, incident, "created", incident["proposal"]["summary"])
        provenance = {"origin_kind": "synthetic_incident_escalation", "incident_id": incident_id, "workspace_mode": workspace.mode, "external_delivery": False, "physical_execution": False, "provider_fact_change": False}
        session.add(CoordinationRequest(id=request_id, workspace_id=workspace.id, status="open", owner_role=prepared["owner_role"], service_kind="emergency_coordination", title=str(incident["title"])[:160], comment=body.note or incident["proposal"]["summary"], container_ids=assessment.get("affected_container_ids", [])[:50], payload={"provenance": provenance, "status_history": [{"status": "open", "comment": "Created by the deterministic incident workflow", "actor": "emergency-coordinator", "at": now.isoformat()}]}, revision=workspace.revision + 1, created_at=now, updated_at=now, resolved_at=None))
        commit_state(session, workspace, state, "emergency_incident.created", {"incident_id": incident_id, "scenario_id": body.scenario_id, "scope_id": body.scope_id, "severity": body.severity, "status": incident["status"], "internal_request_id": request_id, "external_dispatch": False})
        result = envelope({"incident": incident_view(incident, state.get("clock_min", 0), state.get("scale_clock_min"), state.get("scale_run_id")), "workspace": workspace_data(workspace)}, workspace)
        save_receipt(session, scope, idempotency_key, request_body, result, 201)
        return respond(result, 201)


@router.post("/workspaces/{workspace_id}/incidents/{incident_id}/acknowledge")
def acknowledge_incident(workspace_id: str, incident_id: str, body: IncidentAcknowledge, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    request_body = body.model_dump()
    scope = f"{workspace_id}:emergency-incident:{incident_id}:acknowledge"
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        replay = retry_receipt(session, scope, idempotency_key, request_body)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Incident ownership acknowledgement requires its simulation workspace.")
        state = copy.deepcopy(workspace.state)
        incident = records(state).get(incident_id)
        if incident is None:
            raise ApiError(404, "INCIDENT_NOT_FOUND", "This incident is not in the workspace.")
        if incident["status"] == "resolved":
            raise ApiError(409, "INCIDENT_RESOLVED", "This incident is already resolved.")
        now = utcnow()
        incident["acknowledgement"] = {"actor": "workspace-owner", "simulated": True, "note": body.note, "at": now.isoformat(), "at_min": state.get("clock_min", 0)}
        incident["escalation"].update(status="acknowledged", acknowledged=True, acknowledged_at_min=state.get("clock_min", 0))
        incident["updated_at"] = now.isoformat()
        for node in incident["workflow"]:
            if node["stage"] == "escalate":
                node.update(status="acknowledged", summary="Simulated human ownership recorded; operational restrictions and recovery review remain independent.")
        linked = session.get(CoordinationRequest, incident["escalation"]["request_id"])
        if linked is not None and linked.workspace_id == workspace.id:
            linked.status = "in_progress"
            linked.updated_at = now
            linked.revision = workspace.revision + 1
            linked.payload = {**linked.payload, "status_history": [*linked.payload.get("status_history", []), {"status": "in_progress", "actor": "workspace-owner", "comment": body.note or "Simulated human ownership acknowledged", "at": now.isoformat()}]}
        event(state, incident, "acknowledged", "Simulated human ownership acknowledged. No operational restriction was removed.")
        commit_state(session, workspace, state, "emergency_incident.acknowledged", {"incident_id": incident_id, "simulated_human_acknowledgement": True, "external_dispatch": False})
        result = envelope({"incident": incident_view(incident, state.get("clock_min", 0), state.get("scale_clock_min"), state.get("scale_run_id")), "workspace": workspace_data(workspace)}, workspace)
        save_receipt(session, scope, idempotency_key, request_body, result, 200)
        return respond(result)


@router.post("/workspaces/{workspace_id}/incidents/{incident_id}/resolve")
def resolve_incident(workspace_id: str, incident_id: str, body: IncidentResolve, x_workspace_token: str | None = Header(None), if_match: str | None = Header(None), idempotency_key: str | None = Header(None)):
    database = get_database()
    request_body = body.model_dump()
    scope = f"{workspace_id}:emergency-incident:{incident_id}:resolve"
    with database.write_lock, database.session() as session:
        workspace = authorized_workspace(session, workspace_id, x_workspace_token, lock=True)
        replay = retry_receipt(session, scope, idempotency_key, request_body)
        if replay:
            return replay
        check_revision(workspace, if_match)
        if workspace.mode != "SIMULATION":
            raise ApiError(409, "MODE_NOT_ALLOWED", "Incident recovery requires its simulation workspace.")
        if body.acknowledged is not True:
            raise ApiError(422, "ACKNOWLEDGEMENT_REQUIRED", "Explicitly acknowledge the simulated recovery review before proceeding.")
        state = copy.deepcopy(workspace.state)
        current = records(state)
        incident = current.get(incident_id)
        if incident is None:
            raise ApiError(404, "INCIDENT_NOT_FOUND", "This incident is not in the workspace.")
        if incident["status"] != "resolved":
            now = utcnow()
            incident["status"] = "resolved"
            incident["updated_at"] = now.isoformat()
            incident["resolution"] = {"acknowledged": True, "actor": "workspace-owner", "note": body.note, "recovery_evidence_note": body.note, "verification_status": "operator_reported_simulation_only", "at": now.isoformat(), "at_min": state.get("clock_min", 0), "external_authority": False}
            incident["escalation"]["status"] = "resolved"
            state["emergency_incidents"] = current
            if incident["effects"]:
                state = effect_engine().resolve_incident_effects(state, incident, [item for item in current.values() if item["status"] != "resolved"])
            permission_guard(workspace.state, state, allow_queued_reconciliation=True)
            state["emergency_incidents"] = current
            event(state, incident, "resolved", "Human acknowledged this synthetic recovery. Other active restrictions and provider facts remain independent.")
            request = session.get(CoordinationRequest, incident.get("escalation", {}).get("request_id"))
            if request is not None and request.workspace_id == workspace.id:
                request.status = "resolved"
                request.resolved_at = now
                request.updated_at = now
                request.revision = workspace.revision + 1
                request.payload = {**request.payload, "status_history": [*request.payload.get("status_history", []), {"status": "resolved", "comment": body.note or "Incident recovery acknowledged", "actor": "workspace-owner", "at": now.isoformat()}]}
            commit_state(session, workspace, state, "emergency_incident.resolved", {"incident_id": incident_id, "human_acknowledged": True, "external_authority": False})
        result = envelope({"incident": incident_view(incident, state.get("clock_min", 0), state.get("scale_clock_min"), state.get("scale_run_id")), "workspace": workspace_data(workspace)}, workspace)
        save_receipt(session, scope, idempotency_key, request_body, result, 200)
        return respond(result)
