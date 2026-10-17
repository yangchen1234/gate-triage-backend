"""Bounded, synthetic Los Angeles-volume movement stream and local queue model.

Official port totals calibrate TEU volume only.  Terminal allocations, length
mix, times, prerequisites, resources and service durations are invented.  A
movement record is not a unique annual container or a live port observation.
"""
from __future__ import annotations

import bisect
import copy
import hashlib
import heapq
import math
import uuid
from collections import defaultdict
from typing import Iterator

SOURCE_URL = "https://portoflosangeles.org/business/statistics/container-statistics/historical-teu-statistics-2025"
TERMINAL_IDS = ("terminal-apm", "terminal-everport", "terminal-fenix", "terminal-trapac", "terminal-yusen", "terminal-wbct-cs", "terminal-wbct-latil")
CATEGORY_TEUS = {"loaded_import": 5316713.30, "empty_import": 3793.15, "loaded_export": 1429260.00, "empty_export": 3489551.95}
ANNUAL_TEUS = 10239318.40
JULY_TEUS = 1019837.30
PROFILE_INPUTS = {"la_average_day": (1, ANNUAL_TEUS / 365), "la_peak_month_day": (1, JULY_TEUS / 31), "la_seven_day": (7, ANNUAL_TEUS / 365)}
ASSUMPTIONS = [
    "All movement rows, timing, terminal assignment, service times, prerequisites and resource slots are synthetic.",
    "Official Port of Los Angeles 2025 totals calibrate aggregate TEU volume only; records are not historical unique-container counts.",
    "Assume 65% 40-foot and 35% 20-foot movement records; exact integer TEU totals use 1/2 TEU units and nearest feasible mix.",
    "Allocate approximately equal movement counts to seven terminals; these are not actual terminal volume shares or capacities.",
    "Use twelve synthetic independent service slots per terminal, 3–9 minute service, and an explicit synthetic blocked prerequisite fraction.",
    "Local bounded queue simulation does not claim global CP-SAT optimization of 100,000 records or validated physical port performance.",
    "Imports abstract vessel-unload arrival then gate-out service; exports abstract gate-in arrival then vessel-load service. These are synthetic phases, not real berth/lift/gate telemetry.",
    "Cyber source loss changes freshness visibility only; this physical world model continues known permitted work and does not infer new permission or automatic recovery.",
]
SERVICE_SAMPLES = (3,4,4,5,5,5,6,6,7,8,9)


def _apportion(total: int, weights: dict[str, float], caps: dict[str,int] | None = None) -> dict[str,int]:
    denominator=sum(weights.values())
    exact={k:total*v/denominator for k,v in weights.items()}
    result={k:min(math.floor(v), caps[k] if caps else total) for k,v in exact.items()}
    order=sorted(weights,key=lambda k:(-(exact[k]-math.floor(exact[k])),k))
    remaining=total-sum(result.values())
    while remaining:
        changed=False
        for key in order:
            if not caps or result[key]<caps[key]:
                result[key]+=1;remaining-=1;changed=True
                if not remaining:break
        if not changed:raise ValueError("Cannot apportion the requested total within capacities")
    return result


def profile_catalog() -> list[dict]:
    result=[]
    for identifier,(days,raw_daily) in PROFILE_INPUTS.items():
        teu=int(math.floor(raw_daily+.5));records=int(math.floor(teu/1.65+.5));doubles=teu-records
        result.append({"id":identifier,"name":{"la_average_day":"LA annual-average day","la_peak_month_day":"LA July-peak average day","la_seven_day":"LA seven-day volume rehearsal"}[identifier],
                       "days":days,"record_count":records*days,"horizon_minutes":days*1440,"daily_record_count":records,"daily_teu_target":teu,"generated_teu_total":teu*days,
                       "calibration":{"source_url":SOURCE_URL,"credit":"Port of Los Angeles","year":2025,"annual_teu":ANNUAL_TEUS,"july_teu":JULY_TEUS,
                                      "unrounded_daily_teu":raw_daily,"rounding":"Nearest integer TEU per modeled day","record_unit":"synthetic movement, not unique historical container",
                                      "assumed_40ft_share":.65,"modeled_40ft_share":doubles/records,"category_basis":"2025 annual TEU proportions, rounded by largest remainders"},
                       "terminal_ids":list(TERMINAL_IDS),"assumptions":ASSUMPTIONS})
    return result


def get_profile(profile: str) -> dict:
    selected=next((p for p in profile_catalog() if p["id"]==profile),None)
    if selected is None:raise ValueError("Unknown scale profile")
    return selected


def iter_movement_batches(profile: str = "la_seven_day", seed: int = 17, batch_size: int = 1000) -> Iterator[list[dict]]:
    if type(seed) is not int or not 0<=seed<=2147483647:raise ValueError("Seed must be an integer between 0 and 2147483647")
    if type(batch_size) is not int or not 1<=batch_size<=5000:raise ValueError("Batch size must be 1–5000")
    selected=get_profile(profile);teu=selected["daily_teu_target"];n=selected["daily_record_count"]
    category_teu=_apportion(teu,CATEGORY_TEUS)
    doubles=_apportion(teu-n,category_teu,{k:v//2 for k,v in category_teu.items()})
    counts={k:category_teu[k]-doubles[k] for k in category_teu}
    names=list(counts);bounds=[];total=0
    for name in names:total+=counts[name];bounds.append(total)
    batch=[]
    for day in range(selected["days"]):
        offset=int.from_bytes(hashlib.sha256(f"{seed}:{day}:order".encode()).digest()[:8],"big")
        multiplier=(offset % n) or 1
        while math.gcd(multiplier,n)!=1:multiplier=(multiplier+1)%n or 1
        for index in range(n):
            permuted=(multiplier*index+offset)%n
            category_index=bisect.bisect_right(bounds,permuted);category=names[category_index]
            category_start=0 if category_index==0 else bounds[category_index-1]
            weight=2 if permuted-category_start<doubles[category] else 1
            identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,f"gate-triage:scale:{profile}:{seed}:{day}:{index}"))
            sample=hashlib.sha256(f"{identifier}:world".encode()).digest()
            arrival=day*1440+min(1439,max(0,int(index*1440/n)+(sample[1]%7)-3))
            blocked=sample[2]<10
            inbound=category.endswith("import")
            row={"id":identifier,"number":f"SIM-{seed}-{day+1}-{index+1:05}","terminal_id":TERMINAL_IDS[(index+day)%len(TERMINAL_IDS)],
                 "category":category,"teu":weight,"arrival_min":arrival,"ready_min":arrival+sample[3]%46,
                 "service_min":SERVICE_SAMPLES[sample[4]%len(SERVICE_SAMPLES)],"priority":30+sample[5]%71,"blocked":blocked,
                 "payload":{"origin_kind":"synthetic_volume_calibration","profile":profile,"day_index":day,"equipment_length":40 if weight==2 else 20,
                            "arrival_phase":"vessel_unload" if inbound else "gate_in","ready_phase":"yard_ready","completion_phase":"gate_out" if inbound else "vessel_load",
                            "blocked_reason":"Synthetic unconfirmed prerequisite" if blocked else None,"real_terminal_assignment":False}}
            batch.append(row)
            if len(batch)>=batch_size:
                yield batch;batch=[]
    if batch:yield batch


def initial_resource_state(slots_per_terminal: int = 12, strategy: str = "fifo") -> dict:
    if type(slots_per_terminal) is not int or not 1<=slots_per_terminal<=100:raise ValueError("Slots must be 1–100")
    if strategy not in {"fifo","priority"}:raise ValueError("Scale policies are bounded FIFO or priority, not global CP-SAT")
    return {"version":"scale-slots-1","strategy":strategy,"slots":{terminal:[0]*slots_per_terminal for terminal in TERMINAL_IDS},"in_service":{},"clock_min":0}


def _restriction(terminal: str, restrictions, base: int) -> dict:
    result={"capacity":base,"gate_capacity":base,"source_offline":False,"arrival_blocked":False,"phase_incidents":[]}
    if not restrictions:return result
    if not isinstance(restrictions,dict):raise ValueError("Scale restrictions must be a terminal-ID mapping")
    for key in ("port-la",terminal):
        restriction=restrictions.get(key,{})
        if not isinstance(restriction,dict):raise ValueError("Scale terminal restrictions must be objects")
        for flag in ("closed","source_offline","arrival_blocked"):
            if flag in restriction and type(restriction[flag]) is not bool:raise ValueError("Scale restriction flags must be boolean")
        capacity=0 if restriction.get("closed") or restriction.get("status")=="closed" else restriction.get("capacity",base)
        if type(capacity) is not int or not 0<=capacity<=base:raise ValueError("Scale restriction capacity must be an integer within base capacity")
        result["capacity"]=min(result["capacity"],capacity)
        result["source_offline"] |= restriction.get("source_offline",False)
        result["arrival_blocked"] |= restriction.get("arrival_blocked",False)
        gate_capacity=restriction.get("exit_capacity",base)
        if type(gate_capacity) is not int or not 0<=gate_capacity<=base:raise ValueError("Scale exit capacity must be within base capacity")
        result["gate_capacity"]=min(result["gate_capacity"],gate_capacity)
        incidents=restriction.get("phase_incidents",[])
        if not isinstance(incidents,list):raise ValueError("Phase incidents must be a list")
        for incident in incidents:
            if not isinstance(incident,dict) or incident.get("scenario_id") not in {"storm_wind","battery_access_2024","channel_obstruction_2024","earthquake_asset_inspection","exit_congestion","cyber_data_2017"}:raise ValueError("Unknown scale phase incident")
            minute=incident.get("started_at_min")
            if type(minute) is not int or minute<0:raise ValueError("Phase incident time must be a nonnegative integer")
            result["phase_incidents"].append({"scenario_id":incident["scenario_id"],"started_at_min":minute})
            if incident["scenario_id"]=="earthquake_asset_inspection":result["capacity"]=0
            if incident["scenario_id"]=="exit_congestion":result["gate_capacity"]=min(result["gate_capacity"],max(1,base//2))
            if incident["scenario_id"]=="cyber_data_2017":result["source_offline"]=True
    return result


def _phases(row: dict) -> tuple[str,str]:
    inbound=row.get("category","").endswith("import")
    payload=row.get("payload",{})
    return payload.get("arrival_phase","vessel_unload" if inbound else "gate_in"),payload.get("completion_phase","gate_out" if inbound else "vessel_load")


def _arrival_restricted(row: dict, rule: dict, legacy_since: int | None) -> bool:
    # Queued / active means the arrival phase already happened in this model.
    if row.get("status") in {"queued","in_service"}:return False
    arrival_phase,_=_phases(row)
    if rule["arrival_blocked"] and arrival_phase=="vessel_unload" and row["arrival_min"]>=legacy_since:return True
    for incident in rule["phase_incidents"]:
        if row["arrival_min"]<incident["started_at_min"]:continue
        if arrival_phase=="vessel_unload" and incident["scenario_id"] in {"storm_wind","channel_obstruction_2024"}:return True
        if arrival_phase=="gate_in" and incident["scenario_id"]=="battery_access_2024":return True
    return False


def _service_restricted(row: dict, rule: dict) -> bool:
    _,completion_phase=_phases(row)
    return any((completion_phase=="vessel_load" and incident["scenario_id"]=="storm_wind") or
               (completion_phase=="gate_out" and incident["scenario_id"]=="battery_access_2024")
               for incident in rule["phase_incidents"])


def schedule_window(rows: list[dict], from_min: int, to_min: int, resource_state: dict | None = None, restrictions: dict | None = None) -> dict:
    """Advance a bounded set of known rows through an observed-time slot model.

    The DB caller must lock its run, apply row updates transactionally, and
    select each persisted row once per window. Metrics are bounded-window
    deltas; relational state, not these suggestions, is the global truth.
    """
    if type(from_min) is not int or type(to_min) is not int or not 0<=from_min<=to_min:raise ValueError("Window minutes must be nonnegative and ordered")
    if to_min-from_min>1440:raise ValueError("Advance scale work in windows of at most one day")
    if len(rows)>14000:raise ValueError("Use bounded windows of at most 2,000 rows per terminal")
    by_terminal=defaultdict(list)
    if len({row.get("id") for row in rows})!=len(rows):raise ValueError("Movement IDs must be distinct within a scheduling window")
    for row in rows:
        if row.get("terminal_id") not in TERMINAL_IDS:raise ValueError("Unknown scale terminal")
        for field in ("arrival_min","ready_min","service_min","priority"):
            if type(row.get(field)) is not int:raise ValueError(f"Scale {field} must be integer")
        if row["arrival_min"]<0 or row["ready_min"]<row["arrival_min"] or row["service_min"]<=0 or type(row.get("teu")) is not int or row["teu"] not in (1,2) or type(row.get("blocked")) is not bool:raise ValueError("Invalid movement timing, service, prerequisite or TEU")
        by_terminal[row["terminal_id"]].append(row)
    if any(len(group)>2000 for group in by_terminal.values()):raise ValueError("Use at most 2,000 rows per terminal in one scheduling window")
    state=copy.deepcopy(resource_state) if resource_state else initial_resource_state()
    if state.get("strategy") not in {"fifo","priority"}:raise ValueError("Unsupported scale strategy")
    row_index={row["id"]:row for row in rows}
    if set(state["in_service"])-set(row_index):raise ValueError("Include all persisted active-service rows in the bounded decision window")
    updates={};events=[];metrics={"completed_movements":0,"completed_teu":0,"started_movements":0,"permanent_blocked":0,"incident_blocked":0,"source_verification_waiting":0,"source_freshness_unknown":0,"phase_blocked":0,"arrival_waiting":0,"queued_observed":0,"interrupted_movements":0,"scope":"bounded input and active-service deltas; global counts come from relational state","policy":state["strategy"]}
    def update(identifier,status,started=None,completed=None):
        updates[identifier]={"id":identifier,"status":status,"started_min":started,"completed_min":completed}
    def event(identifier,kind,minute,terminal):
        events.append({"movement_id":identifier,"type":kind,"at_min":minute,"terminal_id":terminal,"provenance":"synthetic_scale_model"})
    for terminal in TERMINAL_IDS:
        slots=state["slots"][terminal];rule=_restriction(terminal,restrictions,len(slots));capacity=rule["capacity"]
        if any(i["started_at_min"]>from_min for i in rule["phase_incidents"]):raise ValueError("Apply confirmed incidents at or before the current scale window, not future information")
        history=state.setdefault("restriction_since",{}).setdefault(terminal,{})
        if rule["arrival_blocked"]:history.setdefault("arrival_blocked",from_min)
        else:history.pop("arrival_blocked",None)
        active={key:value for key,value in state["in_service"].items() if value["terminal_id"]==terminal}
        source_blocked={row["id"] for row in by_terminal.get(terminal,[]) if row["blocked"]}
        candidates=[]
        for identifier,work in list(active.items()):
            row=row_index[identifier]
            gate_slot_lost=_phases(row)[1]=="gate_out" and work["slot_index"]>=rule["gate_capacity"]
            if work["slot_index"]>=capacity or identifier in source_blocked or gate_slot_lost or _service_restricted(row,rule):
                state["in_service"].pop(identifier,None);active.pop(identifier,None)
                slots[work["slot_index"]]=from_min
                update(identifier,"blocked");metrics["interrupted_movements"]+=1;metrics["incident_blocked"]+=1
                event(identifier,"movement.interrupted",from_min,terminal)
            elif work["end_min"]<=from_min:
                update(identifier,"completed",work["started_min"],work["end_min"])
                state["in_service"].pop(identifier,None);active.pop(identifier,None)
                metrics["completed_movements"]+=1;metrics["completed_teu"]+=work["teu"]
                event(identifier,"movement.completed",work["end_min"],terminal)
        for row in by_terminal.get(terminal,[]):
            if row.get("status")=="completed" or row["id"] in active or row.get("status")=="in_service":continue
            if row["arrival_min"]>to_min:continue
            if row["blocked"]:
                update(row["id"],"blocked");metrics["permanent_blocked"]+=1;continue
            if _arrival_restricted(row,rule,history.get("arrival_blocked")):
                update(row["id"],"blocked");metrics["arrival_waiting"]+=1;continue
            if capacity==0:
                update(row["id"],"blocked");metrics["incident_blocked"]+=1;continue
            if _service_restricted(row,rule):
                update(row["id"],"blocked");metrics["phase_blocked"]+=1;continue
            if rule["source_offline"]:
                # A telemetry outage is observational; it does not fabricate a physical closure.
                metrics["source_freshness_unknown"]+=1
            release=max(row["arrival_min"],row["ready_min"])
            heapq.heappush(candidates,(release,row["id"],row))
        ready=[];cursor=from_min
        while cursor<=to_min:
            for identifier,work in list(active.items()):
                if work["end_min"]<=cursor:
                    update(identifier,"completed",work["started_min"],work["end_min"])
                    state["in_service"].pop(identifier,None);active.pop(identifier,None)
                    metrics["completed_movements"]+=1;metrics["completed_teu"]+=work["teu"]
                    event(identifier,"movement.completed",work["end_min"],terminal)
            while candidates and candidates[0][0]<=cursor:
                _,_,row=heapq.heappop(candidates)
                key=(-row["priority"],row["arrival_min"],row["id"]) if state["strategy"]=="priority" else (row["arrival_min"],row["id"])
                heapq.heappush(ready,(key,row["id"],row))
            free=[i for i in range(capacity) if slots[i]<=cursor]
            while ready and free and cursor<to_min:
                skipped=[];selected=None
                while ready:
                    item=heapq.heappop(ready);row=item[2]
                    eligible=[slot for slot in free if _phases(row)[1]!="gate_out" or slot<rule["gate_capacity"]]
                    if eligible:selected=(item,eligible[0]);break
                    skipped.append(item)
                for item in skipped:heapq.heappush(ready,item)
                if selected is None:break
                (_,identifier,row),slot=selected;free.remove(slot)
                end=cursor+row["service_min"]
                work={"terminal_id":terminal,"slot_index":slot,"started_min":cursor,"end_min":end,"teu":row["teu"]}
                slots[slot]=end;active[identifier]=work;state["in_service"][identifier]=work
                update(identifier,"in_service",cursor,None);metrics["started_movements"]+=1
                event(identifier,"movement.started",cursor,terminal)
            next_times=[work["end_min"] for work in active.values() if work["end_min"]>cursor]
            if candidates:next_times.append(candidates[0][0])
            if not next_times or min(next_times)>to_min:break
            cursor=min(next_times)
        waiting=[item[2]for item in ready]+[item[2]for item in candidates]
        for row in waiting:
            update(row["id"],"queued");metrics["queued_observed"]+=1
        for identifier,work in active.items():
            if identifier not in updates:update(identifier,"in_service",work["started_min"],None)
    state["clock_min"]=max(state.get("clock_min",0),to_min)
    return {"updates":list(updates.values()),"events":events,"resource_state":state,"metrics":metrics}
