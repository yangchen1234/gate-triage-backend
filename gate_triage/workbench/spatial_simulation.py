"""Explicitly synthetic spatial work orders and composable incident effects.

These quay/transit jobs are a separate illustrative pool. They are not the
Terminal49-shaped cohort, measured TEU, or additional gate handoffs. Geographic
references and incident proposals are owned by the spatial/emergency modules.
"""
from __future__ import annotations

import copy
from typing import Any

RESOURCE_DEFINITIONS = (
    {"id": "quay-crane-1", "kind": "quay_crane", "label": "Synthetic loading crane", "gate": "Any", "zone_id": "zone-vessel-load", "capacity": 1},
    {"id": "quay-crane-2", "kind": "quay_crane", "label": "Synthetic unloading crane", "gate": "Any", "zone_id": "zone-vessel-unload", "capacity": 1},
    {"id": "marine-channel-1", "kind": "marine_channel", "label": "Synthetic vessel transit slot", "gate": "Any", "zone_id": "zone-marine-channel", "capacity": 1},
)


def _log(state: dict, kind: str, title: str, detail: str) -> None:
    from .engine import _event
    _event(state, kind, title, detail, source="Synthetic spatial operations model")


def initialize_in_place(state: dict) -> None:
    if "spatial_operations" in state:
        return
    start = state["clock_min"]
    state.setdefault("spatial_incidents", {})
    state.setdefault("world_provider_online", state["provider_online"])
    for resource in state["resources"].values():
        resource.setdefault("world_available_capacity", resource["available_capacity"])
        resource.setdefault("world_status", resource["status"])
    state["spatial_operations"] = {
        "schema": "spatial-1", "initialized_at_min": start, "last_tick_min": start,
        "workorders": [], "marine_channel": {"world_status": "open", "status": "open"},
        "vessels": [{"id": "SIM-VESSEL-A", "label": "Synthetic vessel A", "initial_state": "berthed"},
                    {"id": "SIM-VESSEL-B", "label": "Synthetic vessel B", "initial_state": "off_terminal"}],
        "provenance": {"kind": "synthetic_operator_overlay", "description": "Illustrative vessel-work queue with invented resources, release times and durations; independent of the 100 tracked journeys.",
                       "counting": "Workorder completions only; not TEU, real vessel observations, or gate-handoff throughput."}}
    if state["mode"] != "SIMULATION":
        return
    for definition in RESOURCE_DEFINITIONS:
        state["resources"].setdefault(definition["id"], {**definition, "available_capacity": definition["capacity"],
                                                       "world_available_capacity": definition["capacity"], "status": "open", "world_status": "open", "provenance": "synthetic_operator_overlay"})
    from .engine import _sample
    workorders = state["spatial_operations"]["workorders"]
    def add(identifier: str, vessel: str, kind: str, resource: str, release: int, predecessors: list[str]) -> str:
        duration = 6 if kind == "vessel_arrival" else 5 if kind == "vessel_departure" else _sample(state["seed"], identifier, {"distribution": "triangular", "minutes": [8, 12, 18]})
        workorders.append({"id": identifier, "vessel_id": vessel, "kind": kind, "phase": kind.removeprefix("vessel_"),
                           "label": f"Synthetic {kind.removeprefix('vessel_')} work order", "resource_id": resource,
                           "zone_id": next(d["zone_id"] for d in RESOURCE_DEFINITIONS if d["id"] == resource),
                           "status": "queued", "release_at_min": start+release, "duration_minutes": duration,
                           "service_minutes": 0, "progress": 0.0, "start_min": None, "completed_at_min": None,
                           "predecessors": predecessors, "segments": [], "provenance": "synthetic_operator_overlay",
                           "container_id": None, "units": "one synthetic workorder"})
        return identifier
    au=[add(f"SIM-A-UNLOAD-{i:02}","SIM-VESSEL-A","vessel_unload","quay-crane-2",0,[]) for i in (1,2)]
    al=[add(f"SIM-A-LOAD-{i:02}","SIM-VESSEL-A","vessel_load","quay-crane-1",0,au) for i in (1,2)]
    add("SIM-A-DEPARTURE","SIM-VESSEL-A","vessel_departure","marine-channel-1",0,al)
    arrival=add("SIM-B-ARRIVAL","SIM-VESSEL-B","vessel_arrival","marine-channel-1",30,[])
    bu=[add(f"SIM-B-UNLOAD-{i:02}","SIM-VESSEL-B","vessel_unload","quay-crane-2",30,[arrival]) for i in (1,2)]
    bl=[add(f"SIM-B-LOAD-{i:02}","SIM-VESSEL-B","vessel_load","quay-crane-1",30,bu) for i in (1,2,3)]
    add("SIM-B-DEPARTURE","SIM-VESSEL-B","vessel_departure","marine-channel-1",30,bl)


def _active_effects(state: dict) -> list[dict]:
    return [effect for incident in state.get("spatial_incidents", {}).values()
            if incident.get("status") in {"active", "monitoring"} for effect in incident.get("effects", [])]


def reconcile_effects_in_place(state: dict) -> None:
    initialize_in_place(state)
    effects = _active_effects(state)
    limits: dict[str, int] = {}
    feed_offline = False
    channel = "open"
    for effect in effects:
        kind = effect.get("kind")
        if kind == "resource_capacity":
            rid, cap = effect.get("resource_id"), effect.get("capacity")
            if rid not in state["resources"] or type(cap) is not int or not 0 <= cap <= state["resources"][rid]["capacity"]:
                raise ValueError("Incident capacity must reference a known resource and valid integer capacity")
            limits[rid] = min(limits.get(rid, cap), cap)
        elif kind == "feed_offline":
            feed_offline = True
        elif kind == "marine_channel":
            if effect.get("status") not in {"closed", "restricted", "open"}:
                raise ValueError("Unsupported marine channel restriction")
            if effect["status"] == "closed":
                channel = "closed"
            elif effect["status"] == "restricted" and channel != "closed":
                channel = "restricted"
        else:
            raise ValueError("Unsupported spatial incident effect")
    for rid, resource in state["resources"].items():
        base = resource.setdefault("world_available_capacity", resource["available_capacity"])
        resource.setdefault("world_status", resource["status"])
        available = min(base, limits.get(rid, base))
        if rid == "marine-channel-1" and channel == "closed":
            available = 0
        resource["available_capacity"] = available
        resource["status"] = "closed" if available == 0 else "restricted" if available < resource["capacity"] else resource["world_status"]
    state["provider_online"] = bool(state["world_provider_online"] and not feed_offline)
    state["feed"]["online"] = state["provider_online"]
    state["spatial_operations"]["marine_channel"]["status"] = channel


def _finish_segment(order: dict, minute: int) -> None:
    if order["segments"] and order["segments"][-1]["end_min"] is None:
        order["segments"][-1]["end_min"] = minute


def advance_spatial_operations(state: dict) -> None:
    """In-place clock hook; call at clock zero and each simulated minute."""
    initialize_in_place(state)
    if state["mode"] != "SIMULATION":
        return
    reconcile_effects_in_place(state)
    model=state["spatial_operations"]
    minute=state["clock_min"]
    delta=minute-model["last_tick_min"]
    if delta not in (0,1):
        raise ValueError("Spatial operations must be stepped on every simulation minute")
    orders=model["workorders"]
    for order in orders:
        if order["status"] != "in_progress":
            continue
        available=state["resources"][order["resource_id"]]["available_capacity"] > 0
        if not available:
            order["status"]="paused"
            _finish_segment(order,minute)
            _log(state,"vessel.operation.paused", "Synthetic vessel work paused",f"{order['id']}: its own resource is unavailable; no completed workorder counted.")
            continue
        order["service_minutes"] += delta
        order["progress"]=round(min(1,order["service_minutes"]/order["duration_minutes"]),4)
        if order["service_minutes"] >= order["duration_minutes"]:
            order["status"]="completed";order["completed_at_min"]=minute
            _finish_segment(order,minute)
            _log(state,"vessel.operation.completed","Synthetic vessel workorder completed",f"{order['id']} ({order['phase']}); counted only in vessel workorders, not gate throughput or TEU.")
    model["last_tick_min"]=minute
    completed={o["id"] for o in orders if o["status"]=="completed"}
    busy={o["resource_id"] for o in orders if o["status"]=="in_progress"}
    for order in sorted(orders,key=lambda o:(o["release_at_min"],o["id"])):
        if order["status"] not in {"queued","paused"} or order["release_at_min"] > minute:
            continue
        resource=state["resources"][order["resource_id"]]
        if order["resource_id"] in busy or resource["available_capacity"] <= 0 or not set(order["predecessors"]) <= completed:
            continue
        resuming=order["status"]=="paused"
        order["status"]="in_progress"
        if order["start_min"] is None:
            order["start_min"]=minute
        order["segments"].append({"start_min":minute,"end_min":None})
        busy.add(order["resource_id"])
        _log(state,"vessel.operation.started","Synthetic vessel work resumed" if resuming else "Synthetic vessel work started",f"{order['id']} uses {order['resource_id']}; abstract work progress is independent of tracked-cohort gate handoffs.")


def spatial_snapshot(state: dict) -> dict:
    projected=copy.deepcopy(state) if "spatial_operations" not in state else state
    initialize_in_place(projected)
    result=copy.deepcopy(projected["spatial_operations"])
    orders=result["workorders"]
    result["metrics"]={"completed_unload_workorders":sum(o["kind"]=="vessel_unload" and o["status"]=="completed" for o in orders),
                       "completed_load_workorders":sum(o["kind"]=="vessel_load" and o["status"]=="completed" for o in orders),
                       "completed_arrivals":sum(o["kind"]=="vessel_arrival" and o["status"]=="completed" for o in orders),
                       "completed_departures":sum(o["kind"]=="vessel_departure" and o["status"]=="completed" for o in orders),
                       "active_workorders":sum(o["status"]=="in_progress" for o in orders),
                       "queued_workorders":sum(o["status"]=="queued" for o in orders),
                       "paused_workorders":sum(o["status"]=="paused" for o in orders),
                       "units":"synthetic workorders; not TEU or gate handoffs"}
    return result


def _apply(state: dict, incident: dict, active: list[dict], resolving: bool) -> dict:
    new=copy.deepcopy(state)
    initialize_in_place(new)
    if new["mode"] != "SIMULATION":
        if incident.get("effects"):
            raise ValueError("Physical incident effects require SIMULATION mode")
        return new
    if not isinstance(incident.get("id"),str) or not incident["id"]:
        raise ValueError("Incident requires an ID")
    relevant={row["id"]:copy.deepcopy(row) for row in active if row.get("status") in {"active","monitoring"}}
    if resolving:
        relevant.pop(incident["id"],None)
    else:
        relevant[incident["id"]]=copy.deepcopy(incident)
    for row in relevant.values():
        if row.get("status")=="monitoring" and row.get("effects"):
            raise ValueError("Monitoring incidents cannot apply physical effects")
    was_online=new["provider_online"]
    new["spatial_incidents"]=relevant
    reconcile_effects_in_place(new)
    if not was_online and new["provider_online"]:
        from .engine import _provider_envelope, _receive_provider_envelope
        backlog=new["feed_queue"];new["feed_queue"]=[]
        for envelope in backlog:
            _receive_provider_envelope(new,envelope,drain=True)
        _receive_provider_envelope(new,_provider_envelope(new,f"incident-recovery:{new['clock_min']}:{new['sequence']+1}",new["clock_min"]),drain=True)
    advance_spatial_operations(new)
    from .simulation import _cancel_unavailable
    from .engine import plan
    _cancel_unavailable(new)
    current=new.get("plan") or {}
    new["plan"]=plan(new,current.get("profile","throughput"),current.get("strategy","optimized"))
    _log(new,"spatial.incident.resolved" if resolving else "spatial.incident.applied", "Spatial incident layer resolved" if resolving else "Spatial incident layer applied",f"{incident['id']}; only its confirmed modeled effects changed. Other active restrictions, known holds and base-world conditions remain independent.")
    return new


def apply_incident_effects(state: dict, incident: dict, active_incidents: list[dict]) -> dict:
    return _apply(state,incident,active_incidents,False)


def resolve_incident_effects(state: dict, incident: dict, remaining_active: list[dict]) -> dict:
    return _apply(state,incident,remaining_active,True)
