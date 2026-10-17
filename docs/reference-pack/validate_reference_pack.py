"""Validate documentation fixtures, not the application or solver.

Install jsonschema separately or use --structural-only for stdlib integrity
checks. Full validation requires JSON Schema Draft 2020-12 support.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = {"normal_operations", "battery_truck_access_2024", "terminal_data_disruption_2017",
            "long_dwell_backlog_2021", "weather_warning_no_closure_2023", "equal_service_control"}
PROVIDER_FIELDS = {"number", "availability_known", "available_for_pickup", "holds_at_pod_terminal",
                   "fees_at_pod_terminal", "weight_in_lbs", "equipment_type", "equipment_length",
                   "pod_discharged_at", "pod_full_out_at", "terminal_checked_at", "pickup_lfd",
                   "pickup_appointment_at", "location_at_pod_terminal", "import_deadlines"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def path(value):
    resolved = (ROOT / value).resolve()
    require(resolved.is_relative_to(ROOT) and resolved.is_file(), "Missing/escaping path: " + value)
    return resolved


def read(value):
    return json.loads(path(value).read_text(encoding="utf-8"))


def validate(structural_only=False):
    schema = read("scenario.schema.json")
    validator = None
    if not structural_only:
        try:
            from jsonschema import Draft202012Validator, FormatChecker
        except ImportError as error:
            raise SystemExit("Full validation needs jsonschema; install it separately or explicitly use --structural-only.") from error
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
    sources = read("source-manifest.json")["sources"]
    source_ids = {s["id"] for s in sources}
    require(len(source_ids) == len(sources), "Duplicate source ids")
    mapping = read("fixtures/source-record-mapping.json")
    require(len(mapping["records"]) == 100, "Source mapping must preserve 100 records")
    original = ROOT.parents[1] / mapping["input_path"]
    require(hashlib.sha256(original.read_bytes()).hexdigest() == mapping["input_sha256"], "Original source changed after fixture build")
    require([m["original_record"] for m in mapping["records"]] == json.loads(original.read_text()), "Original records not preserved")
    seen = set()
    for file in sorted((ROOT / "scenarios").glob("*.json")):
        s = json.loads(file.read_text())
        if validator:
            validator.validate(s)
        sid = s["scenario_id"]
        require(sid not in seen, "Duplicate scenario")
        seen.add(sid)
        require(set(s["provenance"]["source_refs"]) <= source_ids, "Unknown scenario source")
        f = s["containers_fixture"]
        for key, digest in [("path", "sha256"), ("overlay_path", "overlay_sha256")]:
            require(hashlib.sha256(path(f[key]).read_bytes()).hexdigest() == f[digest], "Fixture hash mismatch: " + f[key])
        cohort, overlay = read(f["path"]), read(f["overlay_path"])
        require(cohort["provenance"]["kind"] == "synthetic", "Fixture not labeled synthetic")
        require(set(cohort["provenance"]["source_refs"]) <= source_ids, "Unknown fixture source")
        data = cohort["response"]["data"]
        require(len(data) == len(overlay["containers"]) == 100, "Cohort/overlay size mismatch")
        by_number = {c["attributes"]["number"]: c for c in data}
        require(len(by_number) == 100, "Duplicate container number")
        require(len({c["id"] for c in data}) == 100, "Duplicate provider resource id")
        for c in data:
            attrs = c["attributes"]
            require(c["type"] == "container", "Invalid resource type")
            require(set(attrs) <= PROVIDER_FIELDS, "Site-only or unknown field leaked into provider attributes")
            for hold in attrs.get("holds_at_pod_terminal") or []:
                require(set(hold) == {"name", "status", "description"} and hold["status"] in {"hold", "pending"}, "Malformed hold")
        resources = {r["id"]: r for r in s["resources"]}
        require(len(resources) == len(s["resources"]), "Duplicate resource")
        for name, d in s["duration_models"].items():
            values = d["minutes"]
            require(len(values) == (1 if d["distribution"] == "constant" else 3) and values == sorted(values), "Invalid duration model " + name)
        for c in overlay["containers"]:
            require(c["container_id"] in by_number and c["resource_id"] == by_number[c["container_id"]]["id"], "Overlay identity mismatch")
            jobs = {j["id"]: j for j in c["jobs"]}
            require(len(jobs) == len(c["jobs"]), "Duplicate job")
            for j in jobs.values():
                require(set(j["resource_options"] + j["requires_all"]) <= resources.keys(), "Unknown job resource")
                require(j["duration_model"] in s["duration_models"], "Unknown duration model")
                require(set(j["predecessors"]) <= jobs.keys(), "Unknown predecessor")
            done = set()
            while len(done) < len(jobs):
                ready = {id_ for id_, j in jobs.items() if set(j["predecessors"]) <= done} - done
                require(bool(ready), "Cyclic job dependency")
                done |= ready
        event_ids = set()
        for e in s["events"]:
            require(e["event_id"] not in event_ids, "Duplicate delivery/event id")
            event_ids.add(e["event_id"])
            require(0 <= e["published_at_min"] <= e["observed_at_min"] <= s["horizon_minutes"], "Invalid publication/observation time")
            require(0 <= e["applies_at_min"] <= s["horizon_minutes"], "Invalid application time")
            if e["type"] == "resource.availability":
                require(set(e["resource_ids"]) <= resources.keys(), "Event references unknown resource")
                require(e["capacity"] <= sum(resources[r]["capacity"] for r in e["resource_ids"]), "Capacity above resource total")
                require(e["state"] != "closed" or e["capacity"] == 0, "Closed capacity must be zero")
            if e["type"] == "evidence.update":
                require(e["container_id"] in by_number, "Unknown event container")
                if e["namespace"] == "provider":
                    require(set(e["patch"]) <= PROVIDER_FIELDS, "Operator evidence masquerades as Terminal49 attributes")
        require(overlay["policies"]["additional_2021_port_dwell_fee_usd"] == 0, "Never-activated historical fee must be zero")
        if sid == "long_dwell_backlog_2021":
            start = datetime.fromisoformat(s["start_at"])
            count = sum((start - datetime.fromisoformat(c["attributes"]["pod_discharged_at"])).days >= 9 for c in data)
            require(count == 40, "Backlog fixture requires exactly 40% at least 9 days")
        if sid == "weather_warning_no_closure_2023":
            require(all(e["type"] == "warning.received" for e in s["events"]), "Warning fixture must not close resources")
        if sid == "equal_service_control":
            require(len(resources) == 2 and sum(r["capacity"] for r in resources.values()) == 2, "Equal service needs two lanes")
            require(s["duration_models"]["gate_handoff"]["minutes"] == [5], "Equal service must be five minutes")
            require(all(c["arrival_at_min"] == 0 and len(c["jobs"]) == 1 for c in overlay["containers"]), "Equal service jobs/arrivals invalid")
            require(all(c["attributes"]["availability_known"] and c["attributes"]["available_for_pickup"] and c["attributes"]["holds_at_pod_terminal"] == [] and c["attributes"]["pod_full_out_at"] is None for c in data), "Equal service must have 100 initially eligible, unfinished containers")
            require(min(len(data), 2 * (s["horizon_minutes"] // 5)) == 96, "Equal service expected count mismatch")
    require(seen == EXPECTED, "Missing or extra canonical scenarios")
    print(f"PASS: {len(seen)} scenarios; schema={'Draft 2020-12' if validator else 'SKIPPED (structural only)'}; source references, paths, hashes, originals, 100-record cohorts, job/resource links, DAGs, timestamps, provider isolation and scenario invariants checked.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--structural-only", action="store_true")
    validate(parser.parse_args().structural_only)
