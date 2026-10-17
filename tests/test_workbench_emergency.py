"""End-to-end incident workflow checks using real persisted synthetic worlds."""
from __future__ import annotations

import copy
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gate_triage.workbench.api import install_handlers, router as api_router
from gate_triage.workbench.db import CoordinationRequest, Workspace, configure_database, get_database
from gate_triage.workbench.emergency import router as emergency_router
from gate_triage.workbench.spatial import router as spatial_router
from gate_triage.workbench.worker import stop_worker


@pytest.fixture
def client(tmp_path):
    stop_worker()
    configure_database(f"sqlite:///{tmp_path / 'emergency.db'}")
    app = FastAPI()
    install_handlers(app)
    app.include_router(api_router)
    app.include_router(spatial_router)
    app.include_router(emergency_router)
    with TestClient(app) as client:
        yield client
    stop_worker()


def workspace(client, mode="SIMULATION"):
    response = client.post("/api/v1/workspaces", json={"name": "Emergency integration", "mode": mode, "scenario_id": "normal_operations", "seed": 17}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def prefix(w):
    return f"/api/v1/workspaces/{w['id']}"


def auth(w, revision=None, key=None):
    return {"X-Workspace-Token": w["token"], "If-Match": str(w["revision"] if revision is None else revision), "Idempotency-Key": key or str(uuid.uuid4())}


def current(client, w):
    data = client.get(prefix(w), headers=auth(w)).json()["data"]
    return {**data, "token": w["token"]}


def state(w):
    with get_database().session() as session:
        return copy.deepcopy(session.get(Workspace, w["id"]).state)


def create(client, w, scenario="battery_access_2024", scope="zone-gate-east", severity="critical", key=None):
    return client.post(prefix(w) + "/incidents", json={"scenario_id": scenario, "scope_id": scope, "severity": severity, "note": "Explicitly synthetic operator report"}, headers=auth(w, key=key))


def resolve(client, w, incident, acknowledged=True, key=None):
    return client.post(prefix(w) + f"/incidents/{incident['id']}/resolve", json={"acknowledged": acknowledged, "note": "Operator reviewed this synthetic recovery"}, headers=auth(w, key=key))


def capacities(value):
    return {key: resource["available_capacity"] for key, resource in value["resources"].items() if resource["kind"] == "gate_lane"}


def test_incident_runs_real_workflow_and_records_internal_escalation(client):
    w = workspace(client)
    before = state(w)
    response = create(client, w)
    assert response.status_code == 201, response.text
    incident = response.json()["data"]["incident"]
    assert incident["status"] == "active"
    assert [node["stage"] for node in incident["workflow"]] == ["observe", "impact", "retrieve", "validate", "escalate"]
    assert incident["orchestrator"]["llm_used"] is False
    assert incident["sources"]
    assert incident["assessment"]["scope_id"] == "zone-gate-east"
    assert incident["escalation"]["status"] == "open"
    after = state(w)
    assert capacities(after)["east-lane-1"] == capacities(after)["east-lane-2"] == 0
    assert capacities(after)["west-lane-1"] == capacities(before)["west-lane-1"]
    assert capacities(after)["west-lane-2"] == capacities(before)["west-lane-2"]
    assert after["clock_min"] == before["clock_min"]
    assert after["completed"] == before["completed"]
    assert all(after["containers"][number]["provider"] == container["provider"] for number, container in before["containers"].items())
    with get_database().session() as session:
        request = session.get(CoordinationRequest, incident["escalation"]["request_id"])
        assert request.status == "open"
        assert request.payload["provenance"]["external_delivery"] is False
        assert request.payload["provenance"]["incident_id"] == incident["id"]
    mapped = client.get(prefix(w) + "/map", headers=auth(w)).json()["data"]
    east = next(zone for zone in mapped["zones"] if zone["properties"]["id"] == "zone-gate-east")
    assert east["properties"]["severity"] == "critical"
    assert east["properties"]["metrics"]["capacity_available"] == 0


def test_incident_retry_replays_before_version_and_creates_one_request(client):
    w = workspace(client)
    key = str(uuid.uuid4())
    first = create(client, w, key=key)
    assert first.status_code == 201
    repeated = create(client, w, key=key)
    assert repeated.status_code == 201
    assert repeated.json() == first.json()
    listed = client.get(prefix(w) + "/incidents", headers=auth(w)).json()["data"]
    assert len(listed["items"]) == 1
    assert len(listed["catalog"]) >= 6
    with get_database().session() as session:
        assert len(list(session.scalars(select(CoordinationRequest)))) == 1


def test_resolving_one_layer_preserves_another_incident_and_source_holds(client):
    w = workspace(client)
    before = state(w)
    first = create(client, w).json()["data"]["incident"]
    second = create(client, current(client, w), scenario="exit_congestion", severity="restricted").json()["data"]["incident"]
    response = resolve(client, current(client, w), first)
    assert response.status_code == 200, response.text
    middle = state(w)
    assert capacities(middle)["east-lane-1"] == 1
    assert capacities(middle)["east-lane-2"] == 0
    response = resolve(client, current(client, w), second)
    assert response.status_code == 200, response.text
    after = state(w)
    assert capacities(after) == capacities(before)
    assert all(after["containers"][number]["provider"] == container["provider"] for number, container in before["containers"].items())


def test_manual_closure_before_incident_is_not_removed_on_recovery(client):
    w = workspace(client)
    changed = client.post(prefix(w) + "/commands", json={"command": "incident", "status": "closed", "gate": "east"}, headers=auth(w))
    assert changed.status_code == 200
    incident = create(client, current(client, w)).json()["data"]["incident"]
    response = resolve(client, current(client, w), incident)
    assert response.status_code == 200, response.text
    assert capacities(state(w))["east-lane-1"] == capacities(state(w))["east-lane-2"] == 0


@pytest.mark.parametrize("scope,severity", [("terminal-apm", "critical"), ("unknown-area", "critical"), ("zone-gate-east", "watch"), ("zone-yard", "critical")])
def test_unmodeled_unknown_warning_or_unsupported_scope_only_monitors(client, scope, severity):
    w = workspace(client)
    before = capacities(state(w))
    response = create(client, w, scope=scope, severity=severity)
    assert response.status_code == 201, response.text
    incident = response.json()["data"]["incident"]
    assert incident["status"] == "monitoring"
    assert incident["effects"] == []
    assert capacities(state(w)) == before
    assert incident["proposal"]["requires_human"]
    assert incident["workflow"][-1]["status"] == "needs_human"


def test_recovery_requires_real_boolean_ack_and_scope_isolation(client):
    w, other = workspace(client), workspace(client)
    incident = create(client, w).json()["data"]["incident"]
    latest = current(client, w)
    denied = resolve(client, latest, incident, acknowledged=False)
    assert denied.status_code == 422
    nonboolean = resolve(client, latest, incident, acknowledged="true")
    assert nonboolean.status_code == 422
    cross = resolve(client, other, incident)
    assert cross.status_code == 404
    assert client.get(prefix(w) + "/incidents", headers=auth(other)).status_code == 404
    key = str(uuid.uuid4())
    first = resolve(client, latest, incident, key=key)
    assert first.status_code == 200
    repeated = resolve(client, latest, incident, key=key)
    assert repeated.status_code == 200
    assert repeated.json() == first.json()


def test_incident_persists_across_database_connection_restart(client):
    w = workspace(client)
    incident = create(client, w).json()["data"]["incident"]
    configure_database(get_database().url)
    data = client.get(prefix(w) + "/incidents", headers=auth(w)).json()["data"]
    assert data["items"][0]["id"] == incident["id"]
    assert capacities(state(w))["east-lane-1"] == 0


def test_replay_cannot_inject_operational_incident(client):
    w = workspace(client, mode="REPLAY_T49")
    assert create(client, w).status_code == 409


def test_cyber_layers_and_manual_outage_are_independent(client):
    w = workspace(client)
    first = create(client, w, scenario="cyber_data_2017", scope="terminal-fenix", severity="restricted").json()["data"]["incident"]
    second = create(client, current(client, w), scenario="cyber_data_2017", scope="terminal-fenix", severity="restricted").json()["data"]["incident"]
    assert state(w)["provider_online"] is False
    assert resolve(client, current(client, w), first).status_code == 200
    assert state(w)["provider_online"] is False
    response = resolve(client, current(client, w), second)
    assert response.status_code == 200, response.text
    assert state(w)["provider_online"] is True
    changed = client.post(prefix(w) + "/commands", json={"command": "feed", "action": "delay"}, headers=auth(current(client, w)))
    assert changed.status_code == 200
    third = create(client, current(client, w), scenario="cyber_data_2017", scope="terminal-fenix").json()["data"]["incident"]
    assert resolve(client, current(client, w), third).status_code == 200
    assert state(w)["provider_online"] is False


def test_unsubstantiated_tool_output_is_rolled_back(client, monkeypatch):
    import gate_triage.workbench.spatial_simulation as effect_engine
    def unsafe(state, incident, active):
        after = copy.deepcopy(state)
        after["containers"][after["hero_id"]]["provider"]["holds_at_pod_terminal"] = []
        return after
    monkeypatch.setattr(effect_engine, "apply_incident_effects", unsafe)
    w = workspace(client)
    response = create(client, w)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INCIDENT_GUARD_REJECTED"
    assert state(w).get("emergency_incidents", {}) == {}
    with get_database().session() as session:
        assert session.get(Workspace, w["id"]).revision == 1
        assert not list(session.scalars(select(CoordinationRequest)))


def test_channel_annotation_does_not_close_gates_or_invent_handoffs(client):
    w = workspace(client)
    before = state(w)
    response = create(client, w, scenario="channel_obstruction_2024", scope="corridor-main-channel")
    assert response.status_code == 201, response.text
    incident = response.json()["data"]["incident"]
    after = state(w)
    assert capacities(after) == capacities(before)
    assert after["completed"] == before["completed"]
    assert "Baltimore" in incident["provenance"]["historical_background"]
    assert incident["assessment"]["affected_container_ids"] == []


def test_ownership_acknowledgement_is_separate_from_recovery_and_retry_safe(client):
    w = workspace(client)
    incident = create(client, w).json()["data"]["incident"]
    latest = current(client, w)
    before = state(w)
    key = str(uuid.uuid4())
    url = prefix(w) + f"/incidents/{incident['id']}/acknowledge"
    body = {"note": "Simulated operator owns this review"}
    response = client.post(url, json=body, headers=auth(latest, key=key))
    assert response.status_code == 200, response.text
    assert response.json()["data"]["incident"]["status"] == "active"
    assert response.json()["data"]["incident"]["escalation"]["status"] == "acknowledged"
    repeated = client.post(url, json=body, headers=auth(latest, key=key))
    assert repeated.status_code == 200
    assert repeated.json() == response.json()
    assert capacities(state(w)) == capacities(before)
    with get_database().session() as session:
        assert session.get(CoordinationRequest, incident["escalation"]["request_id"]).status == "in_progress"


def test_unacknowledged_escalation_is_derived_from_virtual_clock(client):
    w = workspace(client)
    incident = create(client, w, severity="restricted").json()["data"]["incident"]
    assert incident["escalation"]["due_at_min"] == 10
    assert incident["escalation"]["overdue"] is False
    advanced = client.post(prefix(w) + "/commands", json={"command": "advance", "minutes": 10}, headers=auth(current(client, w)))
    assert advanced.status_code == 200, advanced.text
    listed = client.get(prefix(w) + "/incidents", headers=auth(w)).json()["data"]["items"][0]
    assert listed["escalation"]["overdue"] is True
    assert listed["escalation"]["effective_severity"] == "critical"
    assert listed["escalation"]["automatic_external_dispatch"] is False
    acknowledged = client.post(prefix(w) + f"/incidents/{incident['id']}/acknowledge", json={"note": "Owned within rehearsal"}, headers=auth(current(client, w)))
    assert acknowledged.status_code == 200
    assert acknowledged.json()["data"]["incident"]["escalation"]["overdue"] is False
    assert state(w)["emergency_incidents"][incident["id"]]["status"] == "active"


def test_resolution_requires_recovery_evidence_note(client):
    w = workspace(client)
    incident = create(client, w).json()["data"]["incident"]
    response = client.post(prefix(w) + f"/incidents/{incident['id']}/resolve", json={"acknowledged": True, "note": "   "}, headers=auth(current(client, w)))
    assert response.status_code == 422
    assert state(w)["emergency_incidents"][incident["id"]]["status"] == "active"


def test_recovery_can_reconcile_already_queued_source_evidence(client):
    from gate_triage.workbench.engine import _receive_provider_envelope
    w = workspace(client)
    incident = create(client, w, scenario="cyber_data_2017", scope="terminal-fenix").json()["data"]["incident"]
    with get_database().session() as session:
        row = session.get(Workspace, w["id"])
        before = copy.deepcopy(row.state)
        envelope = {"id": "queued-authority-source-report", "published_min": before["clock_min"], "generated_at_min": before["clock_min"], "records": [{"container_id": before["hero_id"], "patch": {"holds_at_pod_terminal": [], "availability_known": True, "available_for_pickup": True}}]}
        _receive_provider_envelope(before, envelope)
        assert before["containers"][before["hero_id"]]["provider"]["holds_at_pod_terminal"]
        row.state = before
    response = resolve(client, current(client, w), incident)
    assert response.status_code == 200, response.text
    after = state(w)
    assert after["containers"][after["hero_id"]]["provider"]["holds_at_pod_terminal"] == []
    assert "queued-authority-source-report" in after["feed_processed"]
