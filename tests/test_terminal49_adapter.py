"""The adapter must turn a Terminal49-shaped record into a box score() accepts unchanged."""
from datetime import datetime

from gate_triage.score import score
from gate_triage.terminal49_adapter import from_terminal49

NOW = datetime(2026, 10, 17, 8, 0, 0)

# Shape per Terminal49 API v2 "Holds and fees" guide (values illustrative).
T49_RECORD = {
    "id": "3f1c…",
    "type": "container",
    "attributes": {
        "number": "MSCU9876543",
        "available_for_pickup": False,
        "pickup_lfd": "2026-10-16",
        "holds_at_pod_terminal": [
            {"name": "customs", "status": "hold", "description": "CBP HOLD - DOCS"},
            {"name": "TMF", "status": "pending", "description": None},
        ],
        "fees_at_pod_terminal": [
            {"type": "demurrage", "amount": "345.00", "currency_code": "USD"},
            {"type": "total", "amount": "690.00", "currency_code": "USD"},
        ],
    },
}
TOS = {"declared_status": "laden", "declared_weight_kg": 18200, "weight_kg": 18550}
REEFER = {"temp_c": 2.4, "setpoint_c": 2.0, "last_ping_min": 9}


def test_maps_customs_hold_fees_and_lfd():
    box = from_terminal49(T49_RECORD, tos=TOS, reefer=REEFER, cargo_type="reefer_pharma",
                          consignee_type="hospital", zone="A", now=NOW, carrier_history_mismatches=1)
    assert box["container_id"] == "MSCU9876543"
    assert box["sources"]["customs"]["hold"] is True
    assert box["sources"]["customs"]["hold_type"] == "manifest"          # customs → manifest review
    assert box["sources"]["customs"]["terminal49_hold"]["name"] == "customs"  # government hold wins over TMF
    assert box["carrier_demurrage_per_day"] == 345
    assert box["free_days_left"] == -1                                    # LFD was yesterday
    assert box["data_sources"]["customs"] == "terminal49"


def test_cleared_hold_is_absent_not_released():
    rec = {**T49_RECORD, "attributes": {**T49_RECORD["attributes"], "holds_at_pod_terminal": [], "available_for_pickup": True}}
    box = from_terminal49(rec, tos=TOS, reefer=None, cargo_type="general", consignee_type="retail", zone="C", now=NOW)
    assert box["sources"]["customs"] == {"hold": False, "hold_type": "none", "est_days_to_clear": 0}
    assert box["sources"]["reefer"] is None


def test_adapted_box_scores_without_changes():
    box = from_terminal49(T49_RECORD, tos=TOS, reefer=REEFER, cargo_type="reefer_pharma",
                          consignee_type="hospital", zone="A", now=NOW)
    scored = score(box, {"lanes_open": 8, "customs_online": True, "power_zone_b": True, "port": "LAX"})
    assert scored["action"] == "slow"                      # customs hold, customs online → R2
    assert scored["decision_trace"]["rule_fired"] == "R2_customs_hold"
    assert 0 <= scored["priority"] <= 1
