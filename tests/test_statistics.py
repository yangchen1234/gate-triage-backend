from copy import deepcopy
from decimal import Decimal
import json

import pytest

from gate_triage.statistics import calculate_stats


def container(index, fee, priority, *, action="release", arrived_at=None, **extra):
    return {
        "container_id": f"DEMO{index:07d}",
        "arrived_at": arrived_at or f"2026-10-16T00:00:{index:02d}Z",
        "demurrage_usd_per_day": fee,
        "priority": priority,
        "action": action,
        **extra,
    }


def test_fifo_and_optimized_cost_use_unserved_containers_and_all_actions():
    rows = [
        container(0, 10, 0.1, action="release"),
        container(1, 20, 0.2, action="slow"),
        container(2, 100, 0.8, action="inspect"),
        container(3, 200, 0.9, action="reroute"),
    ]
    scenario = {"lanes_open": 1, "customs_online": True, "power_zone_b": False}

    assert calculate_stats(rows, scenario, containers_per_lane_per_day=2) == {
        "release": 1,
        "slow": 1,
        "inspect": 1,
        "reroute": 1,
        "baseline_demurrage_usd_per_day": 300,
        "optimized_demurrage_usd_per_day": 30,
        "savings_usd_per_day": 270,
        "scenario": scenario,
    }


@pytest.mark.parametrize("lanes_open,expected_cost", [(0, 330), (2, 0), (8, 0)])
def test_zero_capacity_and_enough_capacity(lanes_open, expected_cost):
    rows = [container(i, fee, priority) for i, (fee, priority) in enumerate(
        [(10, 0.1), (20, 0.2), (100, 0.8), (200, 0.9)]
    )]
    result = calculate_stats(rows, {"lanes_open": lanes_open}, containers_per_lane_per_day=2)
    assert result["baseline_demurrage_usd_per_day"] == expected_cost
    assert result["optimized_demurrage_usd_per_day"] == expected_cost
    assert result["savings_usd_per_day"] == 0


def test_default_throughput_is_twelve_containers_per_lane():
    rows = [container(i, i + 1, (i + 1) / 13) for i in range(13)]
    result = calculate_stats(rows, {"lanes_open": 1})
    assert result["baseline_demurrage_usd_per_day"] == 13
    assert result["optimized_demurrage_usd_per_day"] == 1
    assert result["savings_usd_per_day"] == 12


def test_savings_can_be_negative():
    rows = [
        container(0, 100, 0.1), container(1, 200, 0.2),
        container(2, 10, 0.8), container(3, 20, 0.9),
    ]
    result = calculate_stats(rows, {"lanes_open": 1}, containers_per_lane_per_day=2)
    assert result["baseline_demurrage_usd_per_day"] == 30
    assert result["optimized_demurrage_usd_per_day"] == 300
    assert result["savings_usd_per_day"] == -270


def test_time_zones_are_normalized_and_ties_preserve_input_order():
    rows = [
        container(0, 10, 0.5, arrived_at="2026-10-16T01:00:00+01:00"),
        container(1, 20, 0.5, arrived_at="2026-10-16T00:00:00Z"),
        container(2, 30, 0.5, arrived_at="2026-10-16T00:00:01Z"),
    ]
    result = calculate_stats(rows, {"lanes_open": 1}, containers_per_lane_per_day=1)
    assert result["baseline_demurrage_usd_per_day"] == 50
    assert result["optimized_demurrage_usd_per_day"] == 50
    assert result["savings_usd_per_day"] == 0


def test_date_only_and_naive_datetime_mean_utc():
    rows = [
        container(0, 10, 0.5, arrived_at="2026-10-16"),
        container(1, 20, 0.5, arrived_at="2026-10-16T00:00:00"),
        container(2, 30, 0.5, arrived_at="2026-10-15T23:30:00-01:00"),
    ]
    result = calculate_stats(rows, {"lanes_open": 1}, containers_per_lane_per_day=1)
    assert result["baseline_demurrage_usd_per_day"] == 50


def test_decimal_totals_are_exact_before_json_and_free_days_do_not_discount():
    rows = [
        container(0, 0.1, 0.5, free_days_left=3),
        container(1, 0.2, 0.5, free_days_left=-2),
    ]
    result = calculate_stats(rows, {"lanes_open": 0})
    assert result["baseline_demurrage_usd_per_day"] == 0.3
    assert result["optimized_demurrage_usd_per_day"] == 0.3
    assert json.loads(json.dumps(result, allow_nan=False))["savings_usd_per_day"] == 0


def test_empty_queue_keeps_all_zero_action_counts():
    result = calculate_stats([], {"lanes_open": 8})
    assert {action: result[action] for action in ("release", "slow", "inspect", "reroute")} == {
        "release": 0, "slow": 0, "inspect": 0, "reroute": 0,
    }
    assert result["baseline_demurrage_usd_per_day"] == 0
    assert result["optimized_demurrage_usd_per_day"] == 0
    assert result["savings_usd_per_day"] == 0


def test_inputs_are_not_modified_and_returned_scenario_is_independent():
    rows = [container(1, 20, 0.9), container(0, 10, 0.1)]
    scenario = {"lanes_open": 1, "custom": {"enabled": True}}
    original_rows, original_scenario = deepcopy(rows), deepcopy(scenario)
    result = calculate_stats(rows, scenario, containers_per_lane_per_day=1)
    result["scenario"]["custom"]["enabled"] = False
    assert rows == original_rows
    assert scenario == original_scenario


@pytest.mark.parametrize("lanes", [None, True, False, -1, 1.5, "4"])
def test_invalid_lane_counts_are_rejected(lanes):
    with pytest.raises(ValueError, match="scenario.lanes_open"):
        calculate_stats([], {"lanes_open": lanes})


@pytest.mark.parametrize("throughput", [None, True, False, 0, -1, 1.5, "12"])
def test_invalid_throughput_is_rejected(throughput):
    with pytest.raises(ValueError, match="containers_per_lane_per_day"):
        calculate_stats([], {"lanes_open": 1}, containers_per_lane_per_day=throughput)


@pytest.mark.parametrize("field,value", [
    ("action", "hold"), ("action", None), ("action", []),
    ("priority", -0.1), ("priority", 1.1), ("priority", True),
    ("priority", "0.5"), ("priority", None),
    ("priority", float("nan")), ("priority", float("inf")),
    ("demurrage_usd_per_day", -1), ("demurrage_usd_per_day", True),
    ("demurrage_usd_per_day", "150"), ("demurrage_usd_per_day", None),
    ("demurrage_usd_per_day", float("nan")),
    ("demurrage_usd_per_day", Decimal("Infinity")),
    ("arrived_at", None), ("arrived_at", ""),
    ("arrived_at", "yesterday"), ("arrived_at", "2026-02-30"),
])
def test_invalid_container_fields_are_rejected(field, value):
    row = container(0, 150, 0.5)
    row[field] = value
    with pytest.raises(ValueError, match=field):
        calculate_stats([row], {"lanes_open": 1})


@pytest.mark.parametrize("field", ["arrived_at", "priority", "demurrage_usd_per_day", "action"])
def test_missing_required_fields_are_rejected(field):
    row = container(0, 150, 0.5)
    del row[field]
    with pytest.raises(ValueError, match=field):
        calculate_stats([row], {"lanes_open": 1})


def test_non_object_container_is_rejected():
    with pytest.raises(ValueError, match="must be an object"):
        calculate_stats([None], {"lanes_open": 1})
