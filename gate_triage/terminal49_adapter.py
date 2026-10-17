"""
terminal49_adapter.py — map a Terminal49 container record into Gate Triage's container schema.

Terminal49 is the system of record for customs holds, terminal fees and last free day.
It does not carry scale weights or reefer telemetry; those come from the terminal operating
system (TOS) and the reefer sensor feed, so this adapter composes three feeds into one box:

    Terminal49  →  customs hold / hold type, carrier demurrage, free days left, availability
    TOS         →  carrier declaration (status, declared weight) and the terminal scale reading
    Reefer feed →  temperature, setpoint, last ping

Field reference (Terminal49 API v2, "Holds and fees" guide):
    attributes.holds_at_pod_terminal[]  { name: freight|line|customs|USDA|VACIS|TMF|other, status: hold|pending, description }
    attributes.fees_at_pod_terminal[]   { type: demurrage|extended_dwell_time|exam|total|other, amount, currency_code }
    attributes.pickup_lfd               last free day (ISO date)
    attributes.available_for_pickup     bool
A cleared hold is removed from the array; there is no "released" status.

No live Terminal49 data is used in the demo dataset. This module exists so a real feed is a
drop-in: `from_terminal49(record, tos=..., reefer=...)` returns a box `score()` accepts unchanged.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# Terminal49 hold names → the hold_type vocabulary score.py understands.
# 'freight', 'line' and 'TMF' are commercial holds, not customs; they still block release.
HOLD_TYPE_MAP = {
    "customs": "manifest",          # CBP hold; documentation/manifest review is the common case
    "USDA": "document_review",      # partner-government-agency (PGA) review
    "VACIS": "intensive",           # non-intrusive scan; treated like an exam for timing
    "freight": "document_review",   # carrier release pending payment — paperwork, not cargo risk
    "line": "document_review",
    "TMF": "document_review",
    "other": "manifest",
}

# Rough days-to-clear by Terminal49 hold name, used only for the est_days_to_clear hint.
EST_DAYS = {"customs": 2, "USDA": 3, "VACIS": 3, "freight": 1, "line": 1, "TMF": 1, "other": 2}

# Holds that are customs / government in nature (vs. commercial). Both block, but only these
# are "customs" for the customs_online scenario logic.
GOVERNMENT_HOLDS = {"customs", "USDA", "VACIS"}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def from_terminal49(record: dict[str, Any], *, tos: dict[str, Any], reefer: dict[str, Any] | None,
                    cargo_type: str, consignee_type: str, zone: str,
                    now: datetime, carrier_history_mismatches: int = 0) -> dict[str, Any]:
    """Compose one Gate Triage container from a Terminal49 container record plus TOS and reefer feeds.

    `record` is the Terminal49 container object (with `id` and `attributes`).
    `tos` must carry: declared_status ('empty'|'laden'), declared_weight_kg, weight_kg (scale).
    `reefer` is None for dry boxes, else {temp_c, setpoint_c, last_ping_min}.
    """
    attrs = record.get("attributes", {})
    number = attrs.get("number") or record.get("id")
    if not number:
        raise ValueError("Terminal49 record has no container number")

    # ---- customs / holds
    holds = attrs.get("holds_at_pod_terminal") or []
    active = [h for h in holds if h.get("status") in ("hold", "pending")]
    gov = [h for h in active if h.get("name") in GOVERNMENT_HOLDS]
    chosen = (gov or active or [None])[0]
    if chosen is None:
        customs = {"hold": False, "hold_type": "none", "est_days_to_clear": 0}
    else:
        name = chosen.get("name", "other")
        customs = {
            "hold": True,
            "hold_type": HOLD_TYPE_MAP.get(name, "manifest"),
            "est_days_to_clear": EST_DAYS.get(name, 2),
            "terminal49_hold": {"name": name, "status": chosen.get("status"),
                                "description": chosen.get("description")},
        }

    # ---- fees → carrier demurrage per day (Terminal49 describes 'demurrage' as the daily carrier charge)
    fees = attrs.get("fees_at_pod_terminal") or []
    demurrage_fee = next((f for f in fees if f.get("type") == "demurrage"), None)
    carrier_per_day = float(demurrage_fee["amount"]) if demurrage_fee else 0.0
    currency = (demurrage_fee or {}).get("currency_code") or "USD"

    # ---- last free day → free_days_left
    lfd = _parse_date(attrs.get("pickup_lfd"))
    free_days_left = (lfd - now.date()).days if lfd else 0

    # ---- arrival: Terminal49 exposes discharge timestamps on the shipment; fall back to LFD − free time
    arrived_at = attrs.get("pod_discharged_at") or attrs.get("pod_arrived_at")

    return {
        "container_id": number,
        "carrier_code": number[:4],
        "cargo_type": cargo_type,
        "consignee_type": consignee_type,
        "zone": zone,
        "arrived_at": arrived_at or now.isoformat(),
        "free_days_left": free_days_left,
        "pickup_lfd": attrs.get("pickup_lfd"),
        "available_for_pickup": bool(attrs.get("available_for_pickup", False)),
        "currency": currency,
        "carrier_demurrage_per_day": round(carrier_per_day),
        "port_demurrage_per_day": 0.0,              # terminal storage comes from the port tariff profile
        "demurrage_per_day": round(carrier_per_day),
        "demurrage_usd_per_day": round(carrier_per_day) if currency == "USD" else round(carrier_per_day),
        "demurrage_tier": 1,
        "sources": {
            "carrier": {
                "declared_status": tos["declared_status"],
                "declared_weight_kg": int(tos["declared_weight_kg"]),
                "history_mismatches_last10": int(carrier_history_mismatches),
            },
            "scale": {"weight_kg": int(tos["weight_kg"])},
            "customs": customs,
            "reefer": None if reefer is None else {
                "temp_c": float(reefer["temp_c"]),
                "setpoint_c": float(reefer["setpoint_c"]),
                "last_ping_min": int(reefer["last_ping_min"]),
            },
        },
        "data_sources": {
            "customs": "terminal49", "fees": "terminal49", "free_time": "terminal49",
            "carrier_declaration": "tos", "scale": "tos", "reefer": "reefer_feed" if reefer else None,
        },
    }
