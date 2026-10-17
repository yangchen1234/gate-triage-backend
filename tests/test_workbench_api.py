"""Integration tests for durable workspace isolation and execution semantics."""
from __future__ import annotations

import hashlib
import hmac
import json
import copy
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from gate_triage.workbench.api import install_handlers, router
from gate_triage.workbench.connector import Terminal49Connector, verify_webhook
from gate_triage.workbench.db import AuditEvent, CoordinationRequest, CoordinationTask, Job, ProviderInbox, Workspace, configure_database, get_database, utcnow
from gate_triage.workbench.worker import start_worker, stop_worker


@pytest.fixture
def client(tmp_path):
    stop_worker()
    configure_database(f"sqlite:///{tmp_path / 'workbench.db'}")
    app = FastAPI()
    install_handlers(app)
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client
    stop_worker()


def create(client, **overrides):
    response = client.post("/api/v1/workspaces", json={"name": "Test rehearsal", "mode": "SIMULATION", "scenario_id": "battery_truck_access_2024", "seed": 17, **overrides}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def headers(workspace, *, revision=None, key=None):
    return {"X-Workspace-Token": workspace["token"], "If-Match": str(revision if revision is not None else workspace["revision"]), "Idempotency-Key": key or str(uuid.uuid4())}


def test_workspace_creation_and_real_database_projection(client):
    workspace = create(client)
    assert len(workspace["snapshot"]["containers"]) == 100
    assert workspace["mode"] == "SIMULATION"
    assert not workspace["playback"]["playing"]
    with get_database().session() as session:
        assert session.get(Workspace, workspace["id"]).revision == 1
        assert len(list(session.scalars(select(CoordinationTask).where(CoordinationTask.workspace_id == workspace["id"])))) > 100
    response = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers(workspace))
    assert response.headers["etag"] == '"1"'
    assert response.json()["meta"]["workspace_id"] == workspace["id"]
    assert "token" not in response.json()["data"]


def test_workspace_capability_is_required_and_scoped(client):
    one, two = create(client), create(client)
    assert client.get(f"/api/v1/workspaces/{one['id']}").status_code == 404
    assert client.get(f"/api/v1/workspaces/{one['id']}", headers={"X-Workspace-Token": two["token"]}).status_code == 404
    forged = {**headers(one), "X-Role": "admin", "X-Workspace-Token": "wrong-token"}
    assert client.get(f"/api/v1/workspaces/{one['id']}/tasks", headers=forged).status_code == 404


def test_idempotent_mutation_replays_before_revision_check(client):
    workspace = create(client)
    key = str(uuid.uuid4())
    url = f"/api/v1/workspaces/{workspace['id']}/commands"
    command = {"command": "pause"}
    first = client.post(url, json=command, headers=headers(workspace, key=key))
    assert first.status_code == 200, first.text
    assert first.json()["meta"]["revision"] == 2
    replay = client.post(url, json=command, headers=headers(workspace, key=key))
    assert replay.status_code == 200
    assert replay.json() == first.json()
    conflict = client.post(url, json={"command": "advance", "minutes": 1}, headers=headers(workspace, key=key))
    assert conflict.status_code == 409
    stale = client.post(url, json=command, headers=headers(workspace))
    assert stale.status_code == 412
    missing = client.post(url, json=command, headers={"X-Workspace-Token": workspace["token"], "Idempotency-Key": str(uuid.uuid4())})
    assert missing.status_code == 428


def test_creation_retry_returns_same_workspace_and_token(client):
    key = str(uuid.uuid4())
    body = {"scenario_id": "normal_operations", "mode": "SIMULATION", "name": "Same request", "seed": 17}
    one = client.post("/api/v1/workspaces", json=body, headers={"Idempotency-Key": key})
    two = client.post("/api/v1/workspaces", json=body, headers={"Idempotency-Key": key})
    assert one.status_code == two.status_code == 201
    assert one.json() == two.json()
    changed = client.post("/api/v1/workspaces", json={**body, "seed": 18}, headers={"Idempotency-Key": key})
    assert changed.status_code == 409


def test_coordinator_task_cannot_write_external_clearance(client):
    workspace = create(client)
    url = f"/api/v1/workspaces/{workspace['id']}/task-events"
    tasks = workspace["snapshot"]["tasks"]
    task = next(task for task in tasks if task["kind"] == "coordinate_hold")
    invalid = client.post(url, json={"task_id": task["id"], "action": "record_result", "clear_customs": True}, headers=headers(workspace))
    assert invalid.status_code == 422
    valid = client.post(url, json={"task_id": task["id"], "action": "record_contact", "note": "Waiting for a newer source report"}, headers=headers(workspace))
    assert valid.status_code == 200, valid.text
    after = valid.json()["data"]["snapshot"]
    same = next(t for t in after["tasks"] if t["id"] == task["id"])
    assert same["status"] != "resolved"
    container = next(c for c in after["containers"] if c["number"] == task["container_id"])
    assert container["departure"]["status"] != "allowed"


def test_state_and_audit_survive_connection_restart(client):
    workspace = create(client)
    changed = client.post(f"/api/v1/workspaces/{workspace['id']}/commands", json={"command": "pause"}, headers=headers(workspace))
    assert changed.status_code == 200
    url = get_database().url
    configure_database(url)
    response = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers(workspace))
    assert response.status_code == 200
    assert response.json()["meta"]["revision"] == 2
    timeline = client.get(f"/api/v1/workspaces/{workspace['id']}/timeline", headers=headers(workspace)).json()["data"]["items"]
    assert {event["action"] for event in timeline} >= {"workspace.created", "command.pause"}


def test_durable_job_runs_after_worker_starts_and_is_scoped(client, monkeypatch):
    from gate_triage.workbench import engine
    monkeypatch.setattr(engine, "plan", lambda state, profile="throughput", strategy="optimized": {"solver_status": "FEASIBLE", "operations": [], "profile": profile}, raising=False)
    workspace = create(client)
    url = f"/api/v1/workspaces/{workspace['id']}"
    response = client.post(url + "/plan-jobs", json={"profile": "throughput", "strategy": "optimized"}, headers=headers(workspace))
    assert response.status_code == 202, response.text
    job = response.json()["data"]
    assert job["status"] == "queued"
    start_worker()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(url + "/jobs/" + job["id"], headers=headers(workspace)).json()["data"]
        if result["status"] == "succeeded":
            break
        time.sleep(0.05)
    assert result["status"] == "succeeded", result
    assert result["result"]["input_revision"] == 1
    other = create(client)
    cross = client.get(f"/api/v1/workspaces/{other['id']}/jobs/{job['id']}", headers=headers(other))
    assert cross.status_code == 404


def test_playback_is_persisted_server_control_and_pauses_on_restart(client):
    workspace = create(client)
    response = client.post(f"/api/v1/workspaces/{workspace['id']}/playback", json={"playing": True, "speed": 2, "tick_minutes": 1}, headers=headers(workspace))
    assert response.status_code == 200
    assert response.json()["data"]["playback"]["playing"]
    start_worker()
    # Explicit restart recovery pauses existing playback rather than silently
    # simulating the time for which this process was unavailable.
    latest = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers(workspace)).json()["data"]
    assert latest["playback"]["paused_reason"] == "server_restarted"
    latest["token"] = workspace["token"]
    resumed = client.post(f"/api/v1/workspaces/{workspace['id']}/playback", json={"playing": True, "speed": 2, "tick_minutes": 1}, headers=headers(latest))
    assert resumed.status_code == 200
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers(workspace)).json()["data"]
        if current["snapshot"]["clock_min"] > 0:
            break
        time.sleep(0.1)
    assert current["snapshot"]["clock_min"] > 0
    assert current["revision"] > resumed.json()["data"]["revision"]


def test_live_mode_is_explicitly_unavailable(client):
    response = client.post("/api/v1/workspaces", json={"mode": "LIVE_T49"}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SOURCE_NOT_CONFIGURED"


def test_connector_preserves_unknown_and_distinguishes_provider_weight():
    normalized = Terminal49Connector.normalize_container({"id": "journey", "attributes": {"number": "TEST0000001", "holds_at_pod_terminal": None, "weight_in_lbs": 1200, "equipment_type": "reefer", "new_provider_field": "retained"}})
    assert normalized["attributes"]["holds_at_pod_terminal"] is None
    assert "availability_known" not in normalized["attributes"]
    assert normalized["unknown_attributes"]["new_provider_field"] == "retained"
    assert normalized["limitations"]["weight_is_not_independent_scale"]
    body = b'{"data":{"id":"notification-1"}}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_webhook(body, signature, "secret")
    assert not verify_webhook(body + b" ", signature, "secret")


def test_signed_webhook_deduplication_and_conflicting_id_quarantine(client, monkeypatch):
    monkeypatch.setenv("T49_WEBHOOK_SECRET", "test-only-secret")
    monkeypatch.setenv("T49_WEBHOOK_CONNECTION", "test-connection")
    url = "/api/v1/webhooks/terminal49/test-connection"
    body = json.dumps({"data": {"id": "notification-1", "type": "webhook_notification", "attributes": {"event": "container.updated"}}}).encode()
    def deliver(payload, signature=None):
        signature = signature or hmac.new(b"test-only-secret", payload, hashlib.sha256).hexdigest()
        return client.post(url, content=payload, headers={"Content-Type": "application/json", "X-T49-Webhook-Signature": signature})
    assert deliver(body, "wrong-signature").status_code == 401
    first = deliver(body)
    assert first.status_code == 202
    assert first.json()["data"]["status"] == "stored_unprojected"
    second = deliver(body)
    assert second.status_code == 202
    assert second.json()["data"]["duplicate"]
    altered = body.replace(b"container.updated", b"container.replaced")
    conflict = deliver(altered)
    assert conflict.status_code == 409
    with get_database().session() as session:
        rows = list(session.scalars(select(ProviderInbox)))
        assert len(rows) == 1
        assert rows[0].status == "quarantined_id_conflict"
        assert rows[0].payload["data"]["attributes"]["event"] == "container.updated"


def test_concurrent_writers_cannot_overwrite_a_new_revision(client):
    workspace = create(client)
    url = f"/api/v1/workspaces/{workspace['id']}/commands"
    def mutate(action):
        return client.post(url, json={"command": "feed", "action": action}, headers=headers(workspace))
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(mutate, ["delay", "recover"]))
    assert sorted(response.status_code for response in responses) == [200, 412]
    fresh = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers(workspace)).json()
    assert fresh["meta"]["revision"] == 2
    with get_database().session() as session:
        changes = list(session.scalars(select(AuditEvent).where(AuditEvent.workspace_id == workspace["id"], AuditEvent.action == "command.feed")))
        assert len(changes) == 1


def test_replay_cannot_use_physical_commands_or_resource_solver(client):
    workspace = create(client, mode="REPLAY_T49")
    for command in ({"command": "incident", "status": "closed"}, {"command": "evidence", "container_id": workspace["snapshot"]["hero_id"], "kind": "customs", "values": {"holds": []}}):
        response = client.post(f"/api/v1/workspaces/{workspace['id']}/commands", json=command, headers=headers(workspace))
        assert response.status_code == 409
    job = client.post(f"/api/v1/workspaces/{workspace['id']}/plan-jobs", json={}, headers=headers(workspace))
    assert job.status_code == 409


def test_new_plan_job_pauses_playback_before_capturing_input(client):
    workspace = create(client)
    started = client.post(f"/api/v1/workspaces/{workspace['id']}/playback", json={"playing": True, "speed": 1}, headers=headers(workspace))
    current = started.json()["data"]
    current["token"] = workspace["token"]
    queued = client.post(f"/api/v1/workspaces/{workspace['id']}/plan-jobs", json={}, headers=headers(current))
    assert queued.status_code == 202
    fresh = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers(workspace)).json()["data"]
    assert not fresh["playback"]["playing"]
    assert fresh["playback"]["paused_reason"] == "computation_requested"
    assert queued.json()["data"]["input_revision"] == fresh["revision"]


def test_interrupted_durable_job_is_recovered_from_expired_lease(client, monkeypatch):
    from gate_triage.workbench import engine
    monkeypatch.setattr(engine, "plan", lambda state, profile="throughput", strategy="optimized": {"solver_status": "FEASIBLE", "operations": []}, raising=False)
    workspace = create(client)
    prefix = f"/api/v1/workspaces/{workspace['id']}"
    queued = client.post(prefix + "/plan-jobs", json={}, headers=headers(workspace)).json()["data"]
    with get_database().session() as session:
        interrupted = session.get(Job, queued["id"])
        interrupted.status = "running"
        interrupted.lease_owner = "terminated-worker"
        interrupted.lease_until = utcnow() - timedelta(seconds=10)
        interrupted.attempts = 1
    start_worker()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(prefix + "/jobs/" + queued["id"], headers=headers(workspace)).json()["data"]
        if result["status"] == "succeeded":
            break
        time.sleep(.05)
    assert result["status"] == "succeeded"
    assert result["attempts"] == 2


def test_plan_is_stale_after_new_facts_even_at_same_clock(client, monkeypatch):
    from gate_triage.workbench import engine
    monkeypatch.setattr(engine, "plan", lambda state, profile="throughput", strategy="optimized": {"solver_status": "FEASIBLE", "input_clock_min": state["clock_min"], "operations": []}, raising=False)
    workspace = create(client)
    prefix = f"/api/v1/workspaces/{workspace['id']}"
    queued = client.post(prefix + "/plan-jobs", json={}, headers=headers(workspace)).json()["data"]
    start_worker()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(prefix + "/jobs/" + queued["id"], headers=headers(workspace)).json()["data"]
        if result["status"] == "succeeded":
            break
        time.sleep(.05)
    changed = client.post(prefix + "/commands", json={"command": "feed", "action": "delay"}, headers=headers(workspace))
    assert changed.status_code == 200
    assert changed.json()["data"]["snapshot"]["clock_min"] == 0
    fresh = changed.json()["data"]
    fresh["token"] = workspace["token"]
    stale = client.post(prefix + "/commands", json={"command": "select_plan", "plan_id": queued["id"]}, headers=headers(fresh))
    assert stale.status_code == 412
    assert stale.json()["error"]["code"] == "PLAN_STALE"


def test_real_recovery_plan_can_be_selected_and_retried(client):
    workspace = create(client)
    prefix = f"/api/v1/workspaces/{workspace['id']}"
    queued = client.post(prefix + "/plan-jobs", json={"profile": "recovery", "strategy": "optimized"}, headers=headers(workspace))
    assert queued.status_code == 202, queued.text
    job = queued.json()["data"]
    start_worker()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = client.get(prefix + "/jobs/" + job["id"], headers=headers(workspace)).json()["data"]
        if result["status"] == "succeeded":
            break
        time.sleep(.05)
    assert result["status"] == "succeeded", result
    selection = {"plan_id": job["id"], "input_revision": job["input_revision"]}
    url = prefix + f"/simulation-runs/{workspace['id']}/plan-selections"
    key = str(uuid.uuid4())
    selected = client.post(url, json=selection, headers=headers(workspace, key=key))
    assert selected.status_code == 200, selected.text
    assert selected.json()["data"]["snapshot"]["plan"]["profile"] == "recovery"
    assert selected.json()["data"]["snapshot"]["clock_min"] == 0
    replay = client.post(url, json=selection, headers=headers(workspace, key=key))
    assert replay.status_code == 200
    assert replay.json() == selected.json()


def test_coordination_request_retries_normalizes_ids_and_persists(client):
    workspace = create(client)
    container = workspace["snapshot"]["containers"][0]
    body = {"title": "Check readiness before dispatch", "owner_role": "terminal_operations", "service_kind": "readiness_review", "comment": "Internal rehearsal handoff", "container_ids": [container["id"], container["number"]]}
    url = f"/api/v1/workspaces/{workspace['id']}/requests"
    key = str(uuid.uuid4())
    with get_database().session() as session:
        original_state = copy.deepcopy(session.get(Workspace, workspace["id"]).state)
    response = client.post(url, json=body, headers=headers(workspace, key=key))
    assert response.status_code == 201, response.text
    request = response.json()["data"]
    assert request["status"] == "open"
    assert request["container_ids"] == [container["number"]]
    assert request["provenance"]["external_delivery"] is False
    assert request["provenance"]["provider_fact_change"] is False
    assert response.json()["meta"]["revision"] == 2
    retried = client.post(url, json=body, headers=headers(workspace, key=key))
    assert retried.status_code == 201
    assert retried.json() == response.json()
    conflicting = client.post(url, json={**body, "comment": "A different request"}, headers=headers(workspace, key=key))
    assert conflicting.status_code == 409
    database_url = get_database().url
    configure_database(database_url)
    listed = client.get(url, headers=headers(workspace)).json()["data"]
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == request["id"]
    with get_database().session() as session:
        assert session.get(CoordinationRequest, request["id"]).comment == body["comment"]
        assert session.get(Workspace, workspace["id"]).state == original_state


def test_coordination_request_status_is_scoped_and_never_resolves_provider_facts(client):
    workspace, other = create(client), create(client)
    url = f"/api/v1/workspaces/{workspace['id']}/requests"
    hero = next(c for c in workspace["snapshot"]["containers"] if c["number"] == workspace["snapshot"]["hero_id"])
    body = {"title": "Coordinate reported customs hold", "owner_role": "customs_broker", "service_kind": "hold_coordination", "comment": "Waiting for source confirmation", "container_ids": [hero["number"]]}
    created = client.post(url, json=body, headers=headers(workspace))
    assert created.status_code == 201
    row = created.json()["data"]
    fresh = {**workspace, "revision": 2}
    patch = {"status": "resolved", "comment": "Internal follow-up completed; source status remains independent"}
    key = str(uuid.uuid4())
    updated = client.patch(url + "/" + row["id"], json=patch, headers=headers(fresh, key=key))
    assert updated.status_code == 200
    assert updated.json()["data"]["resolved_at"] is not None
    assert len(updated.json()["data"]["status_history"]) == 2
    retried = client.patch(url + "/" + row["id"], json=patch, headers=headers(fresh, key=key))
    assert retried.status_code == 200
    assert retried.json() == updated.json()
    cross = client.patch(f"/api/v1/workspaces/{other['id']}/requests/{row['id']}", json={"status": "resolved"}, headers=headers(other))
    assert cross.status_code == 404
    assert client.get(url, headers=headers(other)).status_code == 404
    assert client.get(f"/api/v1/workspaces/{other['id']}/requests", headers=headers(other)).json()["data"]["items"] == []
    current = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers(workspace)).json()["data"]["snapshot"]
    hero_after = next(c for c in current["containers"] if c["number"] == hero["number"])
    assert hero_after["departure"] == hero["departure"]
    assert hero_after["pickup_state"] == hero["pickup_state"]
    assert hero_after["departure"]["status"] != "allowed"


def test_coordination_requests_reject_unknown_containers_quota_and_fact_patch(client):
    workspace = create(client)
    url = f"/api/v1/workspaces/{workspace['id']}/requests"
    body = {"title": "Review", "owner_role": "terminal_operations", "service_kind": "general", "comment": "", "container_ids": ["NOT-IN-THIS-WORKSPACE"]}
    rejected = client.post(url, json=body, headers=headers(workspace))
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "CONTAINER_NOT_IN_WORKSPACE"
    too_many = client.post(url, json={**body, "container_ids": [workspace["snapshot"]["containers"][0]["number"]] * 51}, headers=headers(workspace))
    assert too_many.status_code == 422
    created = client.post(url, json={**body, "container_ids": []}, headers=headers(workspace))
    assert created.status_code == 201
    row = created.json()["data"]
    forbidden = client.patch(url + "/" + row["id"], json={"status": "resolved", "clear_customs": True}, headers=headers(workspace, revision=2))
    assert forbidden.status_code == 422
    stale = client.patch(url + "/" + row["id"], json={"status": "in_progress"}, headers=headers(workspace))
    assert stale.status_code == 412
