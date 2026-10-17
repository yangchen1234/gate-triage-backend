import copy
import json
from pathlib import Path

from gate_triage.demo_score import score


DEFAULT = {"lanes_open": 8, "customs_online": True, "power_zone_b": True}
FIXTURES = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "original_demo_containers.json").read_text()
)


def test_fixtures_cover_frontend_cargo_types_and_scorer_does_not_mutate_sources():
    assert len(FIXTURES) == 5
    assert {item["cargo_type"] for item in FIXTURES} == {"reefer_pharma", "reefer_food", "hazmat", "general", "empty"}
    original = copy.deepcopy(FIXTURES)
    for container in FIXTURES:
        result = score(container, DEFAULT)
        assert result["action"] in {"release", "slow", "inspect", "reroute"}
        assert all(0 <= result[name] <= 1 for name in ("priority", "urgency", "conflict_score"))
        assert result["reason"]
    assert FIXTURES == original


def test_customs_hold_keeps_human_review_when_power_is_lost():
    result = score(FIXTURES[0], {**DEFAULT, "power_zone_b": False})
    assert result["action"] == "inspect"
    assert "do not release" in result["reason"]
    assert "powered storage" in result["reason"]


def test_clear_food_reefer_can_be_rerouted_but_offline_customs_blocks_release():
    food = FIXTURES[1]
    assert score(food, DEFAULT)["action"] == "release"
    assert score(food, {**DEFAULT, "power_zone_b": False})["action"] == "reroute"
    offline = score(food, {**DEFAULT, "customs_online": False})
    assert offline["action"] == "slow"
    assert "clearance is unverified" in offline["reason"]


def test_reduced_lanes_reorders_time_sensitive_cargo():
    def ranked(scenario):
        return [item["container_id"] for item in sorted(FIXTURES, key=lambda item: score(item, scenario)["priority"], reverse=True)]

    assert ranked(DEFAULT) != ranked({**DEFAULT, "lanes_open": 4})
    food_normal = score(FIXTURES[1], DEFAULT)["urgency"]
    assert score(FIXTURES[1], {**DEFAULT, "lanes_open": 4})["urgency"] > food_normal


def test_weight_conflict_requires_inspection_even_without_customs_hold():
    result = score(FIXTURES[2], DEFAULT)
    assert result["action"] == "inspect"
    assert result["conflict_score"] > 0.15
