"""Geographic projections must never manufacture operations or authority."""
import copy

from gate_triage.workbench.engine import apply_command, create_state
from gate_triage.workbench.spatial import assess_incident, map_snapshot


def test_geography_is_read_only_and_other_terminals_have_no_fake_counts():
    state = create_state("normal_operations")
    original = copy.deepcopy(state)
    view = map_snapshot(state)
    assert state == original
    assert len(view["terminals"]) == 7
    assert sum(t["properties"]["modeled"] for t in view["terminals"]) == 1
    for terminal in view["terminals"]:
        p = terminal["properties"]
        if not p["modeled"]:
            assert p["severity"] == "unknown"
            assert p["metrics"] == {} and p["container_ids"] == []


def test_incident_scope_is_not_an_automatic_all_port_closure():
    state = create_state("normal_operations")
    east = assess_incident(state, "battery_access_2024", "zone-gate-east", "critical")
    assert set(east["resource_ids"]) == {"east-lane-1", "east-lane-2"}
    assert "zone-gate-west" not in east["affected_zone_ids"]
    foreign = assess_incident(state, "battery_access_2024", "terminal-apm", "critical")
    assert foreign["known_scope"] and not foreign["modeled_scope"]
    assert foreign["effects"] == [] and foreign["affected_container_ids"] == []
    unknown = assess_incident(state, "battery_access_2024", "unconfirmed-location", "critical")
    assert not unknown["known_scope"] and unknown["effects"] == []


def test_feed_loss_channel_and_wind_have_separate_operational_effects():
    state = create_state("normal_operations")
    cyber = assess_incident(state, "cyber_data_2017", "terminal-fenix")
    assert cyber["effects"] == [{"kind": "feed_offline"}]
    assert cyber["resource_ids"] == []
    channel = assess_incident(state, "channel_obstruction_2024", "corridor-main-channel")
    assert channel["effects"] == [{"kind": "marine_channel", "status": "closed"}]
    assert channel["affected_container_ids"] == []
    wind = assess_incident(state, "storm_wind", "terminal-fenix")
    assert set(wind["resource_ids"]) == {"quay-crane-1", "quay-crane-2"}
    road = assess_incident(state, "exit_congestion", "corridor-road-exit")
    assert set(road["resource_ids"]) == {"east-lane-2", "west-lane-2"}


def test_map_progress_comes_from_work_not_random_counters():
    state = create_state("normal_operations")
    state = apply_command(state, {"command": "advance", "minutes": 15})
    view = map_snapshot(state)
    gate_progress = sum(z["properties"]["metrics"]["completed_operations"] for z in view["zones"] if z["properties"]["operation_type"] == "gate_handoff")
    assert gate_progress == len(state["completed"])
    assert view["as_of_min"] == 15
    for zone in view["zones"]:
        p = zone["properties"]
        if p["operation_type"].startswith("vessel_"):
            assert p["container_ids"] == []  # these are distinct synthetic work orders
