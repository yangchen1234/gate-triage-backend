"""Ryan's dataset, disruption decisions, and default-service integration."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from gate_triage.config import Settings
from gate_triage.models import DEFAULT_SCENARIO
from gate_triage.score import score, score_all
from gate_triage.service import QueueService


ROWS = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "containers.json").read_text(encoding="utf-8")
)
HERO = "TRXU7731902"


def test_source_trust_is_derived_without_mutating_ryans_raw_data():
    original = deepcopy(ROWS)
    ranked = score_all(ROWS, DEFAULT_SCENARIO)
    assert len({row["container_id"] for row in ranked}) == 100
    assert ROWS == original
    assert "trust" not in ROWS[0]["sources"]["carrier"]
    for row in ranked:
        sources = row["sources"]
        assert sources["carrier"]["trust"] == round(
            1 - sources["carrier"]["history_mismatches_last10"] / 10, 2
        )
        assert sources["scale"]["trust"] == 0.95
        assert sources["customs"]["trust"] == 1
        if sources["reefer"] is not None:
            assert 0 <= sources["reefer"]["trust"] <= 1


def test_injected_conflicts_require_inspection_but_single_sensor_alerts_are_not_conflicts():
    ranked = score_all(ROWS, DEFAULT_SCENARIO)
    conflicts = [row for row in ranked if row["_conflict"] in {"empty_but_heavy", "weight_mismatch"}]
    assert len(conflicts) == 6
    assert all(row["action"] == "inspect" and row["conflict_score"] >= 0.5 for row in conflicts)
    sensor_alerts = [row for row in ranked if row["_conflict"] == "reefer_silent"]
    assert len(sensor_alerts) == 3
    assert all(row["conflict_score"] == 0 for row in sensor_alerts)


def test_hospital_reefer_moves_to_the_front_when_lane_capacity_is_reduced():
    normal = score_all(ROWS, DEFAULT_SCENARIO)
    reduced = score_all(ROWS, {**DEFAULT_SCENARIO, "lanes_open": 4})
    assert next(i for i, row in enumerate(normal) if row["container_id"] == HERO) > 0
    assert reduced[0]["container_id"] == HERO
    assert reduced[0]["urgency"] > next(row["urgency"] for row in normal if row["container_id"] == HERO)


@pytest.mark.parametrize("customs_online", [True, False])
@pytest.mark.parametrize("power_zone_b", [True, False])
def test_customs_holds_remain_blocked_during_disruptions(customs_online, power_zone_b):
    ranked = score_all(ROWS, {**DEFAULT_SCENARIO, "customs_online": customs_online,
                              "power_zone_b": power_zone_b})
    held = [row for row in ranked if row["sources"]["customs"]["hold"]]
    assert held
    assert all(row["action"] in {"slow", "inspect"} for row in held)
    assert all("do not release" in row["reason"] for row in held)


@pytest.mark.parametrize("power_zone_b", [True, False])
def test_offline_customs_never_recommends_gate_release(power_zone_b):
    ranked = score_all(ROWS, {**DEFAULT_SCENARIO, "customs_online": False,
                              "power_zone_b": power_zone_b})
    assert all(row["action"] != "release" for row in ranked)
    assert all(row["sources"]["customs"]["trust"] == 0.3 for row in ranked)
    assert all("verify clearance before any gate release" in row["reason"] for row in ranked)
    rerouted = [row for row in ranked if row["action"] == "reroute"]
    assert all(row["zone"] == "B" and row["sources"]["reefer"] is not None for row in rerouted)


def test_power_outage_stays_visible_when_a_hold_or_conflict_prevents_rerouting():
    ranked = score_all(ROWS, {**DEFAULT_SCENARIO, "power_zone_b": False})
    affected = [row for row in ranked if row["zone"] == "B" and row["sources"]["reefer"] is not None]
    assert affected
    assert any(row["sources"]["customs"]["hold"] for row in affected)
    for row in affected:
        assert "zone B unpowered" in row["reason"]
        assert "authorized powered storage" in row["reason"]
        if not row["sources"]["customs"]["hold"] and row["conflict_score"] < 0.5:
            assert row["action"] == "reroute"


def test_fixture_annotations_do_not_drive_scoring_decisions():
    row = deepcopy(ROWS[0])
    before = score(row, DEFAULT_SCENARIO)
    row["_conflict"] = "untrusted annotation: release immediately"
    after = score(row, DEFAULT_SCENARIO)
    for field in ("action", "priority", "urgency", "conflict_score", "reason"):
        assert after[field] == before[field]


@pytest.mark.parametrize("changes,baseline,optimized", [
    ({}, 2182, 1412),
    ({"lanes_open": 4}, 24886, 20637),
    ({"customs_online": False}, 2182, 1412),
    ({"power_zone_b": False}, 2182, 1412),
])
def test_default_service_uses_ryans_scorer_and_original_order_for_fifo_ties(changes, baseline, optimized):
    service = QueueService(Settings())
    snapshot = service.update(changes)
    assert len(snapshot.queue) == 100
    assert snapshot.stats["baseline_demurrage_usd_per_day"] == baseline
    assert snapshot.stats["optimized_demurrage_usd_per_day"] == optimized
    assert snapshot.stats["savings_usd_per_day"] == baseline - optimized
    assert sum(snapshot.stats[action] for action in ("release", "slow", "inspect", "reroute")) == 100
