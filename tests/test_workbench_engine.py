"""Meaningful operational invariants and closed-loop simulation controls."""
import copy
import json

import pytest

from gate_triage.workbench.engine import (apply_command, create_state, experiment,
                                          plan, scenario_catalog, snapshot)
from gate_triage.workbench.scheduler import validate_plan


def hero(s):
    return next(c for c in snapshot(s)["containers"] if c["container_id"] == s["hero_id"])


def test_reference_fixtures_and_json_persistence_contract():
    for scenario in scenario_catalog():
        state = create_state(scenario["id"])
        restored = json.loads(json.dumps(state))
        snap = snapshot(restored)
        assert len(snap["containers"]) == 100
        assert snap["plan"]["validation"]["valid"]
        assert snap["overview"]["completed_handoffs"] == 0
        assert snap["feed"]["events_received"] == 100


def test_commands_are_copy_safe_and_weight_resolution_keeps_other_blockers():
    initial = create_state("normal_operations")
    before = json.dumps(initial, sort_keys=True)
    result = apply_command(initial, {"command": "evidence", "container_id": initial["hero_id"], "kind": "weight", "values": {"declared_status": "laden", "declared_kg": 16100, "measured_kg": 16100}})
    assert json.dumps(initial, sort_keys=True) == before
    row = hero(result)
    assert next(t for t in row["tasks"] if t["kind"] == "weight_check")["status"] == "resolved"
    assert row["departure"]["status"] == "blocked"
    assert any("hold" in r for r in row["departure"]["reasons"])
    assert any("Reefer" in r for r in row["departure"]["reasons"])


def test_acknowledging_coordination_never_clears_source_hold():
    state = create_state("normal_operations")
    task = next(t for t in hero(state)["tasks"] if t["kind"] == "coordinate_hold")
    state = apply_command(state, {"command": "task", "task_id": task["id"], "status": "acknowledged"})
    assert any("hold" in r for r in hero(state)["departure"]["reasons"])
    with pytest.raises(ValueError, match="resolution requires"):
        apply_command(state, {"command": "task", "task_id": task["id"], "status": "resolved"})
    with pytest.raises(ValueError):
        apply_command(state, {"command": "evidence", "container_id": state["hero_id"], "kind": "customs", "values": {"clear_customs": True}})


def test_scoped_incident_and_partial_recovery_do_not_close_west_or_clear_holds():
    state = create_state("normal_operations")
    state = apply_command(state, {"command": "incident", "status": "closed"})
    resources = snapshot(state)["resources"]
    assert sum(r["available_capacity"] for r in resources if r["gate"] == "East") == 0
    assert sum(r["available_capacity"] for r in resources if r["gate"] == "West") == 2
    state = apply_command(state, {"command": "incident", "status": "restricted"})
    assert sum(r["available_capacity"] for r in snapshot(state)["resources"] if r["gate"] == "East") == 1
    state = apply_command(state, {"command": "incident", "status": "open"})
    assert any("hold" in r for r in hero(state)["departure"]["reasons"])


def test_weather_warning_is_not_a_closure():
    state = apply_command(create_state("weather_warning_no_closure_2023"), {"command": "advance", "minutes": 25, "strategy": "fifo"})
    assert snapshot(state)["overview"]["lanes_open"] == 4
    assert any(t["type"] == "warning.received" for t in state["timeline"])


def test_delayed_and_duplicate_evidence_never_overwrite_newer_hold():
    state = apply_command(create_state("terminal_data_disruption_2017"), {"command": "advance", "minutes": 75, "strategy": "fifo"})
    assert any("hold" in r for r in hero(state)["departure"]["reasons"])
    assert state["containers"][state["hero_id"]]["source_version"] == 15
    assert state["feed"]["duplicates_ignored"] == 1
    assert len([e for e in state["timeline"] if e["type"] == "evidence.duplicate"]) == 1


def test_no_future_incident_exposed_and_world_enforces_delayed_closure():
    state = apply_command(create_state("battery_truck_access_2024"), {"command": "advance", "minutes": 31, "strategy": "fifo"})
    assert sum(r["available_capacity"] for r in state["resources"].values() if r["gate"] == "East") == 2
    # Public evidence remains open until minute 32, but execution uses the world closure.
    assert not any(r["kind"] == "gate_handoff" and any(x.startswith("east") for x in r["resource_ids"]) for r in state["running"])
    state = apply_command(state, {"command": "advance", "minutes": 1, "strategy": "fifo"})
    assert snapshot(state)["overview"]["lanes_open"] == 2
    assert state["metrics"]["constraint_violations"] == 0


@pytest.mark.parametrize("strategy", ["fifo", "priority", "optimized"])
def test_equal_service_negative_control_has_exact_capacity_for_every_policy(strategy):
    state = apply_command(create_state("equal_service_control"), {"command": "advance", "minutes": 240, "strategy": strategy})
    assert len(state["completed"]) == 96
    assert len({r["container_id"] for r in state["completed"]}) == 96
    assert state["metrics"]["invalid_action_attempts"] == 0
    assert state["metrics"]["constraint_violations"] == 0


def test_independent_validator_rejects_over_capacity_and_stale_plan():
    state = create_state("equal_service_control")
    result = plan(state, strategy="fifo")
    corrupted = copy.deepcopy(result)
    corrupted["operations"][1]["resource_ids"] = corrupted["operations"][0]["resource_ids"]
    corrupted["operations"][1]["start_min"] = corrupted["operations"][0]["start_min"]
    corrupted["operations"][1]["end_min"] = corrupted["operations"][0]["end_min"]
    assert any("capacity" in error for error in validate_plan(state, corrupted))
    result["input_clock_min"] = -1
    with pytest.raises(ValueError, match="stale"):
        apply_command(state, {"command": "select_plan", "plan": result})


def test_replay_seek_rebuilds_observations_without_simulated_completions():
    state = create_state("battery_truck_access_2024", mode="REPLAY_T49")
    state = apply_command(state, {"command": "seek", "minute": 95})
    assert snapshot(state)["overview"]["lanes_open"] == 3
    assert not state["completed"]
    assert state["plan"]["solver_status"] == "REPLAY_ONLY"
    state = apply_command(state, {"command": "seek", "minute": 0})
    assert snapshot(state)["overview"]["lanes_open"] == 4
    with pytest.raises(ValueError):
        apply_command(state, {"command": "power", "enabled": False})


def test_feed_controls_change_information_not_physical_resources():
    state = create_state("normal_operations")
    state = apply_command(state, {"command": "feed", "action": "delay"})
    assert not snapshot(state)["feed"]["online"]
    assert len(state["feed_queue"]) == 1
    assert snapshot(state)["overview"]["lanes_open"] == 4
    projection_before = json.dumps({number: c["provider"] for number, c in state["containers"].items()}, sort_keys=True)
    state = apply_command(state, {"command": "feed", "action": "duplicate"})
    assert snapshot(state)["feed"]["duplicates_ignored"] == 1
    assert projection_before == json.dumps({number: c["provider"] for number, c in state["containers"].items()}, sort_keys=True)
    assert len(state["feed_processed"]) == 1
    state = apply_command(state, {"command": "advance", "minutes": 12, "strategy": "fifo"})
    assert len(state["feed_queue"]) == 2
    assert state["feed"]["events_received"] == 100
    assert state["feed"]["latency_minutes"] >= 10
    state = apply_command(state, {"command": "feed", "action": "recover"})
    assert snapshot(state)["feed"]["online"]
    assert not state["feed_queue"]
    assert state["feed"]["events_received"] == 400
    assert state["containers"][state["hero_id"]]["provider_checked_min"] == 12
    assert any("hold" in r for r in hero(state)["departure"]["reasons"])


def test_paired_experiment_uses_common_random_numbers_and_retains_ties():
    result = experiment("equal_service_control", [17], horizon_minutes=30)
    assert {r["completed_handoffs"] for r in result["strategies"]} == {12}
    hashes = {r["runs"][0]["world_sample_hash"] for r in result["strategies"]}
    assert len(hashes) == 1
    assert all(p["mean_difference"] == 0 for p in result["paired_results"])
    assert result["negative_control_expected_handoffs"] == 12


def test_recovery_drains_queued_events_without_clearing_hold_or_resetting_history():
    state = create_state("normal_operations")
    state = apply_command(state, {"command": "feed", "action": "delay"})
    state = apply_command(state, {"command": "advance", "minutes": 75, "strategy": "fifo"})
    received_before = state["feed"]["events_received"]
    queued = len(state["feed_queue"])
    completed_before = len(state["completed"])
    state = apply_command(state, {"command": "feed", "action": "recover"})
    assert state["feed"]["events_received"] == received_before + (queued + 1) * 100
    assert len(state["completed"]) == completed_before
    assert state["clock_min"] == 75
    assert any("hold" in r for r in hero(state)["departure"]["reasons"])
    assert any(e["type"] == "feed.queued" for e in state["timeline"])


def test_same_clock_plan_is_stale_when_new_evidence_changes_prerequisites():
    state = create_state("equal_service_control")
    candidate = plan(state, strategy="fifo")
    number = candidate["operations"][0]["container_id"]
    state = apply_command(state, {"command": "evidence", "container_id": number, "kind": "customs", "values": {"holds": [{"name": "customs", "status": "hold"}]}})
    assert any("stale" in error for error in validate_plan(state, candidate))
    with pytest.raises(ValueError, match="Plan rejected"):
        apply_command(state, {"command": "select_plan", "plan": candidate})


def test_newer_unrelated_field_does_not_block_a_valid_hold_update():
    from gate_triage.workbench.engine import _receive_provider_envelope
    state = create_state("normal_operations")
    state["clock_min"] = 25
    c = state["containers"][state["hero_id"]]
    _receive_provider_envelope(state, {"id": "availability-v20", "published_min": 20, "records": [{"container_id": c["container_id"], "patch": {"available_for_pickup": True}}]})
    _receive_provider_envelope(state, {"id": "hold-v15", "published_min": 15, "records": [{"container_id": c["container_id"], "patch": {"holds_at_pod_terminal": [{"name": "customs", "status": "hold", "description": "newer field evidence"}]}}]})
    assert c["source_watermarks"]["available_for_pickup"] == 20
    assert c["source_watermarks"]["holds_at_pod_terminal"] == 15
    assert c["provider"]["holds_at_pod_terminal"][0]["description"] == "newer field evidence"


def test_pending_unknown_and_active_holds_have_distinct_meaning():
    for hold_status, expected in [("pending", "PENDING_REVIEW"), ("unknown", "UNKNOWN_HOLD"), ("hold", "CONFLICT")]:
        state = create_state("equal_service_control")
        number = next(iter(state["containers"]))
        state = apply_command(state, {"command": "evidence", "container_id": number, "kind": "customs", "values": {"holds": [{"name": "customs", "status": hold_status}]}})
        row = next(c for c in snapshot(state)["containers"] if c["container_id"] == number)
        assert row["pickup_state"] == expected
        assert row["departure"]["status"] == ("blocked" if hold_status == "hold" else "unknown")


def test_historical_reported_departures_do_not_create_arrivals_or_actual_throughput():
    state = create_state("normal_operations")
    historical = [c for c in state["containers"].values() if c["provider"].get("pod_full_out_at")]
    assert len(historical) == 3
    state = apply_command(state, {"command": "advance", "minutes": 180, "strategy": "fifo"})
    assert all(not state["containers"][c["container_id"]]["arrived"] for c in historical)
    assert not {c["container_id"] for c in historical} & {c["container_id"] for c in state["completed"]}
    assert snapshot(state)["overview"]["reported_departed"] == 3


def test_previous_workspace_state_upgrades_without_resetting_progress_or_mutating_input():
    state = apply_command(create_state("equal_service_control"), {"command": "advance", "minutes": 15, "strategy": "fifo"})
    old = copy.deepcopy(state)
    for key in ("engine_revision", "feed_queue", "feed_inbox", "feed_processed"):
        old.pop(key, None)
    for c in old["containers"].values():
        c.pop("source_watermarks", None)
        c.pop("provider_received_min", None)
    before = json.dumps(old, sort_keys=True)
    snap = snapshot(old)
    assert snap["clock_min"] == 15
    assert snap["overview"]["completed_handoffs"] == 6
    assert json.dumps(old, sort_keys=True) == before
    updated = apply_command(old, {"command": "feed", "action": "duplicate"})
    assert updated["clock_min"] == 15
    assert len(updated["completed"]) == 6
    assert updated["engine_revision"] == 4
    assert updated["feed"]["duplicates_ignored"] == 1


def provider_evidence(state, number, field):
    row = next(c for c in snapshot(state)["containers"] if c["container_id"] == number)
    return next(e for e in row["evidence"] if e["id"].startswith(f"{number}:provider:{field}:"))


def test_partial_hold_update_does_not_refresh_lfd_evidence_timestamps():
    state = create_state("normal_operations")
    number = state["hero_id"]
    initial_lfd = provider_evidence(state, number, "pickup_lfd")
    state = apply_command(state, {"command": "advance", "minutes": 5, "strategy": "fifo"})
    state = apply_command(state, {"command": "evidence", "container_id": number, "kind": "provider", "values": {"holds_at_pod_terminal": [{"name": "customs", "status": "hold", "description": "fresh hold report"}]}})
    lfd = provider_evidence(state, number, "pickup_lfd")
    hold = provider_evidence(state, number, "holds_at_pod_terminal")
    assert lfd["observed_at"] == initial_lfd["observed_at"]
    assert lfd["received_at"] == initial_lfd["received_at"]
    assert hold["observed_at"] != lfd["observed_at"]
    assert hold["received_at"] != lfd["received_at"]


def test_provider_lfd_fee_deadline_updates_are_visible_and_leave_hold_unchanged():
    state = create_state("normal_operations")
    number = state["hero_id"]
    original_hold = copy.deepcopy(state["containers"][number]["provider"]["holds_at_pod_terminal"])
    original_terminal_deadline = state["containers"][number]["provider"]["import_deadlines"]["pickup_lfd_terminal"]
    state = apply_command(state, {"command": "advance", "minutes": 6, "strategy": "fifo"})
    fee = {"name": "Synthetic demurrage exposure", "amount": 75.5, "currency": "USD"}
    state = apply_command(state, {"command": "evidence", "container_id": number, "kind": "provider", "values": {"pickup_lfd": "2026-10-17", "fees_at_pod_terminal": [fee], "import_deadlines": {"pickup_lfd_line": "2026-10-17"}}})
    attrs = state["containers"][number]["provider"]
    assert attrs["pickup_lfd"] == "2026-10-17"
    assert attrs["fees_at_pod_terminal"] == [fee]
    assert attrs["import_deadlines"]["pickup_lfd_terminal"] == original_terminal_deadline
    assert attrs["holds_at_pod_terminal"] == original_hold
    assert provider_evidence(state, number, "pickup_lfd")["time_precision"] == "date"
    assert provider_evidence(state, number, "fees_at_pod_terminal")["value"] == [fee]
    assert any("hold" in reason for reason in hero(state)["departure"]["reasons"])
    json.dumps(state, allow_nan=False)


def test_stale_queued_provider_field_updates_cannot_replace_newer_fields():
    state = create_state("normal_operations")
    number = state["hero_id"]
    state = apply_command(state, {"command": "advance", "minutes": 7, "strategy": "fifo"})
    state = apply_command(state, {"command": "evidence", "container_id": number, "kind": "provider", "published_at_min": 7, "values": {"pickup_lfd": "2026-10-20", "fees_at_pod_terminal": [{"amount": 90}]}})
    newest_lfd = provider_evidence(state, number, "pickup_lfd")
    state = apply_command(state, {"command": "feed", "action": "delay"})
    state = apply_command(state, {"command": "evidence", "container_id": number, "kind": "provider", "published_at_min": 2, "values": {"pickup_lfd": "2026-10-18", "fees_at_pod_terminal": [{"amount": 10}]}})
    assert any(e["published_min"] == 2 for e in state["feed_queue"])
    state = apply_command(state, {"command": "feed", "action": "recover"})
    attrs = state["containers"][number]["provider"]
    assert attrs["pickup_lfd"] == "2026-10-20"
    assert attrs["fees_at_pod_terminal"] == [{"amount": 90}]
    assert provider_evidence(state, number, "pickup_lfd")["observed_at"] == newest_lfd["observed_at"]


@pytest.mark.parametrize("values", [
    {"pickup_lfd": "tomorrow"},
    {"pickup_lfd": "2026-10-18T12:00:00"},
    {"fees_at_pod_terminal": [{"amount": float("inf")}]},
    {"fees_at_pod_terminal": [{"amount": float("nan")}]},
    {"import_deadlines": {"arbitrary_unrecognized_source": "2026-10-17"}},
])
def test_provider_updates_reject_invalid_dates_and_nonfinite_values(values):
    state = create_state("normal_operations")
    with pytest.raises(ValueError):
        apply_command(state, {"command": "evidence", "container_id": state["hero_id"], "kind": "provider", "values": values})


def test_upgrade_from_revision_two_does_not_fabricate_per_field_receipts():
    state = create_state("normal_operations")
    state["engine_revision"] = 2
    for c in state["containers"].values():
        c.pop("source_receipts", None)
    result = provider_evidence(state, state["hero_id"], "pickup_lfd")
    assert result["received_at"] is None
    assert result["observed_at"] == state["start_at"]
    with pytest.raises(ValueError):
        apply_command(create_state("normal_operations", mode="REPLAY_T49"), {"command": "evidence", "container_id": state["hero_id"], "kind": "provider", "values": {"pickup_lfd": "2026-10-17"}})
