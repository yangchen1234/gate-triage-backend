"""Deterministic, advisory demo rules; replace with Ryan's score() for the event.

Scores express processing urgency, not permission to move a container. Customs
holds remain a hard constraint and require an authorized human to resolve.
"""

from __future__ import annotations

from typing import Any


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def score(container: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """Return computed fields without changing the input or its source trust."""
    sources = container["sources"]
    carrier, scale, customs = (sources[name] for name in ("carrier", "scale", "customs"))
    reefer = sources.get("reefer")
    cargo_type = container["cargo_type"]
    is_critical = cargo_type in {"reefer_pharma", "reefer_food"}
    lanes_open = scenario.get("lanes_open", 8)
    customs_online = scenario.get("customs_online", True)
    power_out = bool(reefer) and container["zone"] == "B" and not scenario.get("power_zone_b", True)

    declared_weight = float(carrier["declared_weight_kg"])
    actual_weight = float(scale["weight_kg"])
    weight_gap = abs(actual_weight - declared_weight) / max(actual_weight, declared_weight, 1.0)
    empty_but_heavy = carrier["declared_status"] == "empty" and actual_weight > 4500
    temperature_drift = abs(float(reefer["temp_c"]) - float(reefer["setpoint_c"])) if reefer else 0.0
    stale_reefer = bool(reefer) and reefer["last_ping_min"] > 30
    lowest_trust = min(float(source["trust"]) for source in sources.values() if source is not None)
    conflict_score = _clamp(max(weight_gap, 0.9 if empty_but_heavy else 0.0,
                                min(temperature_drift / 6.0, 1.0), 0.4 if stale_reefer else 0.0))

    reasons: list[str] = []
    if empty_but_heavy:
        reasons.append(f"Carrier says empty but scale reads {actual_weight / 1000:.1f}t")
    elif weight_gap > 0.15:
        reasons.append(f"Carrier and scale weights differ by {weight_gap:.0%}")
    if reefer and temperature_drift > 1.0:
        reasons.append(f"Reefer differs from setpoint by {temperature_drift:.1f} C")
    if stale_reefer:
        reasons.append("Reefer telemetry is stale; verify temperature")

    # Precedence prevents a disruption from bypassing a known legal hold.
    if customs["hold"]:
        action = "inspect"
        reasons.append("Customs hold requires authorized human review; do not release")
        if power_out:
            reasons.append("Zone B power is out; arrange approved powered storage while the hold remains")
    elif not customs_online:
        action = "inspect" if conflict_score >= 0.2 or cargo_type == "hazmat" else "slow"
        reasons.append("Customs is offline; clearance is unverified and needs human confirmation")
        if power_out:
            reasons.append("Zone B power is out; request approved powered storage")
    elif weight_gap > 0.15 or empty_but_heavy:
        action = "inspect"
        reasons.append("Verify manifest and physical contents before movement")
        if power_out:
            reasons.append("Zone B power is out; request approved powered inspection storage")
    elif power_out or temperature_drift > 2.0:
        action = "reroute"
        reasons.append("Request authorized transfer to powered cold storage")
    elif lowest_trust < 0.6 or stale_reefer or temperature_drift > 1.0:
        action = "slow"
        reasons.append("Reconcile low-confidence or stale source data before release")
    else:
        action = "release"
        reasons.append("Sources agree and no customs hold is reported; eligible for operator release review")

    fee_weight = min(float(container["demurrage_usd_per_day"]) / 600.0, 1.0)
    overdue_weight = min(max(-float(container["free_days_left"]), 0.0) / 5.0, 1.0)
    critical_weight = {"reefer_pharma": 0.28, "reefer_food": 0.2, "hazmat": 0.1}.get(cargo_type, 0.0)
    capacity_pressure = (1.0 - lanes_open / 8.0) * (0.55 if is_critical else 0.02)
    urgency = _clamp(0.12 + 0.35 * fee_weight + 0.2 * overdue_weight + critical_weight
                     + capacity_pressure + (0.22 if power_out else 0.0)
                     + min(temperature_drift / 20.0, 0.25))
    priority = _clamp(0.76 * urgency + 0.24 * conflict_score
                      + (0.08 if action in {"inspect", "reroute"} else 0.0))
    if lanes_open < 8 and is_critical:
        reasons.append("Reduced lane capacity increases priority for time-sensitive cargo")

    return {
        "action": action,
        "priority": priority,
        "urgency": urgency,
        "conflict_score": conflict_score,
        "reason": "; ".join(reasons) + ".",
    }
