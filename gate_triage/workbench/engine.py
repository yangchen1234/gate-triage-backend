"""Deterministic, JSON-persistable operational workbench.

Provider-shaped fixtures and operator observations deliberately stay separate.  A
coordination task is never authority to clear a hold.  All physical inputs and
operations in this module are explicitly synthetic.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PACK = Path(__file__).resolve().parents[2] / "docs" / "reference-pack"
PROVIDER_FIELDS = {"availability_known", "available_for_pickup", "holds_at_pod_terminal",
                   "pickup_lfd", "fees_at_pod_terminal", "import_deadlines"}
SCENARIO_NAMES = {
    "normal_operations": ("Everyday operations", "Resolve ordinary exceptions while keeping eligible handoffs moving."),
    "battery_truck_access_2024": ("Access disruption · 2024-inspired", "East access closes, partially recovers, then reopens; West operations continue."),
    "terminal_data_disruption_2017": ("Data disruption · 2017-inspired", "Separate provider connectivity from independently reported gate availability."),
    "long_dwell_backlog_2021": ("Long-dwell backlog · 2021-inspired", "A compressed demand surge tests queue fairness and recovery."),
    "weather_warning_no_closure_2023": ("Weather warning · 2023-inspired", "A warning alone must not create an unsupported closure."),
    "equal_service_control": ("Equal-service control", "Two identical lanes, five-minute service, 100 ready containers. Expected: 96 in four hours."),
}
ASSUMPTIONS = [
    "All container records, sensor observations, arrivals, resources and service durations are synthetic.",
    "Historical events supply context, never a reconstruction of actual cargo or terminal performance.",
    "Only completed, valid simulated gate handoffs count as throughput; checks and contacts do not.",
    "The planner sees observations received by the current clock, not future arrivals or recovery events.",
    "Provider pickup availability is not physical movement authority; additional simulated prerequisites apply.",
    "Weight and temperature thresholds are explicit demo review policies, not universal regulatory thresholds.",
]
TASK_META = {
    "weight_check": ("Verify weight and declaration", "terminal_operations", "Confirm container identity, weighing basis, tare and declaration; obtain a verified result.", ["Verified identity and weighing basis", "Reconciled carrier declaration"]),
    "reefer_check": ("Check reefer condition", "reefer_technician", "Confirm power and current readings; record a technician observation. Cargo quality requires separate authority.", ["Current temperature observation", "Technician condition report"]),
    "coordinate_hold": ("Coordinate reported hold", "customs_broker", "Contact the responsible authority and wait for a newer source report; acknowledgment cannot remove the hold.", ["Newer provider clearance report"]),
    "verify_availability": ("Verify pickup readiness", "carrier_contact", "Request current availability and check appointments, payment and documents.", ["Current known provider pickup status"]),
    "reconcile_lfd": ("Reconcile free-time dates", "carrier_contact", "Keep both dates and ask the issuing party to confirm the applicable deadline.", ["Confirmed applicable free-time date"]),
    "gate_handoff": ("Complete gate handoff", "terminal_operations", "Proceed only when every departure prerequisite and lane condition permits the operation.", ["Current departure eligibility", "Compatible open lane"]),
}


def _read(path: Path) -> Any:
    return json.loads(path.read_text())


def scenario_catalog() -> list[dict]:
    result = []
    for key, (name, description) in SCENARIO_NAMES.items():
        config = _read(PACK / "scenarios" / f"{key}.json")
        result.append({"id": key, "scenario_id": key, "name": name, "description": description,
                       "horizon_minutes": config["horizon_minutes"], "historical_facts": config["provenance"],
                       "source_refs": config["provenance"].get("source_refs", []), "assumptions": ASSUMPTIONS})
    return result


def _at(state: dict, minute: int | float | None = None) -> str:
    return (datetime.fromisoformat(state["start_at"]) + timedelta(minutes=state["clock_min"] if minute is None else minute)).isoformat()


def _event(state: dict, kind: str, title: str, detail: str, container_id: str | None = None, source: str = "simulation") -> None:
    seq = state["sequence"] = state.get("sequence", 0) + 1
    row = {"id": f"event-{seq}", "at_min": state["clock_min"], "type": kind, "title": title, "detail": detail, "source": source}
    if container_id:
        row["container_id"] = container_id
    state["timeline"].append(row)


def _sample(seed: int, key: str, model: dict) -> int:
    digest = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    values = model["minutes"]
    if model["distribution"] == "constant":
        return int(values[0])
    lo, mode, hi = values
    return max(1, int(round(rng.triangular(lo, hi, mode))))


def create_state(scenario_id: str, seed: int = 17, mode: str = "SIMULATION") -> dict:
    if scenario_id not in SCENARIO_NAMES:
        raise ValueError("Unknown scenario")
    if mode == "REPLAY":
        mode = "REPLAY_T49"
    if mode not in {"SIMULATION", "REPLAY_T49"}:
        raise ValueError("Only SIMULATION and REPLAY are available in the synthetic workbench")
    config = _read(PACK / "scenarios" / f"{scenario_id}.json")
    fixture = _read(PACK / config["containers_fixture"]["path"])
    overlay = _read(PACK / config["containers_fixture"]["overlay_path"])
    provider = {r["attributes"]["number"]: r for r in fixture["response"]["data"]}
    state = {
        "version": "workbench-1", "engine_revision": 4, "scenario_id": scenario_id, "scenario_name": SCENARIO_NAMES[scenario_id][0],
        "seed": int(seed), "mode": mode, "clock_min": 0, "start_at": config["start_at"],
        "horizon_minutes": config["horizon_minutes"], "config": config, "hero_id": overlay["hero_id"],
        "containers": {}, "operations": {}, "resources": {}, "timeline": [], "sequence": 0,
        "processed_events": [], "evidence_ids": [], "provider_online": True, "customs_online": True,
        "power_enabled": True, "completed": [], "running": [], "execution_log": [], "plan": None,
        "metrics": {"invalid_action_attempts": 0, "new_information_rejections": 0, "constraint_violations": 0},
        "curves": [{"minute": 0, "completed_handoffs": 0, "backlog": 100}], "demand_multiplier": 1,
        "policy": {"weight_tolerance_kg": 1000, "reefer_delta_c": 2, "source_freshness_minutes": 60},
        "feed": {"online": True, "latency_minutes": 0, "last_received_min": 0, "events_received": 100, "duplicates_ignored": 0, "delayed_events": 0},
        "feed_inbox": [], "feed_queue": [], "feed_processed": {},
    }
    for resource in config["resources"]:
        state["resources"][resource["id"]] = {**resource, "label": resource["id"].replace("-", " ").title(), "available_capacity": resource["capacity"], "status": "open"}
    for item in overlay["containers"]:
        number = item["container_id"]
        source = provider[number]
        attrs = copy.deepcopy(source["attributes"])
        c = {"id": source["id"], "container_id": number, "provider": attrs, "site": copy.deepcopy(item["site_evidence"]),
             "gate": item["gate"], "arrival_at_min": item["arrival_at_min"], "original_arrival_at_min": item["arrival_at_min"],
             "stakeholder_group": item["stakeholder_group"], "prerequisites": copy.deepcopy(item["simulated_prerequisites"]),
             "jobs": [j["id"] for j in item["jobs"]], "task_status": {}, "provider_checked_min": 0, "provider_received_min": 0, "source_version": 0,
             "source_watermarks": {key: 0 for key in PROVIDER_FIELDS}, "source_receipts": {key: 0 for key in PROVIDER_FIELDS},
             "evidence_history": [], "completed_at_min": None, "gate_started_min": None, "arrived": item["arrival_at_min"] <= 0 and not attrs.get("pod_full_out_at"),
             "demonstration_flags": item.get("demonstration_flags", [])}
        # Source full-out observations are displayed separately; they do not count as this run's handoffs.
        state["containers"][number] = c
        for observation in c["site"].values():
            if isinstance(observation, dict):
                observation["received_at_min"] = 0
        for j in item["jobs"]:
            state["operations"][j["id"]] = {**copy.deepcopy(j), "container_id": number, "status": "pending",
                "duration": _sample(seed, j["id"], config["duration_models"][j["duration_model"]])}
    bootstrap = _provider_envelope(state, "bootstrap", 0)
    state["feed_inbox"].append(bootstrap)
    state["feed_processed"][bootstrap["id"]] = _envelope_hash(bootstrap)
    _event(state, "run.created", "Synthetic exercise ready", f"{len(state['containers'])} provider-shaped records loaded. Physical resources and observations come from a separate synthetic overlay.")
    from .spatial_simulation import initialize_in_place
    initialize_in_place(state)
    return state


def upgrade_state(state: dict) -> dict:
    """Pure compatibility projection for already-persisted demo workspaces.

    Never resets the clock, completed handoffs, user tasks or source evidence.
    The next successful command naturally persists the upgraded representation.
    """
    if state.get("engine_revision", 0) >= 4:
        return state
    upgraded = copy.deepcopy(state)
    upgraded["engine_revision"] = 4
    upgraded.setdefault("feed", {"online": upgraded.get("provider_online", True), "latency_minutes": 0,
                                 "last_received_min": upgraded.get("clock_min", 0), "events_received": 0,
                                 "duplicates_ignored": 0, "delayed_events": 0})
    for key, value in {"online": upgraded.get("provider_online", True), "latency_minutes": 0,
                       "last_received_min": upgraded.get("clock_min", 0), "events_received": 0,
                       "duplicates_ignored": 0, "delayed_events": 0}.items():
        upgraded["feed"].setdefault(key, value)
    upgraded.setdefault("feed_queue", [])
    upgraded.setdefault("feed_inbox", [])
    upgraded.setdefault("feed_processed", {})
    for c in upgraded["containers"].values():
        c.setdefault("source_version", 0)
        c.setdefault("source_watermarks", {key: c["source_version"] for key in ("availability_known", "available_for_pickup", "holds_at_pod_terminal")})
        for key in PROVIDER_FIELDS:
            # LFD/fee fields were immutable in earlier engine versions, so
            # their fixture observation is still at the exercise origin.
            c["source_watermarks"].setdefault(key, 0)
        c.setdefault("source_receipts", {})
        for key in PROVIDER_FIELDS:
            # Older states cannot reconstruct per-field receipt timestamps.
            # Preserve unknown rather than inventing a recent receipt.
            c["source_receipts"].setdefault(key, None)
        c.setdefault("provider_received_min", c.get("provider_checked_min", 0))
        c.setdefault("evidence_history", [])
        for observation in c["site"].values():
            if isinstance(observation, dict):
                observation.setdefault("received_at_min", 0)
    if not upgraded["feed_inbox"]:
        envelope = _provider_envelope(upgraded, f"migration-bootstrap:{upgraded['clock_min']}", upgraded["clock_min"])
        upgraded["feed_inbox"].append(envelope)
        upgraded["feed_processed"][envelope["id"]] = _envelope_hash(envelope)
    for envelope in upgraded["feed_inbox"]:
        upgraded["feed_processed"].setdefault(envelope["id"], _envelope_hash(envelope))
    from .spatial_simulation import initialize_in_place
    initialize_in_place(upgraded)
    return upgraded


def _active_holds(c: dict) -> list[dict]:
    holds = c["provider"].get("holds_at_pod_terminal")
    return [h for h in holds or [] if str(h.get("status", "unknown")).lower() not in {"released", "clear", "cleared", "removed", "none"}]


def _weight_issue(state: dict, c: dict) -> tuple[bool, str]:
    w = c["site"].get("weight")
    if not w:
        return False, "No site weight observation"
    if w.get("unit") != "kg" or w.get("basis") != "container_gross" or not w.get("identity_verified") or not w.get("measurement_verified"):
        return True, "Confirm weight units, container identity and container-only weighing basis"
    measured = w.get("measured_kg")
    expected = w.get("tare_kg") if w.get("declared_status") == "empty" else w.get("declared_kg")
    if measured is None or expected is None:
        return True, "Weight evidence is incomplete"
    delta = abs(float(measured) - float(expected))
    return delta > state["policy"]["weight_tolerance_kg"], f"Measured {measured:,.0f} kg; {w.get('declared_status', 'declared')} reference {expected:,.0f} kg (demo review tolerance 1,000 kg)"


def _reefer_issue(state: dict, c: dict) -> tuple[bool, str]:
    r = c["site"].get("reefer")
    if not r:
        return False, "No live temperature observation available"
    delta = abs(float(r["temp_c"]) - float(r["setpoint_c"]))
    return delta >= state["policy"]["reefer_delta_c"], f"Observed {r['temp_c']:.1f}°C; configured setpoint {r['setpoint_c']:.1f}°C. A condition check does not certify cargo quality."


def _eligibility(state: dict, c: dict, *, include_lane: bool = True, physical: bool = False) -> dict:
    if c["completed_at_min"] is not None:
        return {"status": "blocked", "reasons": ["Handoff already completed in this run"]}
    reasons, unknown = [], []
    attrs = c["provider"]
    if attrs.get("pod_full_out_at"):
        reasons.append("Provider already reports this journey departed; do not schedule another handoff")
    holds = _active_holds(c)
    if holds:
        for h in holds:
            status = str(h.get("status", "unknown")).lower()
            if status in {"pending", "unknown", "unavailable"}:
                unknown.append(f"Reported {h.get('name', 'external')} {status} requires current confirmation")
            else:
                reasons.append(f"Reported {h.get('name', 'external')} {h.get('status', 'unknown')} remains in effect")
    if attrs.get("holds_at_pod_terminal") is None:
        unknown.append("Hold status is unknown")
    if not attrs.get("availability_known"):
        unknown.append("Provider pickup availability is unknown")
    elif not attrs.get("available_for_pickup"):
        reasons.append("Provider reports unavailable for pickup")
    if not state["provider_online"] and state["clock_min"] - c["provider_checked_min"] > state["policy"]["source_freshness_minutes"]:
        unknown.append("Provider evidence is stale during connectivity loss")
    if not state["customs_online"] and not holds:
        unknown.append("Current customs status cannot be verified during connectivity loss")
    w, wd = _weight_issue(state, c)
    r, rd = _reefer_issue(state, c)
    if w:
        reasons.append("Weight/declaration discrepancy requires verified evidence")
    if r:
        reasons.append("Reefer condition check remains unresolved")
    if not state["power_enabled"] and attrs.get("equipment_type") == "reefer":
        reasons.append("Simulated reefer power is unavailable; condition requires review")
    for key, value in c["prerequisites"].items():
        if value is not True:
            reasons.append(f"Simulated {key.replace('_', ' ')} is not confirmed")
    if not c["arrived"]:
        reasons.append("Vehicle has not arrived in the observed queue")
    if include_lane and not any(_available_capacity(state, r, physical=physical) > 0 for r in state["resources"].values() if r["kind"] == "gate_lane" and (c["gate"] == "Any" or r["gate"] == c["gate"])):
        reasons.append(f"No open compatible {c['gate']} lane")
    if reasons:
        return {"status": "blocked", "reasons": reasons + unknown}
    if unknown:
        return {"status": "unknown", "reasons": unknown}
    return {"status": "allowed", "reasons": ["All current simulated prerequisites are confirmed"]}


def _available_capacity(state: dict, resource: dict, *, physical: bool = False) -> int:
    cap = int(resource["available_capacity"])
    if resource["kind"] == "reefer_technician" and not state["power_enabled"]:
        return 0
    if physical:
        # The world enforces an effective closure even before its delayed notice is received.
        for event in state["config"]["events"]:
            if event["type"] == "resource.availability" and event["applies_at_min"] <= state["clock_min"] < event["observed_at_min"] and resource["id"] in event["resource_ids"]:
                slots = int(event["capacity"])
                index = event["resource_ids"].index(resource["id"])
                cap = min(cap, int(index < slots))
    return cap


def _priority(state: dict, c: dict) -> tuple[str, int]:
    warming, _ = _reefer_issue(state, c)
    weight, _ = _weight_issue(state, c)
    if warming:
        return "critical", 1000
    now = datetime.fromisoformat(_at(state))
    lfd = c["provider"].get("pickup_lfd")
    deadline = datetime.fromisoformat(lfd) if lfd else None
    overdue = deadline and (deadline <= now if deadline.tzinfo else deadline.date() <= now.date())
    age = max(0, state["clock_min"] - c["arrival_at_min"])
    return ("high" if weight or overdue or age >= 60 else "normal", int(250 * bool(overdue) + 180 * weight + min(age, 180)))


def _task(state: dict, c: dict, kind: str, issue: bool, detail: str, operation_id: str | None = None) -> dict:
    number = c["container_id"]
    tid = operation_id or f"{number}:{kind}"
    title, owner, next_step, evidence = TASK_META[kind]
    if kind == "coordinate_hold":
        names = " ".join(str(h.get("name", "")) for h in _active_holds(c)).lower()
        owner = "customs_broker" if any(x in names for x in ("customs", "agriculture", "government")) else "carrier_contact" if any(x in names for x in ("freight", "line", "carrier")) else "terminal_operations"
    operation = state["operations"].get(tid)
    stored = c["task_status"].get(tid)
    if kind == "gate_handoff":
        departure = _eligibility(state, c)
        done = c["completed_at_min"] is not None
        status = "resolved" if done else ("in_progress" if operation and operation["status"] == "running" else stored or "open")
        feasibility = {"status": "allowed" if departure["status"] == "allowed" else departure["status"], "reasons": departure["reasons"]}
    else:
        status = "resolved" if not issue else ("in_progress" if operation and operation["status"] == "running" else "waiting_external" if operation and operation["status"] == "completed" else stored or "open")
        blocked = kind == "reefer_check" and not state["power_enabled"]
        feasibility = {"status": "blocked" if blocked else "allowed", "reasons": ["Simulated power unavailable; coordinate maintenance"] if blocked else ["Coordination is permitted; completing this task does not grant departure permission"]}
    band, score = _priority(state, c)
    if kind not in {"reefer_check", "gate_handoff"} and band == "critical":
        band = "high"
    return {"id": tid, "container_id": number, "kind": kind, "title": title, "owner_role": owner,
            "status": status, "priority_band": band, "priority_score": score, "reason": detail,
            "next_step": next_step, "required_evidence": evidence, "feasibility": feasibility,
            "arrived": c["arrived"], "operation_id": operation_id}


def _tasks_for(state: dict, c: dict) -> list[dict]:
    if c["provider"].get("pod_full_out_at"):
        return []
    tasks = []
    weight, wd = _weight_issue(state, c)
    reefer, rd = _reefer_issue(state, c)
    kinds = set()
    for oid in c["jobs"]:
        op = state["operations"][oid]
        kind = op["kind"]
        kinds.add(kind)
        issue, detail = (weight, wd) if kind == "weight_check" else (reefer, rd) if kind == "reefer_check" else (True, "Final simulated physical handoff; all dependencies and authorizations remain required")
        tasks.append(_task(state, c, kind, issue, detail, oid))
    for kind, flag, detail in [("weight_check", weight, wd), ("reefer_check", reefer, rd)]:
        if flag and kind not in kinds:
            tasks.append(_task(state, c, kind, True, detail))
    holds = _active_holds(c)
    if holds:
        tasks.append(_task(state, c, "coordinate_hold", True, "; ".join(f"{h.get('name')}: {h.get('status')}" for h in holds)))
    elif any(k.endswith(":coordinate_hold") for k in c["task_status"]):
        tasks.append(_task(state, c, "coordinate_hold", False, "Newer source evidence no longer reports a hold"))
    attrs = c["provider"]
    if not attrs.get("availability_known") or not attrs.get("available_for_pickup") or not state["provider_online"]:
        tasks.append(_task(state, c, "verify_availability", True, "Pickup status is unavailable, unknown or awaiting current source verification"))
    dates = attrs.get("import_deadlines") or {}
    distinct_dates = {v for v in dates.values() if v}
    if len(distinct_dates) > 1:
        tasks.append(_task(state, c, "reconcile_lfd", True, "Line and terminal free-time dates differ; both original values are retained"))
    return tasks


def _evidence(state: dict, c: dict) -> list[dict]:
    n, attrs = c["container_id"], c["provider"]
    result = []
    for field, label in [("availability_known", "Availability known"), ("available_for_pickup", "Reported pickup availability"), ("holds_at_pod_terminal", "Reported terminal holds"), ("pickup_lfd", "Pickup last free day"), ("import_deadlines", "Source-specific deadlines"), ("fees_at_pod_terminal", "Reported terminal fees")]:
        observed = c["source_watermarks"].get(field, 0)
        received = c["source_receipts"].get(field)
        result.append({"id": f"{n}:provider:{field}:{observed}", "source": "Terminal49-shaped synthetic fixture", "label": label,
                       "value": attrs.get(field), "observed_at": _at(state, observed), "received_at": _at(state, received) if received is not None else None,
                       "time_precision": "date" if field == "pickup_lfd" and isinstance(attrs.get(field), str) and len(attrs[field]) == 10 else "second",
                       "quality": "reported" if state["provider_online"] else "last_known", "detail": "Synthetic provider-shaped observation. Not a direct site sensor or physical authorization."})
    for kind in ("weight", "reefer"):
        if c["site"].get(kind):
            result.append({"id": f"{n}:operator:{kind}", "source": "Synthetic operator overlay", "label": "Site weight observation" if kind == "weight" else "Reefer condition observation",
                           "value": c["site"][kind], "observed_at": _at(state, c["site"][kind].get("observed_at_min", 0)), "received_at": _at(state, c["site"][kind].get("received_at_min", 0)),
                           "quality": "synthetic_verified" if kind == "weight" and c["site"][kind].get("measurement_verified") else "synthetic_reported",
                           "detail": "Separate invented site observation; Terminal49 does not provide these site sensor readings in the verified contract."})
    return result + c["evidence_history"]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo), 2)


def snapshot(state: dict) -> dict:
    state = upgrade_state(state)
    rows, tasks = [], []
    completed_waits, truck_turns, censored = [], [], []
    for c in state["containers"].values():
        ct = _tasks_for(state, c)
        tasks.extend(ct)
        band, score = _priority(state, c)
        departure = _eligibility(state, c)
        attrs = c["provider"]
        holds = _active_holds(c)
        if attrs.get("pod_full_out_at"):
            pickup = "REPORTED_DEPARTED"
        elif holds and all(str(h.get("status", "unknown")).lower() in {"pending", "unknown", "unavailable"} for h in holds):
            pickup = "PENDING_REVIEW" if any(str(h.get("status", "")).lower() == "pending" for h in holds) else "UNKNOWN_HOLD"
        elif holds and attrs.get("available_for_pickup"):
            pickup = "CONFLICT"
        elif holds:
            pickup = "REPORTED_HOLD"
        elif not attrs.get("availability_known"):
            pickup = "UNKNOWN"
        else:
            pickup = "REPORTED_AVAILABLE" if attrs.get("available_for_pickup") else "REPORTED_UNAVAILABLE"
        issues = [{"id": f"issue:{t['id']}", "kind": t["kind"], "title": t["title"], "detail": t["reason"], "severity": t["priority_band"], "status": "resolved" if t["status"] == "resolved" else "open"} for t in ct if t["kind"] != "gate_handoff"]
        row = {"id": c["id"], "container_id": c["container_id"], "number": c["container_id"], "gate": c["gate"], "cargo_type": attrs.get("equipment_type", "dry"),
               "stakeholder_group": c["stakeholder_group"], "priority_band": band, "priority_score": score, "pickup_state": pickup,
               "departure": departure, "issues": issues, "evidence": _evidence(state, c), "tasks": ct,
               "arrived_at": _at(state, c["arrival_at_min"]) if c["arrived"] else None, "arrival_at_min": c["arrival_at_min"] if c["arrived"] else None,
               "arrived": c["arrived"], "lfd": attrs.get("pickup_lfd"), "fees": attrs.get("fees_at_pod_terminal", []),
               "completed_at_min": c["completed_at_min"], "gate_started_min": c["gate_started_min"], "simulated_prerequisites": c["prerequisites"],
               "demonstration_flags": c["demonstration_flags"]}
        rows.append(row)
        if c["completed_at_min"] is not None:
            completed_waits.append(c["gate_started_min"] - c["arrival_at_min"])
            truck_turns.append(c["completed_at_min"] - c["arrival_at_min"])
        elif c["arrived"]:
            censored.append(state["clock_min"] - c["arrival_at_min"])
    rows.sort(key=lambda c: (c["container_id"] != state["hero_id"], {"critical": 0, "high": 1, "normal": 2}[c["priority_band"]], -c["priority_score"], c["container_id"]))
    active_tasks = [t for t in tasks if t["status"] not in {"resolved", "cancelled"} and t["kind"] != "gate_handoff"]
    completed = len(state["completed"])
    throughput = round(completed * 60 / state["clock_min"], 2) if state["clock_min"] else 0
    busy_resources: dict[str, int] = {}
    for running in state["running"]:
        for rid in running["resource_ids"]:
            busy_resources[rid] = busy_resources.get(rid, 0) + 1
    for order in state.get("spatial_operations", {}).get("workorders", []):
        if order["status"] == "in_progress":
            busy_resources[order["resource_id"]] = busy_resources.get(order["resource_id"], 0) + 1
    resources = [{**r, "available_capacity": _available_capacity(state, r), "busy_capacity": busy_resources.get(r["id"], 0), "status": "power_off" if r["kind"] == "reefer_technician" and not state["power_enabled"] else r["status"]} for r in state["resources"].values()]
    overview = {"total_containers": len(rows), "completed_handoffs": completed, "backlog": sum(c["arrived"] and c["completed_at_min"] is None for c in rows),
                "reported_departed": sum(c["pickup_state"] == "REPORTED_DEPARTED" for c in rows),
                "reported_available": sum(c["pickup_state"] == "REPORTED_AVAILABLE" for c in rows), "ready_departures": sum(c["departure"]["status"] == "allowed" for c in rows),
                "attention_tasks": len(active_tasks), "critical_tasks": sum(t["priority_band"] == "critical" for t in active_tasks),
                "lanes_open": sum(r["available_capacity"] for r in resources if r["kind"] == "gate_lane"), "throughput_per_hour": throughput,
                "avg_wait_minutes": round(sum(completed_waits) / len(completed_waits), 2) if completed_waits else 0,
                "p90_wait_minutes": percentile(completed_waits, .9)}
    groups = []
    for group in sorted({c["stakeholder_group"] for c in rows}):
        cs = [c for c in rows if c["stakeholder_group"] == group and c["arrived"]]
        waits = [((c["gate_started_min"] if c["gate_started_min"] is not None else state["clock_min"]) - c["arrival_at_min"]) for c in cs]
        groups.append({"group": group, "arrived": len(cs), "completed": sum(c["completed_at_min"] is not None for c in cs), "avg_wait_minutes": round(sum(waits)/len(waits),2) if waits else 0, "max_wait_minutes": max(waits, default=0)})
    metrics = {**state["metrics"], "actual_completed_handoffs": completed, "modeled_departures_per_hour": throughput,
               "completed_wait_sample_size": len(completed_waits), "avg_wait_minutes": overview["avg_wait_minutes"], "p90_wait_minutes": overview["p90_wait_minutes"],
               "unfinished_arrived": len(censored), "unfinished_wait_lower_bound_mean": round(sum(censored)/len(censored), 2) if censored else 0,
               "avg_truck_turn_minutes": round(sum(truck_turns)/len(truck_turns),2) if truck_turns else 0,
               "wait_definition": "Observed external arrival to gate-service start, completed samples only; unfinished waits shown separately.",
               "curves": state["curves"], "stakeholder_groups": groups,
               "provider_online": state["provider_online"], "customs_online": state["customs_online"], "power_enabled": state["power_enabled"]}
    current_plan = state.get("plan")
    from .scheduler import state_fingerprint
    if not current_plan or current_plan.get("input_clock_min") != state["clock_min"] or current_plan.get("input_state_hash") != state_fingerprint(state):
        current_plan = plan(state)
    from .spatial_simulation import spatial_snapshot
    return {"scenario_id": state["scenario_id"], "scenario_name": state["scenario_name"], "mode": state["mode"], "seed": state["seed"],
            "clock_min": state["clock_min"], "horizon_minutes": state["horizon_minutes"], "as_of": _at(state), "hero_id": state["hero_id"],
            "assumptions": ASSUMPTIONS, "overview": overview, "containers": rows, "tasks": tasks, "resources": resources,
            "timeline": list(reversed(state["timeline"][-150:])), "metrics": metrics, "plan": current_plan,
            "spatial_operations": spatial_snapshot(state),
            "spatial_incidents": copy.deepcopy(state.get("spatial_incidents", {})),
            "feed": {**state["feed"], "latency_minutes": state["clock_min"] - min(e["published_min"] for e in state["feed_queue"]) if state["feed_queue"] else 0, "queued_envelopes": len(state["feed_queue"]),
                     "oldest_queued_published_min": min((e["published_min"] for e in state["feed_queue"]), default=None)}}


def plan(state: dict, profile: str = "throughput", strategy: str = "optimized") -> dict:
    from .scheduler import make_plan
    return make_plan(upgrade_state(state), profile=profile, strategy=strategy)


def _resolve_evidence(state: dict, c: dict, kind: str, values: dict, *, source: str = "Synthetic operator report", published_min: int | None = None, evidence_id: str | None = None) -> bool:
    if kind not in {"weight", "reefer", "customs"}:
        raise ValueError("Unsupported evidence kind")
    if not isinstance(values, dict):
        raise ValueError("Evidence values must be an object")
    version = state["clock_min"] if published_min is None else published_min
    if kind == "customs":
        if version < c["source_version"]:
            _event(state, "evidence.stale", "Older evidence retained without overwriting current state", f"Source version {version} is older than current {c['source_version']}.", c["container_id"])
            return False
        allowed = {"holds", "holds_at_pod_terminal", "availability_known", "available_for_pickup"}
        if set(values) - allowed:
            raise ValueError("Customs evidence may only update source-reported hold/availability fields")
        if "holds" in values:
            if values["holds"] is not None and (not isinstance(values["holds"], list) or any(not isinstance(h, dict) for h in values["holds"])):
                raise ValueError("Reported holds must be an array of objects or null")
            c["provider"]["holds_at_pod_terminal"] = copy.deepcopy(values["holds"])
        for k in allowed - {"holds"}:
            if k in values:
                if k in {"availability_known", "available_for_pickup"} and type(values[k]) is not bool:
                    raise ValueError("Reported availability fields must be boolean")
                if k == "holds_at_pod_terminal" and values[k] is not None and (not isinstance(values[k], list) or any(not isinstance(h, dict) for h in values[k])):
                    raise ValueError("Reported holds must be an array of objects or null")
                c["provider"][k] = copy.deepcopy(values[k])
        c["source_version"] = version
        c["provider_checked_min"] = state["clock_min"]
        c["provider_received_min"] = state["clock_min"]
    else:
        allowed = {"declared_status", "declared_kg", "measured_kg", "identity_verified", "measurement_verified", "unit", "basis", "tare_kg"} if kind == "weight" else {"temp_c", "setpoint_c"}
        if set(values) - allowed:
            raise ValueError("Unexpected site evidence fields")
        merged = {**(c["site"].get(kind) or {}), **copy.deepcopy(values), "observed_at_min": state["clock_min"], "received_at_min": state["clock_min"]}
        if kind == "weight":
            for k in ("measured_kg", "declared_kg", "tare_kg"):
                if k in merged and (not isinstance(merged[k], (int, float)) or not math.isfinite(merged[k]) or merged[k] < 0):
                    raise ValueError("Weight observations must be finite nonnegative numbers")
        else:
            for k in ("temp_c", "setpoint_c"):
                if k not in merged or not isinstance(merged[k], (int, float)) or not math.isfinite(merged[k]) or not -100 <= merged[k] <= 100:
                    raise ValueError("Temperature observations must be finite numbers between -100 and 100°C")
        c["site"][kind] = merged
    eid = evidence_id or f"manual:{state['sequence'] + 1}"
    c["evidence_history"].append({"id": eid, "source": source, "label": f"New {kind} evidence", "value": values, "observed_at": _at(state, version), "received_at": _at(state), "quality": "synthetic_reported", "detail": "New synthetic evidence updates only its own fields; other blockers and permissions are preserved."})
    _event(state, "evidence.received", f"{kind.title()} evidence received", "Re-evaluated affected issues. Other holds, dependencies and simulated permissions remain independent.", c["container_id"], source)
    return True


def _envelope_hash(envelope: dict) -> str:
    return hashlib.sha256(json.dumps(envelope, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validate_json_value(value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError("Provider evidence nesting exceeds the supported limit")
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Provider evidence numbers must be finite")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json_value(item, depth + 1)
        return
    raise ValueError("Provider evidence must contain only JSON-compatible values")


def _validate_deadline(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("Deadline values must be ISO dates or timezone-aware ISO timestamps")
    try:
        parsed = datetime.fromisoformat(value)
        if len(value) != 10 and parsed.tzinfo is None:
            raise ValueError("Timestamp is missing its timezone")
    except ValueError:
        raise ValueError("Deadline values must be ISO dates or timezone-aware ISO timestamps") from None


def _validate_provider_patch(patch: Any) -> None:
    if not isinstance(patch, dict) or not patch or set(patch) - PROVIDER_FIELDS:
        raise ValueError("Provider evidence contains an unsupported field or empty patch")
    _validate_json_value(patch)
    for key, value in patch.items():
        if key in {"availability_known", "available_for_pickup"} and type(value) is not bool:
            raise ValueError("Reported availability fields must be boolean")
        if key == "holds_at_pod_terminal" and value is not None and (not isinstance(value, list) or len(value) > 100 or any(not isinstance(h, dict) for h in value)):
            raise ValueError("Reported holds must be an array of at most 100 objects or null")
        if key == "pickup_lfd":
            _validate_deadline(value)
        if key == "fees_at_pod_terminal" and value is not None and (not isinstance(value, list) or len(value) > 200 or any(not isinstance(fee, dict) for fee in value)):
            raise ValueError("Reported fees must be an array of at most 200 objects or null")
        if key == "import_deadlines":
            if value is not None and (not isinstance(value, dict) or set(value) - {"pickup_lfd_line", "pickup_lfd_terminal", "pickup_lfd_rail"}):
                raise ValueError("Import deadlines must contain supported source-specific date fields")
            for deadline in (value or {}).values():
                _validate_deadline(deadline)


def _provider_envelope(state: dict, event_id: str, published_min: int) -> dict:
    """Produce a real synthetic source snapshot, not a counter-only heartbeat."""
    return {"id": event_id, "published_min": published_min, "generated_at_min": state["clock_min"],
            "records": [{"container_id": c["container_id"], "patch": {k: copy.deepcopy(c["provider"].get(k)) for k in PROVIDER_FIELDS}} for c in state["containers"].values()]}


def _receive_provider_envelope(state: dict, envelope: dict, *, drain: bool = False) -> None:
    """One inbox path for scheduled updates, polling, duplicates and recovery.

    Business timestamps remain those of generation.  Receipt time is this
    simulation clock.  Duplicate IDs with changed bodies are quarantined.
    """
    eid, published = envelope.get("id"), envelope.get("published_min")
    if not isinstance(eid, str) or not 1 <= len(eid) <= 200 or type(published) is not int or not 0 <= published <= state["clock_min"]:
        raise ValueError("Provider envelope requires a valid ID and an already-observed business minute")
    if not isinstance(envelope.get("records"), list) or not 1 <= len(envelope["records"]) <= 100:
        raise ValueError("Provider envelope requires 1–100 records")
    for record in envelope["records"]:
        if not isinstance(record, dict) or record.get("container_id") not in state["containers"]:
            raise ValueError("Provider envelope references an unknown container")
        _validate_provider_patch(record.get("patch"))
    body_hash = _envelope_hash(envelope)
    if eid in state["feed_processed"]:
        if state["feed_processed"][eid] == body_hash:
            state["feed"]["duplicates_ignored"] += 1
            _event(state, "evidence.duplicate", "Duplicate provider envelope ignored", f"Envelope {eid} re-entered the same inbox; its payload hash matched, so no source projection or task was applied twice.", source="Synthetic provider inbox")
        else:
            _event(state, "evidence.quarantined", "Conflicting duplicate envelope quarantined", "An existing source ID arrived with a different payload. Current evidence was not overwritten.", source="Synthetic provider inbox")
        return
    if not state["provider_online"] and not drain:
        if not any(item["id"] == eid for item in state["feed_queue"]):
            state["feed_queue"].append(copy.deepcopy(envelope))
            state["feed"]["delayed_events"] += len(envelope["records"])
        state["feed"]["latency_minutes"] = max(0, state["clock_min"] - min(e["published_min"] for e in state["feed_queue"]))
        _event(state, "feed.queued", "Source envelope waiting in delayed delivery queue", f"{len(envelope['records'])} actual synthetic source observations queued; business timestamps retained.", source="Synthetic provider transport")
        return
    state["feed_processed"][eid] = body_hash
    state["feed_inbox"].append(copy.deepcopy(envelope))
    state["feed"]["last_received_min"] = state["clock_min"]
    state["feed"]["events_received"] += len(envelope["records"])
    stale = 0
    for record in envelope["records"]:
        c = state["containers"][record["container_id"]]
        published = envelope["published_min"]
        watermarks = c["source_watermarks"]
        receipts = c["source_receipts"]
        for key, value in record["patch"].items():
            if published < watermarks.get(key, 0):
                stale += 1
                continue
            c["provider"][key] = {**(c["provider"].get(key) or {}), **copy.deepcopy(value)} if key == "import_deadlines" and isinstance(value, dict) else copy.deepcopy(value)
            watermarks[key] = published
            receipts[key] = state["clock_min"]
        c["source_version"] = max(watermarks.values())
        c["provider_checked_min"] = max(c["provider_checked_min"], published)
        c["provider_received_min"] = state["clock_min"]
    _event(state, "feed.received", "Provider source envelope processed", f"{len(envelope['records'])} observations; published minute {envelope['published_min']}, received minute {state['clock_min']}; {stale} older observations retained without overwrite.", source="Terminal49-shaped synthetic inbox")


def _set_incident(state: dict, status: str, resource_ids: list[str] | None = None, capacity: int | None = None) -> None:
    if status not in {"closed", "restricted", "open"}:
        raise ValueError("Incident status must be closed, restricted or open")
    ids = resource_ids or [r["id"] for r in state["resources"].values() if r["kind"] == "gate_lane" and r["gate"] == "East"]
    total = (0 if status == "closed" else 1 if status == "restricted" else len(ids)) if capacity is None else capacity
    for i, rid in enumerate(ids):
        resource = state["resources"].get(rid)
        if not resource:
            raise ValueError("Unknown resource in incident")
        resource["available_capacity"] = min(resource["capacity"], max(0, total - i))
        resource["status"] = status if resource["available_capacity"] else "closed"
        resource["world_available_capacity"] = resource["available_capacity"]
        resource["world_status"] = resource["status"]
    from .spatial_simulation import reconcile_effects_in_place
    reconcile_effects_in_place(state)
    _event(state, "incident.changed", f"East access {status}", f"Only reported resource scope changes: {', '.join(ids)}. Other lanes, holds and authorizations are unchanged.", source="Synthetic incident report")


def apply_command(state: dict, command: dict) -> dict:
    if not isinstance(command, dict):
        raise ValueError("Command must be an object")
    new = copy.deepcopy(upgrade_state(state))
    name = command.get("command")
    if new["mode"] != "SIMULATION" and name in {"incident", "power", "customs_connectivity", "evidence", "feed", "select_plan", "spatial_incident"}:
        raise ValueError("Synthetic injections and physical plans require SIMULATION mode")
    if name == "advance":
        minutes = command.get("minutes", 15)
        if type(minutes) is not int or not 1 <= minutes <= 1440:
            raise ValueError("Advance must be 1–1440 integer minutes")
        if new["mode"] == "REPLAY_T49":
            # Replay projects only received evidence and never performs synthetic physical handoffs.
            _advance_replay(new, min(new["horizon_minutes"], new["clock_min"] + minutes))
        else:
            from .simulation import advance
            advance(new, minutes, command.get("strategy", "optimized"), command.get("profile", "throughput"))
    elif name == "seek":
        if new["mode"] != "REPLAY_T49":
            raise ValueError("Seek is available only in REPLAY mode")
        minute = command.get("minute")
        if type(minute) is not int or not 0 <= minute <= new["horizon_minutes"]:
            raise ValueError("Replay minute is outside the run horizon")
        new = create_state(new["scenario_id"], new["seed"], "REPLAY_T49")
        _advance_replay(new, minute)
    elif name == "reset":
        new = create_state(new["scenario_id"], new["seed"], new["mode"])
    elif name == "spatial_incident":
        from .spatial_simulation import apply_incident_effects, resolve_incident_effects
        incident = command.get("incident")
        if not isinstance(incident, dict):
            raise ValueError("A structured spatial incident is required")
        current = list(new.get("spatial_incidents", {}).values())
        if incident.get("status") == "resolved":
            return resolve_incident_effects(new, incident, [row for row in current if row["id"] != incident.get("id")])
        return apply_incident_effects(new, incident, current)
    elif name == "feed":
        action = command.get("action")
        if action == "delay":
            new["provider_online"] = False
            new["world_provider_online"] = False
            new["feed"]["online"] = False
            new["feed"]["latency_minutes"] = 0
            _receive_provider_envelope(new, _provider_envelope(new, f"poll:{new['clock_min']}:{new['sequence'] + 1}", new["clock_min"]))
            _event(new, "feed.delayed", "Provider stream delayed", "Synthetic provider polling is paused. Last-known holds remain, source freshness ages, and physical lanes remain independent.", source="Synthetic feed controller")
        elif action == "duplicate":
            _receive_provider_envelope(new, copy.deepcopy(new["feed_inbox"][-1]), drain=True)
        elif action == "recover":
            if any(effect.get("kind") == "feed_offline" for row in new.get("spatial_incidents", {}).values() if row.get("status") == "active" for effect in row.get("effects", [])):
                raise ValueError("Resolve the active confirmed feed incident before restoring provider transport")
            new["provider_online"] = True
            new["world_provider_online"] = True
            new["feed"]["online"] = True
            new["feed"]["latency_minutes"] = 0
            pending = new["feed_queue"]
            new["feed_queue"] = []
            for envelope in pending:
                _receive_provider_envelope(new, envelope, drain=True)
            _receive_provider_envelope(new, _provider_envelope(new, f"recovery:{new['clock_min']}:{new['sequence'] + 1}", new["clock_min"]), drain=True)
            _event(new, "feed.recovered", "Provider stream recovered", "Fresh synthetic source poll received. Existing field values and holds remain unchanged unless a newer observation updates them.", source="Synthetic feed controller")
        else:
            raise ValueError("Feed action must be delay, duplicate or recover")
    elif name == "select_plan":
        candidate = command.get("plan")
        if not isinstance(candidate, dict) or candidate.get("input_clock_min") != new["clock_min"]:
            raise ValueError("Plan input clock is stale or missing")
        if not candidate.get("input_state_hash"):
            raise ValueError("Plan input evidence hash is missing; generate a new plan")
        from .scheduler import validate_plan
        errors = validate_plan(new, candidate)
        if errors:
            raise ValueError("Plan rejected: " + "; ".join(errors))
        new["plan"] = copy.deepcopy(candidate)
        _event(new, "plan.selected", "Validated plan selected", f"{candidate.get('profile', 'throughput')} policy; projected operations remain conditional on execution-time guards.", source="Planner")
        return new
    elif name == "incident":
        if new["mode"] != "SIMULATION":
            raise ValueError("Incident injections require SIMULATION mode")
        _set_incident(new, command.get("status", ""))
    elif name == "power":
        if type(command.get("enabled")) is not bool:
            raise ValueError("Power enabled must be boolean")
        new["power_enabled"] = command["enabled"]
        _event(new, "power.changed", "Reefer power restored" if new["power_enabled"] else "Reefer power unavailable", "Synthetic reefer maintenance capacity and condition feasibility updated. Gate lanes are not implicitly closed.")
    elif name == "customs_connectivity":
        if type(command.get("online")) is not bool:
            raise ValueError("Customs online must be boolean")
        new["customs_online"] = command["online"]
        _event(new, "customs.connectivity", "Customs source online" if new["customs_online"] else "Customs source offline", "Known holds are retained. An outage cannot provide clearance.")
    elif name == "evidence":
        if new["mode"] != "SIMULATION":
            raise ValueError("Evidence injections require SIMULATION mode")
        c = new["containers"].get(command.get("container_id"))
        if c is None:
            c = next((row for row in new["containers"].values() if row["id"] == command.get("container_id")), None)
        if c is None:
            raise ValueError("Unknown container")
        if command.get("kind") in {"customs", "provider"}:
            values = command.get("values", {})
            if not isinstance(values, dict):
                raise ValueError("Evidence values must be an object")
            patch = {"holds_at_pod_terminal" if key == "holds" else key: value for key, value in values.items()}
            published = command.get("published_at_min", new["clock_min"])
            event_id = command.get("event_id", f"manual-provider:{new['clock_min']}:{new['sequence'] + 1}")
            _receive_provider_envelope(new, {"id": event_id, "published_min": published, "generated_at_min": published, "records": [{"container_id": c["container_id"], "patch": patch}]})
        else:
            _resolve_evidence(new, c, command.get("kind"), command.get("values", {}))
    elif name == "task":
        task_id, status = command.get("task_id"), command.get("status")
        if status is None:
            status = {"acknowledge": "acknowledged", "start": "in_progress", "wait": "waiting_external", "record_contact": "waiting_external", "record_result": "waiting_external"}.get(command.get("action"))
        if status not in {"acknowledged", "in_progress", "waiting_external"}:
            raise ValueError("Task commands may acknowledge, start coordination or wait; resolution requires new evidence")
        found = None
        for c in new["containers"].values():
            for task in _tasks_for(new, c):
                if task["id"] == task_id:
                    found = (c, task)
                    break
            if found:
                break
        if not found:
            raise ValueError("Unknown task")
        c, task = found
        if task["status"] == "resolved":
            raise ValueError("Resolved task cannot be reopened without a new issue")
        if task["kind"] == "gate_handoff":
            raise ValueError("Physical handoffs are started only by the validated simulator")
        c["task_status"][task_id] = status
        _event(new, "task.updated", f"{task['title']}: {status.replace('_', ' ')}", "Coordination record updated; no source evidence, hold or physical authorization changed.", c["container_id"], "Planner")
    else:
        raise ValueError("Unsupported command")
    if new["mode"] == "SIMULATION":
        from .spatial_simulation import reconcile_effects_in_place
        reconcile_effects_in_place(new)
        from .simulation import _cancel_unavailable
        _cancel_unavailable(new)
    previous = new.get("plan") or {}
    new["plan"] = plan(new, command.get("profile", previous.get("profile", "throughput")), command.get("strategy", previous.get("strategy", "optimized")))
    return new


def _apply_events(state: dict) -> bool:
    changed = False
    for event in state["config"]["events"]:
        if event["event_id"] in state["processed_events"] or event["observed_at_min"] > state["clock_min"]:
            continue
        state["processed_events"].append(event["event_id"])
        changed = True
        kind = event["type"]
        if kind == "resource.availability":
            _set_incident(state, event["state"], event["resource_ids"], event["capacity"])
        elif kind == "provider.connectivity":
            state["provider_online"] = event["state"] == "online"
            state["world_provider_online"] = state["provider_online"]
            from .spatial_simulation import reconcile_effects_in_place
            reconcile_effects_in_place(state)
            state["feed"]["online"] = state["provider_online"]
            if state["provider_online"]:
                pending = state["feed_queue"]
                state["feed_queue"] = []
                for envelope in pending:
                    _receive_provider_envelope(state, envelope, drain=True)
            _event(state, kind, f"Provider connectivity: {event['state']}", "Connectivity and physical resource availability are independent. Last-known holds are retained.", source="Synthetic provider monitor")
        elif kind == "evidence.update":
            eid = event["evidence_id"]
            c = state["containers"][event["container_id"]]
            if event["namespace"] == "provider":
                _receive_provider_envelope(state, {"id": eid, "published_min": event["published_at_min"], "generated_at_min": event["published_at_min"], "records": [{"container_id": c["container_id"], "patch": copy.deepcopy(event["patch"])}]}, drain=True)
            else:
                if eid in state["evidence_ids"]:
                    _event(state, "evidence.duplicate", "Duplicate site evidence ignored", "The same evidence ID cannot update a site observation twice.")
                    continue
                state["evidence_ids"].append(eid)
                for field, values in event["patch"].items():
                    _resolve_evidence(state, c, field, values, published_min=event["published_at_min"], evidence_id=eid)
        elif kind == "warning.received":
            _event(state, kind, event["code"].replace("_", " ").title(), event["message"], source="Synthetic warning report")
        elif kind == "demand.multiplier":
            state["demand_multiplier"] = event["multiplier"]
            if event["multiplier"] > 1:
                now, multiplier = state["clock_min"], event["multiplier"]
                for c in state["containers"].values():
                    if not c["arrived"]:
                        c["arrival_at_min"] = now + math.ceil((c["arrival_at_min"] - now) / multiplier)
            _event(state, kind, "Synthetic arrival intensity changed", f"Multiplier {event['multiplier']} applies only to not-yet-observed fixture arrivals. No historical fee is activated.")
    from .spatial_simulation import reconcile_effects_in_place
    reconcile_effects_in_place(state)
    return changed


def _observe_arrivals(state: dict) -> bool:
    arrived = []
    for c in state["containers"].values():
        if not c["arrived"] and not c["provider"].get("pod_full_out_at") and c["arrival_at_min"] <= state["clock_min"]:
            c["arrived"] = True
            arrived.append(c["container_id"])
    if arrived:
        _event(state, "queue.arrival", f"{len(arrived)} vehicle arrival{'s' if len(arrived) != 1 else ''}", ", ".join(arrived), source="Synthetic arrival process")
    if state["clock_min"] % 10 == 0:
        _receive_provider_envelope(state, _provider_envelope(state, f"poll:{state['clock_min']}", state["clock_min"]))
    return bool(arrived)


def _advance_replay(state: dict, target: int) -> None:
    while state["clock_min"] < target:
        state["clock_min"] += 1
        _apply_events(state)
        _observe_arrivals(state)
    state["plan"] = None


def experiment(scenario_id: str, seeds: list[int], horizon_minutes: int = 240) -> dict:
    from .simulation import run_experiment
    return run_experiment(scenario_id, seeds, horizon_minutes)
