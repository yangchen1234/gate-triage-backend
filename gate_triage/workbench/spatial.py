"""Reference geography and inspectable, state-derived synthetic operational views.

Coordinates are orientation references. No geofence/dispatch authority or live
terminal condition is inferred from a point or historical document.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi import APIRouter, Header

from .api import authorized_workspace, envelope, respond
from .db import begin_read_snapshot, get_database

router = APIRouter(prefix="/api/v1", tags=["geographic operations"])
ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "docs/reference-pack/geography/los-angeles-reference.geojson"
PORT_SOURCE = "https://portoflosangeles.org/business/terminals/container"
RANK = {"unknown": -1, "normal": 0, "watch": 1, "restricted": 2, "critical": 3}

# Schematic coordinates deliberately have no claim to be actual crane/gate/yard
# locations. Only the underlying terminal reference points are published data.
ZONES = [
    ("zone-gate-east", "East access · simulated", "gate_handoff", [-118.2477, 33.7448], ["east-lane-1", "east-lane-2"]),
    ("zone-gate-west", "West access · simulated", "gate_handoff", [-118.2588, 33.7448], ["west-lane-1", "west-lane-2"]),
    ("zone-yard", "Yard & weight review · simulated", "yard_check", [-118.2533, 33.7428], ["scale-1", "yard-crew"]),
    ("zone-reefer", "Reefer care · simulated", "reefer_check", [-118.2497, 33.7407], ["reefer-tech"]),
    ("zone-vessel-load", "Vessel loading · simulated", "vessel_load", [-118.2571, 33.7388], ["quay-crane-1"]),
    ("zone-vessel-unload", "Vessel unloading · simulated", "vessel_unload", [-118.2533, 33.7368], ["quay-crane-2"]),
]
CORRIDORS = [
    ("corridor-road-exit", "Road exit corridor · simulated impact", "road_access", [[-118.248,33.745],[-118.254,33.750],[-118.269,33.750],[-118.283,33.750]]),
    ("corridor-main-channel", "Marine access · schematic impact", "marine_transit", [[-118.261,33.710],[-118.271,33.726],[-118.268,33.738],[-118.272,33.750]]),
]


def incident_catalog() -> list[dict]:
    """Curated response policies, not operational orders or automatic alerts."""
    result = [
        {"id":"battery_access_2024", "name":"Battery fire / blocked access · 2024-inspired", "default_scope_id":"zone-gate-east", "default_severity":"critical", "owner_role":"terminal_incident_commander", "source_refs":[{"title":"Port of Los Angeles · September 2024 truck accident", "url":"https://portoflosangeles.org/references/2024-news-releases/news_092724_truck_accident"},{"title":"LAFD · lithium-ion battery truck crash", "url":"https://lafd.org/news/lithiumion-batteries-burn-days-after-san-pedro-big-rig-crash"}], "historical_facts":"A September 2024 battery truck accident disrupted roads and terminal operations in Los Angeles. The port reported roads reopening and expected terminal resumption; this does not establish each service's actual recovery time.", "synthetic_parameters":"Selected access resources become unavailable until acknowledged recovery. No blast radius, evacuation distance, cargo damage or real closure duration is inferred.", "response_steps":["Escalate to incident command / emergency responders through authorized procedures.","Mark confirmed affected access unavailable; keep the exclusion area and responders' instructions authoritative.","Continue only independently permitted work outside the affected scope; coordinate appointments and reefer care without crossing the restriction.","Record separate road, terminal-service and resource recovery confirmations before phased release."], "hard_boundaries":["No automated emergency response dispatch", "No hazardous-material handling advice", "No inferred all-port closure"]},
        {"id":"cyber_data_2017", "name":"Terminal data outage · 2017-inspired", "default_scope_id":"terminal-fenix", "default_severity":"restricted", "owner_role":"terminal_it_and_operations", "source_refs":[{"title":"U.S. Congresswoman Torres · 2017 LA terminal cyber closure", "url":"https://torres.house.gov/media-center/press-releases/rep-torres-port-la-terminal-closure-after-cyber-attack"}], "historical_facts":"A June 2017 cyberattack caused closure of a Los Angeles terminal. The synthetic outage here is relocated to the modeled terminal; it is not a claim about Fenix in 2017.", "synthetic_parameters":"Provider feed is offline. Resource closures require separate evidence and are not inferred from network loss.", "response_steps":["Escalate connectivity and integrity questions to IT and terminal operations.","Preserve known holds and evidence watermarks; label stale or unknown fields.","Continue only tasks with independently valid prerequisites; do not treat missing messages as clearance.","Recover the feed, reconcile queued events and verify integrity before trusting new state."], "hard_boundaries":["No clearing holds during an outage", "No inferred physical terminal closure"]},
        {"id":"storm_wind", "name":"Confirmed crane wind restriction", "default_scope_id":"terminal-fenix", "default_severity":"restricted", "owner_role":"crane_supervisor", "source_refs":[{"title":"OSHA 29 CFR 1917.45 · crane high-wind instructions", "url":"https://www.osha.gov/laws-regs/regulations/standardnumber/1917/1917.45"},{"title":"Port of LA · Hilary preparedness 2023", "url":"https://portoflosangeles.org/references/2023-news-releases/news_081823_hurricane_hilary"}], "historical_facts":"OSHA requires crane-specific high-wind operating instructions. In 2023 the port distinguished storm preparation from normal reported ship and terminal movements. A warning alone is not evidence of closure.", "synthetic_parameters":"The exercise injects an operator-confirmed crane restriction, not weather API inference or a universal wind-speed threshold.", "response_steps":["Confirm equipment-specific operating instructions and the authorized supervisor's restriction.","Suspend only affected synthetic crane work; preserve unaffected gate work when permitted.","Queue vessel work and explain the impacted schedule.","Require supervisor recovery confirmation before modeled crane work resumes."], "hard_boundaries":["No invented universal wind threshold", "No automated equipment control"]},
        {"id":"channel_obstruction_2024", "name":"Marine channel obstruction · Baltimore-inspired", "default_scope_id":"corridor-main-channel", "default_severity":"critical", "owner_role":"marine_operations_and_port_authority", "source_refs":[{"title":"NTSB · Dali / Key Bridge investigation", "url":"https://www.ntsb.gov/investigations/Pages/DCA24MM031.aspx"},{"title":"USACE · 2024 channel recovery", "url":"https://www.nab.usace.army.mil/Media/News-Releases/Article/3731790/us-army-corps-of-engineers-develops-tentative-timeline-to-reopen-fort-mchenry-c/"}], "historical_facts":"The March 2024 Key Bridge collapse obstructed Baltimore's channel and required coordinated clearance. This scenario transposes the class of disruption into a Los Angeles exercise; no LA bridge failure is alleged.", "synthetic_parameters":"Block synthetic future vessel transit; already-berthed lifts and truck handoffs remain independently assessed. No navigational routing or salvage model.", "response_steps":["Escalate to marine operations and responsible authorities.","Stop planning new transits through the affected channel; retain pending vessel demand.","Keep already-berthed terminal work and road access independently scoped.","Record authority-confirmed restrictions and phased recovery; do not infer opening from elapsed time."], "hard_boundaries":["No vessel navigation instructions", "No automatic all-gate closure"]},
        {"id":"exit_congestion", "name":"Port road exit congestion · backlog-inspired", "default_scope_id":"corridor-road-exit", "default_severity":"restricted", "owner_role":"terminal_and_trucking_coordinator", "source_refs":[{"title":"Port of LA · October 2021 cargo backlog response", "url":"https://portoflosangeles.org/references/2021-news-releases/news_102931_cargofee"}], "historical_facts":"In 2021 Los Angeles adopted measures to address long-dwell cargo amid record volumes. This source supports the backlog context, not a specific road-exit closure or traffic capacity.", "synthetic_parameters":"One lane per modeled gate is removed, representing constrained downstream acceptance. Other six terminals carry a potential-impact annotation only. No measured road queue, reroute or real travel time is claimed.", "response_steps":["Confirm downstream acceptance and affected access with transport coordinators.","Reduce admission to modeled downstream capacity instead of moving the queue outside the gate.","Prioritize feasible work, show unserved backlog and stakeholder wait tradeoffs.","Restore capacity only after recorded downstream recovery confirmation."], "hard_boundaries":["No road navigation/rerouting", "No fake metrics for unmodeled terminals"]},
        {"id":"earthquake_asset_inspection", "name":"Earthquake / asset inspection · 2011-inspired", "default_scope_id":"terminal-fenix", "default_severity":"critical", "owner_role":"incident_command_and_asset_inspector", "source_refs":[{"title":"MLIT Japan · 2011 port clearance and relief access", "url":"https://infra-archive311.thr.mlit.go.jp/en/w02.html"},{"title":"Port of LA · all-hazards and earthquake preparedness", "url":"https://portoflosangeles.org/community/residents/emergency-management"}], "historical_facts":"After the 2011 Tohoku earthquake and tsunami, Japanese authorities cleared affected channels and prioritized relief access. Los Angeles publishes all-hazards and earthquake preparedness guidance. This exercise is not a Los Angeles earthquake prediction or reconstruction.", "synthetic_parameters":"An operator-confirmed affected asset scope is unavailable pending qualified inspection. No seismic intensity threshold, structural assessment, evacuation route or damage estimate is inferred.", "response_steps":["Escalate life-safety and asset concerns under the employer's emergency action plan; account for staff through authorized processes.","Keep confirmed affected gates, yard and lifting resources unavailable pending qualified inspection; an alert alone is not structural evidence.","Separate road, quay, channel and power inspections. Coordinate authorized relief priorities without overriding holds or uninspected assets.","Require asset-specific confirmation, remaining restriction checks and staged restart; partial clearance is not all-port recovery."], "hard_boundaries":["No structural safety certification", "No seismic prediction", "No arbitrary evacuation instructions"]},
    ]
    strategies = {
        "battery_access_2024": {"goal":"Protect the confirmed exclusion scope while preserving permitted access elsewhere.", "required_evidence":["Current responder / authorized operations report", "Affected access and exclusion scope", "Separate road and terminal service recovery confirmations"], "continue_when":"Other access is independently confirmed usable and no task crosses the exclusion scope.", "recovery_checks":["Responder restriction update", "Road acceptance confirmed", "Terminal service and lane separately checked"], "escalate_when":["Fire, off-gassing or life-safety concern", "Uncertain exclusion scope", "No owner acknowledgement within the synthetic ten-minute follow-up window"], "tradeoff":"Protect people and responder access first; show which carrier and cargo queues wait rather than silently favoring urgent freight."},
        "cyber_data_2017": {"goal":"Preserve trustworthy restrictions and coordinate continuity while source integrity is uncertain.", "required_evidence":["Feed heartbeat and oldest queued timestamp", "Per-field source observation / receipt time", "IT integrity and recovery confirmation"], "continue_when":"Independent prerequisites remain current; unknown source clearance is never assumed.", "recovery_checks":["Connectivity restored", "Queued IDs deduplicated", "Late updates checked against field watermarks", "IT / operations owner confirmation"], "escalate_when":["Suspected corruption or conflicting source updates", "Evidence freshness expires", "Unknown physical capacity; do not infer it from feed status"], "tradeoff":"Continuity benefits must be balanced against decisions on stale evidence; degraded visibility is not proof of zero risk."},
        "storm_wind": {"goal":"Respect equipment-specific restrictions and avoid closing unrelated services.", "required_evidence":["Supervisor-confirmed equipment restriction", "Applicable crane / manufacturer operating instructions", "Scope and time of restriction"], "continue_when":"Unaffected gate, yard or reefer tasks are separately permitted; crane warnings alone do not imply their closure.", "recovery_checks":["Crane supervisor releases the specific restriction", "Equipment readiness confirmation", "Any separate marine restrictions retained"], "escalate_when":["Unsafe crane condition", "Missing equipment-specific instructions", "Contradictory warning and operating report"], "tradeoff":"Vessel turnaround may worsen while qualified road work continues; do not mix lift completions and truck throughput."},
        "channel_obstruction_2024": {"goal":"Hold affected transits and retain feasible already-berthed work under independent permissions.", "required_evidence":["Responsible marine authority restriction", "Affected transit scope / vessel class", "Current berth and road operating confirmation"], "continue_when":"Already-berthed lifts and road services have independent permission; future vessel arrivals remain blocked.", "recovery_checks":["Authority-confirmed transit clearance", "Any vessel-class or one-way restriction", "Berth and equipment availability"], "escalate_when":["Collision, obstruction or life-safety report", "No authoritative transit scope", "Relief / salvage priority decision required"], "tradeoff":"A shipowner's departure objective cannot override channel restrictions; preserving yard space and relief access requires explicit human priorities."},
        "exit_congestion": {"goal":"Match modeled release to confirmed downstream acceptance and expose displaced waiting.", "required_evidence":["Downstream receiving capacity confirmation", "Gate / corridor scope", "Appointment and warehouse coordination status"], "continue_when":"Downstream acceptance exists and release does not simply relocate the queue outside the gate.", "recovery_checks":["Receiving capacity reconfirmed", "Active corridor restrictions checked", "Controlled admission restored"], "escalate_when":["Spillback threatens safe access", "No downstream acceptance evidence", "Stakeholder service commitments conflict"], "tradeoff":"Favoring short jobs can improve near-term throughput while worsening some waits; show group waits, unfinished backlog and operator-selected objectives."},
        "earthquake_asset_inspection": {"goal":"Require asset-specific safety confirmation and support authorized phased recovery.", "required_evidence":["Current incident-command report", "Qualified asset inspections", "Separate access, quay, channel and utility status"], "continue_when":"Only independently inspected and authorized assets may return; uninspected scope stays restricted.", "recovery_checks":["Qualified asset release recorded", "Remaining hazards and incident layers checked", "Phased recovery approved by responsible role"], "escalate_when":["Possible casualties or structural damage", "Unknown inspection coverage", "Relief-priority or cross-agency authority required"], "tradeoff":"Life safety and access for authorized relief precede commercial throughput; software must not certify infrastructure or invent evacuation routes."},
    }
    for item in result:
        item["dispatcher_strategy"] = {**strategies[item["id"]], "policy_provenance":"Our generic exercise policy informed by the cited sources; not an authority-approved site procedure.", "response_steps":item["response_steps"], "hard_boundaries":item["hard_boundaries"]}
    return result


def scope_catalog() -> list[dict]:
    refs = json.loads(REFERENCE.read_text())["features"]
    return ([{"id":"port-la", "name":"Port of Los Angeles · modeled cohort only", "kind":"port", "modeled":True}]
            + [{"id":f["properties"]["id"], "name":f["properties"]["name"], "kind":"terminal", "modeled":f["properties"]["modeled"]} for f in refs]
            + [{"id":z[0], "name":z[1], "kind":"zone", "modeled":True} for z in ZONES]
            + [{"id":c[0], "name":c[1], "kind":"corridor", "modeled":True} for c in CORRIDORS])


def assess_incident(state: dict, scenario_id: str, scope_id: str, severity: str = "restricted") -> dict:
    catalog = {r["id"]:r for r in incident_catalog()}
    if scenario_id not in catalog:
        raise ValueError("Unknown incident scenario")
    scope = next((s for s in scope_catalog() if s["id"] == scope_id), None)
    known = scope is not None
    modeled = bool(scope and scope["modeled"])
    resources, zones, effects = [], [], []
    all_scope = scope_id in {"port-la","terminal-fenix"}
    if modeled:
        if scenario_id == "battery_access_2024":
            zones = ["zone-gate-east","zone-gate-west"] if all_scope or scope_id == "corridor-road-exit" else [scope_id] if scope_id in {"zone-gate-east","zone-gate-west"} else []
        elif scenario_id == "exit_congestion":
            zones = ["zone-gate-east","zone-gate-west"] if all_scope or scope_id == "corridor-road-exit" else [scope_id] if scope_id in {"zone-gate-east","zone-gate-west"} else []
        elif scenario_id == "storm_wind":
            zones = ["zone-vessel-load","zone-vessel-unload"] if all_scope else [scope_id] if scope_id in {"zone-vessel-load","zone-vessel-unload"} else []
        elif scenario_id == "cyber_data_2017" and all_scope:
            effects = [{"kind":"feed_offline"}]
            zones = [z[0] for z in ZONES if z[0].startswith("zone-gate") or z[0] in {"zone-yard","zone-reefer"}]
        elif scenario_id == "channel_obstruction_2024" and (all_scope or scope_id == "corridor-main-channel"):
            effects = [{"kind":"marine_channel", "status":"closed"}]
            zones = ["corridor-main-channel"]
        elif scenario_id == "earthquake_asset_inspection":
            zones = [z[0] for z in ZONES] if all_scope else [scope_id] if any(z[0]==scope_id for z in ZONES) else []
            if all_scope:
                # This is the modeled terminal's receiving/transit slot, not a
                # declaration that all real marine traffic is prohibited.
                resources.append("marine-channel-1")
        if scenario_id in {"battery_access_2024", "exit_congestion", "storm_wind", "earthquake_asset_inspection"}:
            for zid in zones:
                ids = next((z[4] for z in ZONES if z[0] == zid), [])
                resources.extend(ids[1:] if scenario_id == "exit_congestion" else ids)
        effects += [{"kind":"resource_capacity", "resource_id":rid, "capacity":0} for rid in resources]
    containers = []
    for c in state["containers"].values():
        if c.get("completed_at_min") is not None or c["provider"].get("pod_full_out_at"):
            continue
        if effects and (scenario_id == "cyber_data_2017" or any(c["gate"] == "Any" or c["gate"].lower() in zid for zid in zones if "gate-" in zid)):
            containers.append(c["container_id"])
    applicable = bool(effects)
    return {"known_scope":known, "modeled_scope":modeled, "applicable":applicable,
            "scope":scope or {"id":scope_id,"name":"Unrecognized scope", "modeled":False},
            "scope_id":scope_id, "effects":effects, "resource_ids":resources,
            "restriction":"closed", "affected_zone_ids":zones,
            "affected_terminal_ids":[s["id"] for s in scope_catalog() if s["kind"]=="terminal"] if scope_id in {"port-la","corridor-road-exit","corridor-main-channel"} else [scope_id] if scope and scope["kind"]=="terminal" else ["terminal-fenix"] if applicable else [],
            "affected_container_ids":sorted(containers), "severity":severity,
            "limitations":["All quantities and resource effects apply only to the synthetic modeled cohort.","Reference terminals have no live operational metrics."] + ([] if applicable else ["Scope/incident combination has no executable resource mapping; monitor and ask a human to confirm scope."])}


def _severity(*values: str) -> str:
    return max(values or ("unknown",), key=lambda x:RANK.get(x,-1))


def map_snapshot(state: dict) -> dict:
    from .engine import snapshot
    snap = snapshot(copy.deepcopy(state))
    references = json.loads(REFERENCE.read_text())
    rows, tasks = snap["containers"], snap["tasks"]
    incidents = state.get("emergency_incidents", [])
    if isinstance(incidents, dict): incidents = list(incidents.values())
    from .emergency import incident_view
    incidents = [incident_view(i, state["clock_min"], state.get("scale_clock_min"), state.get("scale_run_id")) for i in incidents]
    active = [i for i in incidents if i.get("status") not in {"resolved","cancelled"}]
    resources = {r["id"]:r for r in snap["resources"]}
    workorders = snap.get("spatial_operations", {}).get("workorders", [])
    if isinstance(workorders, dict): workorders = list(workorders.values())
    def incident_severity(identifier):
        values = [i.get("escalation",{}).get("effective_severity",i.get("severity","watch")) for i in active if identifier in i.get("assessment",{}).get("affected_zone_ids",[]) or identifier in i.get("assessment",{}).get("affected_terminal_ids",[]) or i.get("scope_id")==identifier]
        return _severity(*values) if values else "normal"
    zones=[]
    for zid,name,op,point,rids in ZONES:
        if "gate-" in zid:
            linked=[c for c in rows if c["gate"] in {"Any", "East" if "east" in zid else "West"}]
            kinds={"gate_handoff"}
        elif zid=="zone-reefer":
            linked=[c for c in rows if any(t["kind"]=="reefer_check" for t in c["tasks"])]
            kinds={"reefer_check"}
        elif zid=="zone-yard":
            linked=[c for c in rows if any(t["kind"]=="weight_check" for t in c["tasks"])]
            kinds={"weight_check"}
        else:
            linked=[];kinds=set()
        ids=[c["container_id"] for c in linked]
        relevant=[t for t in tasks if t["container_id"] in ids and t["kind"] in kinds]
        jobs=[j for j in workorders if j.get("kind",j.get("type",j.get("operation_type")))==op]
        completed=sum(o["status"]=="completed" and o["kind"] in kinds and o["container_id"] in ids for o in state["operations"].values()) if kinds else sum(j.get("status")=="completed" for j in jobs)
        satisfied=sum(t["status"]=="resolved" for t in relevant) if kinds else completed
        running=sum(j.get("status") in {"running","in_progress"} for j in jobs) if not kinds else sum(o["status"]=="running" and o["kind"] in kinds and o["container_id"] in ids for o in state["operations"].values())
        capacity=sum(resources[r].get("available_capacity",0) for r in rids if r in resources)
        base_capacity=sum(resources[r].get("capacity",0) for r in rids if r in resources)
        open_tasks=sum(t["status"] not in {"resolved","cancelled"} for t in relevant)
        critical=any(t.get("priority_band")=="critical" and t["status"] not in {"resolved","cancelled"} for t in relevant)
        severity=_severity(incident_severity(zid), "restricted" if base_capacity and capacity==0 else "watch" if capacity<base_capacity else "normal", "critical" if critical else "normal")
        total=len(relevant) if kinds else len(jobs)
        metrics={"containers":len(ids),"open_tasks":open_tasks if kinds else sum(j.get("status") not in {"completed","cancelled"} for j in jobs),"completed_operations":completed,"satisfied_tasks":satisfied,"running_operations":running,"capacity_available":capacity,"capacity_total":base_capacity,"total_operations":total,"progress_percent":round(completed*100/total,1) if total else None,"readiness_percent":round(satisfied*100/total,1) if total else None}
        p={"id":zid,"name":name,"kind":"zone","modeled":True,"provenance":"synthetic","terminal_id":"terminal-fenix","operation_type":op,"severity":severity,"metrics":metrics,"container_ids":ids,"tasks":relevant,"operations":[{"type":op,"status":"modeled" if total else "not_modeled", "completed":completed,"total":total}],"description":"Synthetic operational zone near the Fenix reference location. Position, assignment and capacity are exercise inputs, not the terminal's actual layout. Counts are derived from this workspace's tasks and simulation clock.","source_url":PORT_SOURCE,"resource_ids":rids}
        zones.append({"type":"Feature","geometry":{"type":"Point","coordinates":point},"properties":p})
    terminals=[]
    for f in references["features"]:
        f=copy.deepcopy(f);p=f["properties"];p.update(severity=incident_severity(p["id"]) if p["modeled"] else "unknown",operation_type="terminal_coordination", metrics={} if not p["modeled"] else snap["overview"],container_ids=[c["container_id"] for c in rows] if p["modeled"] else [],description=p["geometry_provenance"]+" "+p["name_provenance"])
        p["potential_incident_ids"]=[i["id"] for i in active if p["id"] in i.get("assessment",{}).get("affected_terminal_ids",[])]
        if p["modeled"]:p["severity"]=_severity(p["severity"],*(z["properties"]["severity"] for z in zones))
        terminals.append(f)
    corridors=[]
    for cid,name,op,coordinates in CORRIDORS:
        corridors.append({"type":"Feature","geometry":{"type":"LineString","coordinates":coordinates},"properties":{"id":cid,"name":name,"kind":"corridor","modeled":True,"severity":incident_severity(cid),"operation_type":op,"container_ids":sorted({n for i in active if i.get("scope_id")==cid for n in i.get("assessment",{}).get("affected_container_ids",[])}),"metrics":{},"description":"Schematic impact corridor for this exercise, not a surveyed road route, channel boundary or navigation instruction.","source_url":PORT_SOURCE}})
    return {"geojson":{"type":"FeatureCollection","features":terminals+zones+corridors},"terminals":terminals,"zones":zones,"incidents":active,"scopes":scope_catalog(),"summary":{"reference_terminals":len(terminals),"modeled_zones":len(zones),"active_incidents":len(active),"modeled_terminal":"terminal-fenix"},"as_of_min":snap["clock_min"],"notice":"Real published terminal reference points + OSM basemap. All operational zones, corridors, resource states and counts are synthetic; other terminals are reference only."}


@router.get("/workspaces/{workspace_id}/map")
def get_map(workspace_id: str, x_workspace_token: str | None = Header(default=None)):
    with get_database().session() as session:
        begin_read_snapshot(session)
        workspace=authorized_workspace(session, workspace_id, x_workspace_token)
        data=map_snapshot(workspace.state)
        from .scale import latest_run, run_data, summary
        run=latest_run(session, workspace_id)
        if run is not None and run.status=="ready":
            bulk=summary(session, run)
            data["scale"]={"run":run_data(run),"summary":bulk,"independent_clock":True}
            by_terminal={r["terminal_id"]:r for r in bulk["terminals"]}
            incidents=data["incidents"]
            for terminal in data["terminals"]:
                p=terminal["properties"];identifier=p["id"]
                counts=by_terminal.get(identifier)
                if counts is None:
                    continue
                applicable=[]
                for incident in incidents:
                    if incident.get("status")=="resolved":continue
                    assessment=incident.get("scale_assessment",{})
                    if assessment.get("run_id")==run.id and identifier in assessment.get("affected_terminal_ids",[]):
                        applicable.append(incident.get("escalation",{}).get("effective_severity",incident.get("severity","watch")))
                p.update(scale_modeled=True,scale_metrics=counts,scale_clock_min=run.clock_min,
                         scale_run_id=run.id,scale_revision=run.revision,
                         scale_severity=_severity("watch" if counts["counts_by_status"].get("blocked",0) else "normal",*applicable),
                         scale_provenance="Persisted synthetic movement rows, allocated by an explicit workload assumption. No actual terminal flow or concurrent inventory is inferred.")
        return respond(envelope(data, workspace))
