"""Pure, deterministic rules for an explicitly synthetic operations simulator.

This module does not authorize real terminal operations. All added readiness,
resource topology, sensor interpretation and thresholds are demo assumptions.
Ryan's input records are kept unmodified under each container's ``raw`` field.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from typing import Any


RULE_VERSION = "planner-demo-1.0"
SEED_TIME = "2026-10-17T16:00:00+00:00"
HERO_ID = "TRXU7731902"
PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2}
MANUAL_STATUSES = {"acknowledged", "in_progress", "waiting"}

ASSUMPTIONS = [
    "Synthetic operations overlay on Ryan's mock data; no live terminal, customs or Terminal49 connection.",
    "Zone B uses East gate; zones A/C use West gate, with four lanes each. This is invented demo topology, not an LA terminal map.",
    "Each open lane has a modeled daily capacity of 12 departures; this is a configurable demo assumption, not measured throughput.",
    "Appointment, payment and carrier-document readiness are assumed true in the seed; a real integration must verify each independently.",
    "Seed scale and carrier weights are interpreted as container-only gross kilograms. All containers use a simulated 3,800 kg tare, not a container specification.",
    "Weight differences above max(1,000 kg, 15%) and temperature deviations above 2 C are demo alert thresholds, not industry or cargo-safety standards.",
    "Sensor freshness is modeled at 30 minutes; scale, declaration and customs evidence at 120 minutes. Stale or unavailable evidence is not clearance.",
    "A normal temperature reading does not establish cargo quality. Recorded warming leaves a separate cargo-condition review outstanding.",
    "All movement and release indications are advisory simulation results. Customs notices are simulated authoritative evidence, never a supervisor override.",
    "Fee comparison is a one-day synthetic queue proxy using the same eligible containers and gate capacities for both strategies, not actual savings or a bill forecast.",
]


def _time(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _ago(now: str, minutes: float) -> str:
    return (_time(now) - timedelta(minutes=minutes)).isoformat()


def _number(value: Any, name: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ValueError(f"{name} must be finite" + (" and nonnegative" if nonnegative else ""))
    return result


def _fresh(observed_at: str, now: str, minutes: float) -> bool:
    age = (_time(now) - _time(observed_at)).total_seconds() / 60
    return 0 <= age <= minutes


def _evidence(container_id: str, source: str, label: str, value: Any,
              at: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"id": f"{container_id}:{source}", "source": source, "label": label,
            "value": value, "observed_at": at, "quality": "simulated",
            "detail": detail, **extra}


def build_seed(raw_containers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a separate operational state without modifying or extending raw data."""
    if not isinstance(raw_containers, list):
        raise ValueError("raw_containers must be a list")
    originals = deepcopy(raw_containers)
    ids = [row.get("container_id") for row in originals]
    if any(not isinstance(cid, str) or not cid for cid in ids) or len(set(ids)) != len(ids):
        raise ValueError("Every container requires a unique non-empty container_id")
    hero = HERO_ID if HERO_ID in ids else next(
        (row["container_id"] for row in originals if row.get("sources", {}).get("reefer")),
        None,
    )
    state: dict[str, Any] = {
        "rule_version": RULE_VERSION, "simulated_at": SEED_TIME, "hero_id": hero,
        "assumptions": deepcopy(ASSUMPTIONS),
        "config": {"departures_per_lane_per_day": 12, "reefer_fresh_minutes": 30,
                   "record_fresh_minutes": 120, "temperature_deviation_c": 2.0,
                   "weight_tolerance_kg": 1000.0, "weight_tolerance_fraction": 0.15},
        "incident": {"id": "access_road", "label": "East access road", "status": "open",
                     "affected_gate": "East", "detail": "Synthetic access-road incident; West gate remains independent."},
        "power": {"A": True, "B": True, "C": True}, "customs_online": True,
        "containers": [], "task_status": {}, "task_history": {},
    }
    for row in originals:
        cid = row["container_id"]
        sources = row.get("sources", {})
        carrier, scale, customs = (sources.get(name, {}) for name in ("carrier", "scale", "customs"))
        reefer = sources.get("reefer")
        tare = 3800.0
        declared_status = carrier.get("declared_status", "laden")
        declared_weight = _number(carrier.get("declared_weight_kg", 0), "declared_weight_kg", nonnegative=True)
        actual_weight = _number(scale.get("weight_kg", 0), "weight_kg", nonnegative=True)
        temp = _number(reefer.get("temp_c", 0), "temp_c") if reefer else None
        setpoint = _number(reefer.get("setpoint_c", 0), "setpoint_c") if reefer else None
        minutes = _number(reefer.get("last_ping_min", 0), "last_ping_min", nonnegative=True) if reefer else 0
        hold = bool(customs.get("hold", False))
        overlay: list[str] = []
        if cid == hero:
            declared_status, declared_weight, hold = "empty", tare, True
            actual_weight = max(actual_weight, tare + 8000)
            if reefer:
                temp, minutes = max(temp, setpoint + 3.8), 0
            overlay = ["Carrier declaration changed to empty with simulated tare weight.",
                       "Scale report uses validated container-only gross kg and exceeds tare.",
                       "Customs hold added; warming reading made fresh for the multi-issue demo."]
        zone = row.get("zone", "A")
        if zone not in {"A", "B", "C"}:
            raise ValueError("Demo zones must be A, B or C")
        evidence = {
            "carrier": _evidence(cid, "carrier", "Carrier declaration",
                {"declared_status": declared_status, "declared_weight_kg": declared_weight,
                 "unit": "kg", "weight_basis": "container_gross"}, SEED_TIME,
                "Simulated declaration; weight basis explicitly normalized for this demo."),
            "scale": _evidence(cid, "scale", "Terminal scale report",
                {"container_weight_kg": actual_weight, "tare_kg": tare,
                 "unit": "kg", "weight_basis": "container_gross", "identity_verified": True,
                 "measurement_verified": True}, SEED_TIME,
                "Simulated verified measurement of this container; excludes tractor/chassis. Not a SOLAS certificate."),
            "customs": _evidence(cid, "customs", "Customs status",
                {"hold": hold, "hold_type": "simulated_review" if cid == hero else customs.get("hold_type", "none")},
                SEED_TIME, "Simulated customs notice. Only a new customs notice can change this record."),
            "readiness": _evidence(cid, "readiness", "Dispatch prerequisites",
                {"appointment_ready": True, "payment_ready": True, "documents_ready": True},
                SEED_TIME, "All three are explicit seed assumptions; no real appointment, payment or document verification."),
        }
        if reefer:
            evidence["reefer"] = _evidence(cid, "reefer", "Reefer telemetry",
                {"temp_c": temp, "setpoint_c": setpoint, "unit": "C"}, _ago(SEED_TIME, minutes),
                "Mock telemetry. Threshold and freshness window are configurable demo rules, not a spoilage prediction.")
        state["containers"].append({
            "container_id": cid, "cargo_type": row.get("cargo_type", "general"),
            "zone": zone, "gate": "East" if zone == "B" else "West", "raw": row,
            "evidence": evidence, "synthetic_overlay": overlay,
            "cargo_condition_review": bool(reefer and abs(temp - setpoint) > state["config"]["temperature_deviation_c"]),
        })
    initial = evaluate(state)
    state["task_history"] = {task["id"]: deepcopy(task) for task in initial["tasks"]}
    return state


def _feasibility(blocked: list[str], unknown: list[str], success: str) -> dict[str, Any]:
    return {"status": "blocked" if blocked else "unknown" if unknown else "allowed",
            "reasons": blocked + unknown if blocked or unknown else [success]}


def _resources(state: dict[str, Any]) -> list[dict[str, Any]]:
    east = {"open": 4, "restricted": 2, "closed": 0}[state["incident"]["status"]]
    per_lane = state["config"]["departures_per_lane_per_day"]
    return [
        {"id": "gate_east", "type": "gate", "label": "East gate", "gate": "East",
         "lanes_open": east, "capacity_per_day": east * per_lane, "status": state["incident"]["status"]},
        {"id": "gate_west", "type": "gate", "label": "West gate", "gate": "West",
         "lanes_open": 4, "capacity_per_day": 4 * per_lane, "status": "open"},
        {"id": "power_B", "type": "power", "label": "Zone B power", "zone": "B",
         "enabled": state["power"]["B"], "status": "online" if state["power"]["B"] else "offline"},
        {"id": "customs", "type": "connectivity", "label": "Customs feed",
         "online": state["customs_online"], "status": "online" if state["customs_online"] else "offline"},
    ]


def _fee(container: dict[str, Any]) -> float:
    raw = container["raw"]
    return 0.0 if float(raw.get("free_days_left", 0)) > 0 else max(0.0, float(raw.get("demurrage_usd_per_day", 0)))


def _arrival(container: dict[str, Any]) -> tuple[str, str]:
    return str(container["raw"].get("arrived_at", "")), container["container_id"]


def _comparison(containers: list[dict[str, Any]], resources: list[dict[str, Any]],
                per_lane: int) -> dict[str, Any]:
    capacities = {r["gate"]: r["capacity_per_day"] for r in resources if r["type"] == "gate"}
    eligible = [c for c in containers if c["departure"]["status"] == "allowed"]
    excluded = [c for c in containers if c["departure"]["status"] != "allowed"]
    result: dict[str, Any] = {
        "label": "Synthetic one-day dispatch/fee proxy; not actual savings",
        "horizon_days": 1, "lane_capacity_per_day": per_lane, "gate_capacity": capacities,
        "eligible_container_ids": sorted(c["container_id"] for c in eligible),
        "excluded_container_ids": sorted(c["container_id"] for c in excluded),
        "assumptions": ["Same departure-eligible set and gate-specific capacities for both strategies.",
                        "Inspection, maintenance, holds and unknown clearance do not count as gate exits.",
                        "Only currently accruing daily fees are counted; positive free days incur zero in this proxy.",
                        "No forecast of holds clearing, free-time expiry, fee waivers, new arrivals or cargo damage."],
    }
    for strategy in ("fifo", "priority"):
        selected: list[dict[str, Any]] = []
        for gate, capacity in capacities.items():
            group = [c for c in eligible if c["gate"] == gate]
            if strategy == "fifo":
                group.sort(key=_arrival)
            else:
                group.sort(key=lambda c: (PRIORITY_ORDER[c["priority_band"]], -_fee(c), *_arrival(c)))
            selected.extend(group[:capacity])
        selected_ids = {c["container_id"] for c in selected}
        remaining = [c for c in containers if c["container_id"] not in selected_ids]
        result[strategy] = {
            "selected_ids": [c["container_id"] for c in selected],
            "remaining_ids": [c["container_id"] for c in remaining],
            "eligible_remaining_ids": [c["container_id"] for c in eligible if c["container_id"] not in selected_ids],
            "selected_count": len(selected), "remaining_count": len(remaining),
            "modeled_remaining_fee_usd": round(sum(_fee(c) for c in remaining), 2),
        }
    result["modeled_fee_difference_usd"] = round(
        result["fifo"]["modeled_remaining_fee_usd"] - result["priority"]["modeled_remaining_fee_usd"], 2)
    return result


def evaluate(state: dict[str, Any]) -> dict[str, Any]:
    """Return a new advisory snapshot; evaluating never mutates state."""
    now, config = state["simulated_at"], state["config"]
    resources = _resources(state)
    all_tasks: list[dict[str, Any]] = []
    evaluated: list[dict[str, Any]] = []
    for record in state["containers"]:
        cid, ev = record["container_id"], deepcopy(record["evidence"])
        blocked: list[str] = []
        unknown: list[str] = []
        tasks: list[dict[str, Any]] = []
        maintenance = _feasibility([], [], "In-place checks are allowed by the simulator; site access and safe-work procedures still apply.")
        onsite_move = _feasibility([], ["No explicit authorization for an on-site physical move is recorded."], "")

        def task(kind: str, title: str, owner: str, priority: str, reason: str,
                 next_step: str, required: str, sources: list[str],
                 feasibility: dict[str, Any] | None = None) -> None:
            task_id = f"{cid}:{kind}"
            historical = state.get("task_history", {}).get(task_id, {})
            old_active = historical.get("status") != "resolved"
            tasks.append({
                "id": task_id, "container_id": cid, "kind": kind, "title": title,
                "owner": owner, "priority_band": priority,
                "status": state.get("task_status", {}).get(task_id, "open") if old_active else "open",
                "reason": reason, "next_step": next_step, "required_evidence": required,
                "feasibility": deepcopy(feasibility if feasibility is not None else maintenance),
                "evidence_ids": [ev[s]["id"] for s in sources if s in ev],
                "first_seen_at": historical.get("first_seen_at", now), "resolved_at": None,
            })

        for source, item in ev.items():
            limit = config["reefer_fresh_minutes"] if source == "reefer" else config["record_fresh_minutes"]
            item["fresh"] = _fresh(item["observed_at"], now, limit)
            if not item["fresh"]:
                item["quality"] = "stale"
            elif source == "customs" and not state["customs_online"]:
                item["quality"] = "cached_offline"
            else:
                item["quality"] = "simulated_verified" if item.get("verified_report") else "simulated"

        carrier, scale, customs = (ev[s]["value"] for s in ("carrier", "scale", "customs"))
        scale_valid = (scale.get("unit") == "kg" and scale.get("weight_basis") == "container_gross"
                       and scale.get("identity_verified") is True and scale.get("measurement_verified") is True)
        comparable = scale_valid and carrier.get("unit") == "kg" and carrier.get("weight_basis") == "container_gross"
        if not comparable:
            unknown.append("Weight identity, units or measurement basis are unverified.")
            task("verify_weight_basis", "Verify the weighing basis", "Weighing / gate coordinator", "high",
                 "A raw scale value cannot be compared until identity, units, tare and vehicle deductions are verified.",
                 "Confirm the container and whether the report includes tractor/chassis; obtain a verified report.",
                 "Matched container-only kg report and declaration", ["carrier", "scale"])
        else:
            actual, declared = scale["container_weight_kg"], carrier["declared_weight_kg"]
            tolerance = max(config["weight_tolerance_kg"], max(actual, declared) * config["weight_tolerance_fraction"])
            mismatch = (carrier["declared_status"] == "empty" and actual > scale["tare_kg"] + config["weight_tolerance_kg"]
                        or abs(actual - declared) > tolerance)
            if mismatch:
                blocked.append("Unresolved declaration/weight discrepancy blocks simulated departure.")
                task("weight_review", "Reconcile empty / weight evidence", "Carrier + weighing coordinator", "high",
                     f"Declaration: {carrier['declared_status']}, {declared:,.0f} kg; container-only scale: {actual:,.0f} kg; simulated tare: {scale['tare_kg']:,.0f} kg.",
                     "Check matched records and request a verified reweigh or corrected declaration; arrange authorized inspection if needed.",
                     "Reconciled simulated scale and carrier report", ["carrier", "scale"])
        if not ev["scale"]["fresh"] or not ev["carrier"]["fresh"]:
            unknown.append("Weight or declaration evidence is stale.")
            task("refresh_weight", "Refresh weight / declaration evidence", "Carrier + weighing coordinator", "high",
                 "The stored report exceeds the configured freshness window.", "Obtain a current matched report.",
                 "Fresh verified weight and declaration", ["carrier", "scale"])

        if customs["hold"]:
            blocked.append("Known customs hold remains in force in the simulation.")
            task("customs_hold", "Resolve the customs prerequisite", "Customs liaison / authorized agency", "high",
                 "A recorded hold remains blocking even when the customs connection is offline.",
                 "Contact the authorized party and await a new customs notice; a local task status cannot remove a hold.",
                 "New simulated customs notice reporting no hold", ["customs"],
                 _feasibility([], ["Resolution requires an authorized customs notice."], ""))
        if not state["customs_online"] or not ev["customs"]["fresh"]:
            unknown.append("Current customs status cannot be confirmed.")
            task("verify_customs", "Verify current customs status", "Customs liaison", "high",
                 "The connection is offline or the stored notice is stale; a prior no-hold report is insufficient.",
                 "Restore connectivity and obtain a fresh simulated customs notice.", "Fresh notice while feed is online", ["customs"],
                 _feasibility(["Customs feed is offline."] if not state["customs_online"] else [], [], "Feed is available for a new notice."))

        if record["gate"] == "East" and state["incident"]["status"] == "closed":
            blocked.append("East access road is closed; this container cannot use West gate under demo topology.")
            task("access_restoration", "Wait for East access restoration", "Terminal operations / incident coordinator", "high",
                 "The assigned external access route is closed.",
                 "Keep this departure queued; use available West capacity only for independently eligible West containers.",
                 "Road restriction updated to restricted or open", [],
                 _feasibility(["Assigned gate access is closed."], [], ""))

        reefer = ev.get("reefer")
        if reefer:
            reading = reefer["value"]
            deviation = abs(reading["temp_c"] - reading["setpoint_c"])
            if deviation > config["temperature_deviation_c"]:
                blocked.append("Recorded temperature excursion requires an operational response.")
                task("reefer_alarm", "Respond to reefer temperature alarm", "Reefer technician / duty coordinator", "critical",
                     f"{'Current' if reefer['fresh'] else 'Last recorded'} reading {reading['temp_c']:.1f} C versus {reading['setpoint_c']:.1f} C setpoint; demo deviation threshold exceeded.",
                     "Check the reefer and power in place, obtain a fresh reading and involve the cargo specialist. Any physical move requires separate approval.",
                     "Fresh telemetry within the demo threshold", ["reefer"])
            if not reefer["fresh"]:
                unknown.append("Reefer telemetry is stale; present condition is unknown.")
                task("verify_reefer", "Obtain fresh reefer telemetry", "Reefer technician", "high",
                     "The last ping exceeds the demo freshness window. Silence is not a normal temperature reading.",
                     "Check connectivity and obtain a current reading.", "Fresh temperature evidence", ["reefer"])
            if not state["power"][record["zone"]]:
                blocked.append(f"Zone {record['zone']} power is unavailable.")
                task("power_response", "Restore reefer power / request an approved alternative", "Electrical + reefer operations", "critical",
                     "The modeled power resource is offline; cargo damage is not estimated.",
                     "Coordinate safe power restoration. Request authorization before moving a held container to powered storage.",
                     "Power resource restored or separately authorized alternative", ["reefer"])
            if record["cargo_condition_review"]:
                unknown.append("Cargo condition has not been assessed after the recorded temperature excursion.")
                task("cargo_condition_review", "Request cargo-condition assessment", "Cargo owner / qualified cargo specialist", "high",
                     "A recovered sensor reading does not establish cargo quality or clear a separate cargo hold.",
                     "Request the specialist's disposition; this demo does not fabricate cargo acceptance.",
                     "External specialist assessment (not modeled by the demo)", ["reefer"],
                     _feasibility([], ["No specialist disposition is recorded."], ""))

        if not ev["readiness"]["fresh"]:
            unknown.append("Appointment, payment and document assumptions need re-verification.")
            task("verify_readiness", "Refresh dispatch prerequisites", "Gate / documentation coordinator", "normal",
                 "Seed readiness assumptions have aged beyond the demo window.",
                 "Recheck appointment, payments and documents with their owners.",
                 "Current independent readiness evidence", ["readiness"])
        for prerequisite, ready in ev["readiness"]["value"].items():
            if ready is not True:
                unknown.append(f"Unverified dispatch prerequisite: {prerequisite}.")
        departure = _feasibility(blocked, unknown, "All modeled prerequisites pass; eligible for simulated operator dispatch review only.")
        active_bands = [t["priority_band"] for t in tasks]
        priority = min(active_bands, key=PRIORITY_ORDER.__getitem__) if active_bands else "normal"
        if priority == "normal" and _fee(record) > 0:
            priority = "high"
        reason = next((t["title"] for t in tasks if t["priority_band"] == priority),
                      "Currently accruing modeled fees" if priority == "high" else "Routine dispatch review")
        tasks.sort(key=lambda t: (PRIORITY_ORDER[t["priority_band"]], t["id"]))
        evaluated.append({
            "container_id": cid, "cargo_type": record["cargo_type"], "zone": record["zone"], "gate": record["gate"],
            "priority_band": priority, "priority_reason": reason, "departure": departure,
            "maintenance": maintenance, "onsite_move": onsite_move,
            "evidence": list(ev.values()), "tasks": tasks, "raw": deepcopy(record["raw"]),
            "synthetic_overlay": deepcopy(record["synthetic_overlay"]),
        })
        all_tasks.extend(tasks)

    active_ids = {t["id"] for t in all_tasks}
    # Resolved records remain inspectable; status changes never themselves resolve rules.
    for old_id, old_task in state.get("task_history", {}).items():
        if old_id not in active_ids:
            resolved = deepcopy(old_task)
            resolved["status"] = "resolved"
            resolved["resolved_at"] = resolved.get("resolved_at") or now
            all_tasks.append(resolved)
    all_tasks.sort(key=lambda t: (t["status"] == "resolved", PRIORITY_ORDER[t["priority_band"]], t["id"]))
    evaluated.sort(key=lambda c: (PRIORITY_ORDER[c["priority_band"]], c["container_id"]))
    for container in evaluated:
        container["tasks"] = [deepcopy(t) for t in all_tasks if t["container_id"] == container["container_id"]]
    active = [t for t in all_tasks if t["status"] != "resolved"]
    return {
        "rule_version": state["rule_version"], "simulated_at": now, "hero_id": state["hero_id"],
        "assumptions": deepcopy(state["assumptions"]),
        "overview": {"total_containers": len(evaluated), "urgent_tasks": sum(t["priority_band"] == "critical" for t in active),
                     "open_tasks": len(active), "resolved_tasks": len(all_tasks) - len(active),
                     "eligible_departures": sum(c["departure"]["status"] == "allowed" for c in evaluated),
                     "blocked_departures": sum(c["departure"]["status"] == "blocked" for c in evaluated),
                     "unknown_departures": sum(c["departure"]["status"] == "unknown" for c in evaluated),
                     "lanes_open": sum(r["lanes_open"] for r in resources if r["type"] == "gate")},
        "resources": resources, "incidents": [deepcopy(state["incident"])],
        "containers": evaluated, "tasks": all_tasks,
        "comparison": _comparison(evaluated, resources, config["departures_per_lane_per_day"]),
    }


def apply_event(state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    """Validate and atomically apply a simulated event to a deep copy.

    Preferred envelope: ``{"type": "power.set", "payload": {"zone": "B", ...}}``.
    Flat payloads are accepted too. Revision/idempotency/audit storage belong to
    the API session layer; repeated evidence never creates duplicate task IDs.
    """
    if not isinstance(event, dict) or not isinstance(event.get("type"), str):
        raise ValueError("event must have a string type")
    kind = event["type"]
    payload = event.get("payload", {k: v for k, v in event.items() if k != "type"})
    if not isinstance(payload, dict):
        raise ValueError("event payload must be an object")
    result = deepcopy(state)
    now = result["simulated_at"]

    def required(key: str) -> Any:
        if key not in payload:
            raise ValueError(f"Missing {key}")
        return payload[key]

    def note() -> str:
        value = required("note")
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError("note must be non-empty text of at most 2000 characters")
        return value.strip()

    def find_container() -> dict[str, Any]:
        cid = required("container_id")
        for item in result["containers"]:
            if item["container_id"] == cid:
                return item
        raise ValueError("Unknown container_id")

    if kind == "incident.set":
        if required("incident_id") != "access_road" or required("status") not in {"closed", "restricted", "open"}:
            raise ValueError("Unsupported incident or incident status")
        result["incident"]["status"] = payload["status"]
    elif kind == "power.set":
        if required("zone") != "B" or type(required("enabled")) is not bool:
            raise ValueError("Only zone B supports power events, with a boolean enabled")
        result["power"]["B"] = payload["enabled"]
    elif kind == "customs.connectivity":
        if type(required("online")) is not bool:
            raise ValueError("online must be a boolean")
        result["customs_online"] = payload["online"]
    elif kind == "evidence.weight":
        record = find_container()
        actual = _number(required("container_weight_kg"), "container_weight_kg", nonnegative=True)
        declared = _number(required("declared_weight_kg"), "declared_weight_kg", nonnegative=True)
        status, explanation = required("declared_status"), note()
        if status not in {"empty", "laden"}:
            raise ValueError("declared_status must be empty or laden")
        for source in ("scale", "carrier"):
            record["evidence"][source].update(observed_at=now, verified_report=True,
                detail="Simulated verified report: " + explanation)
        record["evidence"]["scale"]["value"].update(container_weight_kg=actual, unit="kg",
            weight_basis="container_gross", identity_verified=True, measurement_verified=True)
        record["evidence"]["carrier"]["value"].update(declared_weight_kg=declared, declared_status=status,
            unit="kg", weight_basis="container_gross")
    elif kind == "evidence.reefer":
        record = find_container()
        if "reefer" not in record["evidence"]:
            raise ValueError("This container has no reefer telemetry")
        temperature, explanation = _number(required("temp_c"), "temp_c"), note()
        item = record["evidence"]["reefer"]
        item.update(observed_at=now, verified_report=True, detail="Simulated fresh reading: " + explanation)
        item["value"]["temp_c"] = temperature
        if abs(temperature - item["value"]["setpoint_c"]) > result["config"]["temperature_deviation_c"]:
            record["cargo_condition_review"] = True
    elif kind == "evidence.customs":
        if not result["customs_online"]:
            raise ValueError("Cannot receive a customs notice while the simulated feed is offline")
        record = find_container()
        hold, explanation = required("hold"), note()
        if type(hold) is not bool:
            raise ValueError("hold must be a boolean")
        item = record["evidence"]["customs"]
        item.update(observed_at=now, verified_report=True, detail="Simulated authoritative customs notice: " + explanation)
        item["value"] = {"hold": hold, "hold_type": "simulated_review" if hold else "none"}
    elif kind == "task.update":
        task_id, status = required("task_id"), required("status")
        active = {t["id"] for t in evaluate(result)["tasks"] if t["status"] != "resolved"}
        if task_id not in active:
            raise ValueError("Unknown or resolved task_id")
        if status not in MANUAL_STATUSES:
            raise ValueError("Task status may be acknowledged, in_progress or waiting; evidence resolves tasks")
        result["task_status"][task_id] = status
    elif kind == "clock.advance":
        minutes = required("minutes")
        if type(minutes) is not int or not 1 <= minutes <= 120:
            raise ValueError("minutes must be an integer from 1 to 120")
        result["simulated_at"] = (_time(now) + timedelta(minutes=minutes)).isoformat()
    else:
        raise ValueError("Unsupported event type")
    snapshot = evaluate(result)
    result["task_history"] = {t["id"]: deepcopy(t) for t in snapshot["tasks"]}
    result["task_status"] = {key: value for key, value in result["task_status"].items()
                             if result["task_history"].get(key, {}).get("status") != "resolved"}
    return result
