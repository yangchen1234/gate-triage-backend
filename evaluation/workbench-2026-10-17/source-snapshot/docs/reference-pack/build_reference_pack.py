"""Rebuild documentation fixtures only. No network access or application writes."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
START = datetime.fromisoformat("2026-10-17T09:00:00-07:00")
HERO = "TRXU7731902"


def write(path, value):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return hashlib.sha256(p.read_bytes()).hexdigest()


def obj(properties, required=None):
    return {"type": "object", "additionalProperties": False, "properties": properties,
            "required": list(properties) if required is None else required}


S = {"type": "string", "minLength": 1}
N = {"type": "number", "minimum": 0}
I = {"type": "integer", "minimum": 0}
ARRAY = lambda item: {"type": "array", "items": item}
PROV = obj({"kind": {"const": "synthetic"}, "description": S, "source_refs": ARRAY(S)})
BASE_EVENT = {"event_id": S, "type": S, "published_at_min": N, "observed_at_min": N,
              "applies_at_min": N, "provenance": {"const": "synthetic"}}
EVENT_FIELDS = {
    "resource.availability": {"resource_ids": ARRAY(S), "state": {"enum": ["closed", "restricted", "open"]}, "capacity": I},
    "provider.connectivity": {"provider_id": {"const": "terminal49_simulated"}, "scope": S,
                              "state": {"enum": ["offline", "partial", "online"]}},
    "evidence.update": {"container_id": S, "namespace": {"enum": ["provider", "operator"]}, "evidence_id": S,
                        "patch": {"type": "object", "minProperties": 1}},
    "demand.multiplier": {"multiplier": {"type": "number", "exclusiveMinimum": 0}, "scope": {"const": "unobserved_fixture_arrivals"}},
    "warning.received": {"code": S, "message": S, "action": {"enum": ["attention_only", "record_policy_only"]}},
}
RESOURCE = obj({"id": S, "kind": {"enum": ["gate_lane", "scale", "crew", "reefer_technician"]},
                "capacity": {"type": "integer", "minimum": 1}, "gate": {"enum": ["East", "West", "Any"]},
                "provenance": {"const": "synthetic"}})
DURATION = obj({"distribution": {"enum": ["constant", "triangular"]}, "minutes": ARRAY({"type": "number", "exclusiveMinimum": 0})})
SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:gate-triage:simulation-1",
    **obj({"schema_version": {"const": "simulation-1"}, "scenario_id": S, "seed": I,
           "start_at": {"type": "string", "format": "date-time"},
           "horizon_minutes": {"type": "integer", "minimum": 1}, "provenance": PROV,
           "containers_fixture": obj({"path": S, "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                                      "mode": {"const": "synthetic"}, "overlay_path": S,
                                      "overlay_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}),
           "planning": obj({"lookahead_minutes": {"type": "integer", "minimum": 1},
                            "replan_minutes": {"type": "integer", "minimum": 1}, "freeze_minutes": I}),
           "resources": ARRAY(RESOURCE), "duration_models": {"type": "object", "additionalProperties": DURATION},
           "events": ARRAY({"oneOf": [obj({**BASE_EVENT, "type": {"const": k}, **v}) for k, v in EVENT_FIELDS.items()]}),
           "expected_invariants": ARRAY(S)})}

SOURCES = [
    ("t49_container", "Terminal49 container fields", "https://terminal49.com/docs/api-docs/api-reference/containers/get-a-container",
     "Container resource attributes and relationships; no guarantee of all fields for every account."),
    ("t49_holds", "Terminal49 holds and fees", "https://terminal49.com/docs/api-docs/in-depth-guides/holds-and-fees",
     "Hold statuses include hold/pending; a cleared hold is removed, not changed to a released status."),
    ("lafd_battery_2024", "LAFD battery truck incident account", "https://lafd.org/news/lithiumion-batteries-burn-days-after-san-pedro-big-rig-crash",
     "Records the September 2024 battery truck incident and subsequent clearance. Does not provide this cohort or simulation timings."),
    ("pola_reopening_2024", "Port of LA road reopening update", "https://portoflosangeles.org/references/2024-news-releases/news_092724_truck_accident",
     "Reports roads open and expected terminal recovery; expectation is not confirmation of full recovery."),
    ("one_fee_notice_2024", "ONE customer notice", "https://us.one-line.com/news/us-los-angeles-terminal-truck-incident",
     "Carrier-specific fee-clock notice; not a universal waiver and not a quantified saving for this cohort."),
    ("maersk_cyber_2017", "Maersk cyber incident update", "https://investor.maersk.com/news-releases/news-release-details/cyber-attack-update",
     "June 2017 cyber incident affected systems and operations. Does not establish a Terminal49 outage."),
    ("torres_cyber_2017", "Torres official statement", "https://torres.house.gov/media-center/press-releases/torres-introduces-port-cybersecurity-legislation-following-cyber-attack",
     "Official statement discusses the LA terminal disruption; not a complete operating timeline."),
    ("apm_recovery_2017", "APM recovery update", "https://www.apmterminals.com/en/news/news-releases/2017/cyber-attack-updae-friday",
     "Describes staged recovery of LA gate services, not proof of full recovery at every terminal."),
    ("pola_backlog_2021", "Port of LA backlog and proposed fee", "https://portoflosangeles.org/references/2021-news-releases/news_102931_cargofee",
     "Port announcement described roughly 40% of imports dwelling at least nine days; no historical container list is reproduced here."),
    ("pola_fee_never_activated", "Port of LA fee program conclusion", "https://portoflosangeles.org/references/2022-news-releases/news_121622_dwell_fee",
     "The proposed additional container dwell fee was never activated. Its accrued amount is zero in this historical-background scenario."),
    ("pola_hilary_2023", "Port of LA Hilary update", "https://portoflosangeles.org/references/2023-news-releases/news_081823_hurricane_hilary",
     "The August 21 update reported normal operations without damage. This is a warning/no-closure control, not a shutdown reconstruction."),
]


def timestamp(minutes=0):
    return (START + timedelta(minutes=minutes)).isoformat()


def uid(label):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "gate-triage-reference:" + label))


def fixture(raw, variant="normal"):
    data, mapping, containers = [], [], []
    for index, row in enumerate(raw):
        cid, rid = row["container_id"], uid(row["container_id"])
        original_hold = row["sources"]["customs"]["hold"]
        hero = cid == HERO
        hold = bool(original_hold or hero)
        unknown = index % 17 == 0 and not hero
        completed = index >= 97 and not hero
        holds = [{"name": "customs", "status": "hold", "description": "SYNTHETIC customs hold"}] if hold else []
        if not hold and index % 19 == 0:
            holds = [{"name": "customs", "status": "pending", "description": "SYNTHETIC pending notice"}]
        discharged = -1440 * ((9 + index % 4) if variant == "backlog" and index < 40 else (1 + index % 7))
        attrs = {"number": cid, "availability_known": not unknown, "available_for_pickup": not hold and not unknown,
                 "holds_at_pod_terminal": holds, "fees_at_pod_terminal": [], "weight_in_lbs": None,
                 "equipment_type": "reefer" if row["sources"].get("reefer") else "dry", "equipment_length": 40,
                 "pod_discharged_at": timestamp(discharged), "pod_full_out_at": timestamp(-60) if completed else None,
                 "terminal_checked_at": timestamp(), "pickup_lfd": timestamp(1440 * row["free_days_left"]),
                 "pickup_appointment_at": None if index % 7 == 0 else timestamp(30 + index % 60),
                 "location_at_pod_terminal": None,
                 "import_deadlines": {"pickup_lfd_line": timestamp(1440 * row["free_days_left"]),
                                      "pickup_lfd_terminal": timestamp(1440 * (row["free_days_left"] + (1 if index % 13 == 0 else 0))),
                                      "pickup_lfd_rail": None}}
        if unknown:
            attrs["holds_at_pod_terminal"] = None
        if variant == "equal":
            attrs.update(availability_known=True, available_for_pickup=True, holds_at_pod_terminal=[],
                         pod_full_out_at=None, pickup_appointment_at=timestamp())
        data.append({"id": rid, "type": "container", "attributes": attrs, "relationships": {}})
        mapping.append({"fixture_resource_id": rid, "container_number": cid, "original_index": index,
                        "original_record": deepcopy(row), "provenance": "synthetic_source_copy"})
        gate = "East" if row["zone"] == "B" else "West"
        if variant == "equal":
            gate = "Any"
        arrival = 0 if variant == "equal" or hero else index % 90
        reefer = row["sources"].get("reefer")
        weight = {"unit": "kg", "basis": "container_gross", "identity_verified": True,
                  "measurement_verified": True, "tare_kg": 3800,
                  "measured_kg": max(row["sources"]["scale"]["weight_kg"], 11800) if hero else row["sources"]["scale"]["weight_kg"],
                  "declared_status": "empty" if hero else row["sources"]["carrier"]["declared_status"],
                  "declared_kg": 3800 if hero else row["sources"]["carrier"]["declared_weight_kg"],
                  "provenance": "synthetic"}
        jobs = []
        if variant != "equal" and (index % 5 == 0 or hero):
            jobs.append({"id": cid + ":weight_check:1", "kind": "weight_check", "predecessors": [],
                         "resource_options": ["scale-1"], "requires_all": ["yard-crew"],
                         "outcome": "waiting_evidence", "duration_model": "weight_check"})
        if variant != "equal" and hero:
            jobs.append({"id": cid + ":reefer_check:1", "kind": "reefer_check", "predecessors": [],
                         "resource_options": ["reefer-tech"], "requires_all": [],
                         "outcome": "waiting_evidence", "duration_model": "reefer_check"})
        gates = ["east-lane-1", "east-lane-2"] if gate == "East" else ["west-lane-1", "west-lane-2"]
        if variant == "equal":
            gates = ["east-lane-1", "west-lane-1"]
        jobs.append({"id": cid + ":gate_handoff:1", "kind": "gate_handoff", "predecessors": [j["id"] for j in jobs],
                     "resource_options": gates, "requires_all": [], "outcome": "valid_gate_handoff",
                     "duration_model": "gate_handoff", "requires_current_departure_eligibility": True})
        containers.append({"container_id": cid, "resource_id": rid, "provenance": "synthetic", "gate": gate,
                           "arrival_at_min": arrival, "stakeholder_group": "truck-group-" + str(index % 4),
                           "source_state_is_not_physical_authorization": True, "jobs": jobs,
                           "site_evidence": {} if variant == "equal" else {"weight": weight,
                              "reefer": None if not reefer else {"temp_c": max(reefer["temp_c"], reefer["setpoint_c"] + 3.8) if hero else reefer["temp_c"],
                                  "setpoint_c": reefer["setpoint_c"], "observed_at_min": 0 if hero else -reefer["last_ping_min"], "provenance": "synthetic"}},
                           "simulated_prerequisites": {"appointment_ready": True, "payment_ready": True,
                               "documents_ready": True, "movement_authorized": variant == "equal" or (not hold and not unknown and not completed and index % 11 != 0)},
                           "demonstration_flags": ["HERO: empty/weight conflict + warming + customs hold"] if hero and variant != "equal" else []})
    wrapper = {"provenance": {"kind": "synthetic", "description": "Invented Terminal49-shaped collection; not an API response or historical reconstruction.",
                "source_refs": ["t49_container", "t49_holds"]}, "response": {"data": data, "included": []}}
    overlay = {"schema_version": "operator-overlay-1", "provenance": {"kind": "synthetic", "description": "All resources, job models, approvals and sensor values are invented demo inputs.", "source_refs": []},
               "hero_id": None if variant == "equal" else HERO, "containers": containers,
               "policies": {"verification_completion_clears_holds": False, "normal_temperature_certifies_cargo": False,
                            "additional_2021_port_dwell_fee_activated": False, "additional_2021_port_dwell_fee_usd": 0},
               "duration_semantics": "Sample hidden world durations by seed/container/job/episode/attempt/resource_class; same keyed samples across policies.",
               "demand_semantics": "Multiplier compresses only future, still-unobserved fixture interarrival intervals; it creates no extra containers.",
               "movement_semantics": "Readiness flags are demo assumptions; departure still checks reported holds, unknown evidence and current resources."}
    return wrapper, overlay, mapping


def event(kind, at, observed=None, **payload):
    return {"event_id": "", "type": kind, "published_at_min": at, "observed_at_min": at if observed is None else observed,
            "applies_at_min": at, "provenance": "synthetic", **payload}


def build():
    raw_path = REPO / "data/containers.json"
    raw = json.loads(raw_path.read_text())
    if len(raw) != 100:
        raise ValueError("Reference pack requires the current 100-record source cohort")
    write("scenario.schema.json", SCHEMA)
    write("source-manifest.json", {"schema_version": "source-manifest-1", "runtime_external_business_provider": "Terminal49 only",
        "sources": [{"id": id_, "title": title, "url": url, "supported_background": facts,
                     "runtime_input": False} for id_, title, url, facts in SOURCES]})
    hashes = {}
    for variant, name in [("normal", "t49-cohort-100"), ("backlog", "t49-backlog-100"), ("equal", "t49-equal-service-100")]:
        cohort, overlay, mapping = fixture(raw, variant)
        a, b = "fixtures/" + name + ".json", "fixtures/" + name + ".operator-overlay.json"
        hashes[variant] = (a, write(a, cohort), b, write(b, overlay))
        if variant == "normal":
            write("fixtures/source-record-mapping.json", {"input_path": "data/containers.json", "input_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                "note": "Byte source unchanged. Original records copied here; collection attributes and overlays are separate synthetic transformations.", "records": mapping})
    resources = [{"id": f"{gate.lower()}-lane-{i}", "kind": "gate_lane", "capacity": 1, "gate": gate, "provenance": "synthetic"}
                 for gate in ("East", "West") for i in (1, 2)]
    resources += [{"id": "scale-1", "kind": "scale", "capacity": 1, "gate": "Any", "provenance": "synthetic"},
                  {"id": "yard-crew", "kind": "crew", "capacity": 2, "gate": "Any", "provenance": "synthetic"},
                  {"id": "reefer-tech", "kind": "reefer_technician", "capacity": 1, "gate": "Any", "provenance": "synthetic"}]
    durations = {"gate_handoff": {"distribution": "triangular", "minutes": [3, 5, 9]},
                 "weight_check": {"distribution": "triangular", "minutes": [6, 10, 16]},
                 "reefer_check": {"distribution": "triangular", "minutes": [5, 8, 14]}}
    road = lambda t, state, capacity, observed=None: event("resource.availability", t, observed, resource_ids=["east-lane-1", "east-lane-2"], state=state, capacity=capacity)
    feed = lambda t, state: event("provider.connectivity", t, provider_id="terminal49_simulated", scope="synthetic-terminal", state=state)
    evidence = lambda t, namespace, patch, observed=None, evid=None: event("evidence.update", t, observed, container_id=HERO, namespace=namespace,
        evidence_id=evid or "hero-evidence-" + str(t), patch=patch)
    definitions = [
        ("normal_operations", "normal", [], []),
        ("battery_truck_access_2024", "normal", ["lafd_battery_2024", "pola_reopening_2024", "one_fee_notice_2024"], [
            road(30, "closed", 0, 32), evidence(45, "operator", {"weight": {"measured_kg": 16100, "declared_kg": 16100, "declared_status": "laden", "unit": "kg", "basis": "container_gross"}}),
            evidence(60, "operator", {"reefer": {"temp_c": 2.0, "setpoint_c": 2.0}}), road(90, "restricted", 1), road(120, "open", 2),
            evidence(140, "provider", {"holds_at_pod_terminal": [], "available_for_pickup": True, "availability_known": True})]),
        ("terminal_data_disruption_2017", "normal", ["maersk_cyber_2017", "torres_cyber_2017", "apm_recovery_2017"], [
            feed(20, "offline"), road(35, "closed", 0),
            evidence(10, "provider", {"holds_at_pod_terminal": []}, 70, "late-old-clearance"),
            evidence(15, "provider", {"holds_at_pod_terminal": [{"name": "customs", "status": "hold", "description": "Synthetic retained hold"}]}, 70, "late-hold"),
            evidence(10, "provider", {"holds_at_pod_terminal": []}, 70, "late-old-clearance"), feed(100, "partial"), road(130, "restricted", 1), feed(160, "online"), road(160, "open", 2)]),
        ("long_dwell_backlog_2021", "backlog", ["pola_backlog_2021", "pola_fee_never_activated"], [
            event("demand.multiplier", 10, multiplier=3, scope="unobserved_fixture_arrivals"),
            event("demand.multiplier", 60, multiplier=1, scope="unobserved_fixture_arrivals"),
            event("warning.received", 20, code="historical_fee_never_activated", message="Record announcement background only; additional historical port fee remains zero.", action="record_policy_only")]),
        ("weather_warning_no_closure_2023", "normal", ["pola_hilary_2023"], [
            event("warning.received", 20, code="weather_attention", message="Synthetic warning received; no closure evidence. Preserve normal resource availability.", action="attention_only")]),
        ("equal_service_control", "equal", [], []),
    ]
    for sid, variant, refs, events in definitions:
        a, ah, b, bh = hashes[variant]
        for i, item in enumerate(events):
            item["event_id"] = sid + "-" + str(i + 1)
        scenario = {"schema_version": "simulation-1", "scenario_id": sid, "seed": 17, "start_at": START.isoformat(), "horizon_minutes": 240,
            "provenance": {"kind": "synthetic", "description": "Compressed hypothetical exercise; historical sources explain background only, never resource counts or timings.", "source_refs": refs},
            "containers_fixture": {"path": a, "sha256": ah, "mode": "synthetic", "overlay_path": b, "overlay_sha256": bh},
            "planning": {"lookahead_minutes": 60, "replan_minutes": 5, "freeze_minutes": 5}, "resources": deepcopy(resources),
            "duration_models": deepcopy(durations), "events": events,
            "expected_invariants": ["Known holds remain blocking through outages and road recovery.", "Verification never implies clearance or cargo quality acceptance.",
                                    "Only valid completed gate handoffs count as throughput.", "No future observations are exposed to policies."]}
        if variant == "equal":
            scenario["resources"] = [r for r in resources if r["id"] in {"east-lane-1", "west-lane-1"}]
            scenario["duration_models"] = {"gate_handoff": {"distribution": "constant", "minutes": [5]}}
            scenario["expected_invariants"] = ["100 arrivals at time zero, two equivalent lanes, deterministic five-minute jobs.", "Every work-conserving feasible policy completes min(100, 2*floor(240/5)) = 96; four remain right-censored."]
        write("scenarios/" + sid + ".json", scenario)
    print("Built six scenario configurations and separate 100-container fixtures; application code untouched.")


if __name__ == "__main__":
    build()
