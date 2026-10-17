#!/usr/bin/env python3
"""Reproducible, resumable paired synthetic workbench benchmark.

Example: .venv/bin/python scripts/benchmark_workbench.py --workers 2
Each world is executed through minute 240, with immutable 90/240 checkpoints.
The six scenario policies have identical samples and feasible execution guards.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCENARIOS = ["normal_operations", "battery_truck_access_2024", "terminal_data_disruption_2017",
             "long_dwell_backlog_2021", "weather_warning_no_closure_2023", "equal_service_control"]
STRATEGIES = ("fifo", "priority", "optimized")
HORIZONS = (90, 240)
ENGINE_PATHS = [ROOT / "gate_triage/workbench" / name for name in ("engine.py", "scheduler.py", "simulation.py")]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * q
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def trace_audit(state: dict) -> list[str]:
    """Offline independent audit of the actual sampled execution trace.

    The auditor can inspect historical world calendars; these calendars are
    never passed as future information to a scheduling policy.
    """
    errors = []
    horizon = state["clock_min"]
    occupancy = {rid: [0] * horizon for rid in state["resources"]}
    seen_handoffs = set()
    finished_at = {}
    trace = sorted(state["execution_log"] + state["running"], key=lambda op: (op["start_min"], op["end_min"], op["task_id"]))
    for operation in trace:
        original = state["operations"][operation["task_id"]]
        resources = operation["resource_ids"]
        if not any(rid in original["resource_options"] for rid in resources):
            errors.append(f"incompatible_resource:{operation['task_id']}")
        if not set(original.get("requires_all", [])) <= set(resources):
            errors.append(f"missing_joint_resource:{operation['task_id']}")
        end = min(horizon, operation.get("interrupted_at_min", operation["end_min"]))
        for rid in resources:
            for minute in range(operation["start_min"], end):
                occupancy[rid][minute] += 1
        if operation["status"] == "completed":
            finished_at[operation["task_id"]] = operation["end_min"]
            if operation["kind"] == "gate_handoff":
                if operation["container_id"] in seen_handoffs:
                    errors.append(f"duplicate_handoff:{operation['container_id']}")
                seen_handoffs.add(operation["container_id"])
    for operation in trace:
        for predecessor in state["operations"][operation["task_id"]].get("predecessors", []):
            if predecessor not in finished_at or finished_at[predecessor] > operation["start_min"]:
                errors.append(f"unmet_predecessor:{operation['task_id']}:{predecessor}")
    events = sorted((e for e in state["config"]["events"] if e["type"] == "resource.availability"), key=lambda e: e["applies_at_min"])
    for rid, samples in occupancy.items():
        initial = state["resources"][rid]["capacity"]
        for minute, count in enumerate(samples):
            capacity = initial
            for event in events:
                if event["applies_at_min"] > minute:
                    break
                if rid in event["resource_ids"]:
                    capacity = min(initial, max(0, event["capacity"] - event["resource_ids"].index(rid)))
            if count > capacity:
                errors.append(f"resource_over_capacity:{rid}:minute{minute}:{count}>{capacity}")
    if len(seen_handoffs) != len(state["completed"]):
        errors.append("completion_count_disagrees_with_actual_trace")
    return list(dict.fromkeys(errors))


def checkpoint(state: dict, strategy: str, wall_seconds: float, start_hashes: dict) -> dict:
    from gate_triage.workbench.engine import snapshot
    snap = snapshot(state)
    waits = [state["clock_min"] - c["arrival_at_min"] for c in state["containers"].values() if c["arrived"] and c["completed_at_min"] is None]
    groups = snap["metrics"]["stakeholder_groups"]
    means = [g["avg_wait_minutes"] for g in groups if g["arrived"]]
    durations = {key: op["duration"] for key, op in sorted(state["operations"].items())}
    arrivals = {key: c["arrival_at_min"] for key,c in sorted(state["containers"].items())}
    world = {"durations": durations, "arrivals": arrivals, "scenario_hash": digest(ROOT / "docs/reference-pack/scenarios" / f"{state['scenario_id']}.json")}
    return {"scenario_id": state["scenario_id"], "seed": state["seed"], "strategy": strategy, "profile": "throughput",
            "horizon_minutes": state["clock_min"], "status": "ok", "completed_handoffs": len(state["completed"]),
            "avg_wait_minutes": snap["overview"]["avg_wait_minutes"], "p90_wait_minutes": snap["overview"]["p90_wait_minutes"],
            "completed_wait_sample_size": snap["metrics"]["completed_wait_sample_size"],
            "unfinished_backlog": snap["overview"]["backlog"], "unfinished_wait_lower_bound_mean": snap["metrics"]["unfinished_wait_lower_bound_mean"],
            "unfinished_wait_lower_bound_max": max(waits, default=0),
            "service_group_mean_wait_spread": round(max(means)-min(means),2) if means else 0,
            "stakeholder_groups": groups, "reported_departed_before_run": snap["overview"]["reported_departed"],
            "constraint_violations": state["metrics"]["constraint_violations"],
            "invalid_action_attempts": state["metrics"]["invalid_action_attempts"],
            "new_information_rejections": state["metrics"]["new_information_rejections"],
            "independent_trace_audit_errors": trace_audit(state),
            "solver_status_counts": state["metrics"].get("solver_status_counts", {}),
            "solver_fallbacks": state["metrics"].get("solver_fallbacks", 0),
            "plan_validation_rejections": state["metrics"].get("plan_validation_rejections", 0),
            "total_solver_ms": state["metrics"].get("total_solver_ms", 0),
            "wall_seconds": round(wall_seconds,4),
            "world_sample_hash": hashlib.sha256(json.dumps(world, sort_keys=True).encode()).hexdigest(),
            "service_sample_hash": hashlib.sha256(json.dumps(durations, sort_keys=True).encode()).hexdigest(),
            "engine_hashes": start_hashes, "curves": state["curves"]}


def execute_world(arguments: tuple) -> list[dict]:
    scenario, seed, strategy, expected_hashes = arguments
    from gate_triage.workbench.engine import create_state
    from gate_triage.workbench.simulation import advance
    actual = {str(path.relative_to(ROOT)): digest(path) for path in ENGINE_PATHS}
    if actual != expected_hashes:
        return [{"scenario_id": scenario,"seed":seed,"strategy":strategy,"horizon_minutes":h,"status":"error","error":"Engine changed during benchmark; rerun with a new output directory"} for h in HORIZONS]
    started = time.monotonic()
    try:
        state = create_state(scenario, seed)
        result = []
        for horizon in HORIZONS:
            advance(state, horizon-state["clock_min"], strategy, "throughput")
            result.append(checkpoint(state, strategy, time.monotonic()-started, expected_hashes))
        return result
    except Exception as error:
        return [{"scenario_id":scenario,"seed":seed,"strategy":strategy,"horizon_minutes":h,"status":"error","error":f"{type(error).__name__}: {error}"} for h in HORIZONS]


def bootstrap_interval(differences: list[float], key: str, resamples: int = 10000):
    if len(differences) < 10:
        return None
    rng = random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],"big"))
    n = len(differences)
    samples = [sum(differences[rng.randrange(n)] for _ in range(n))/n for _ in range(resamples)]
    return [round(percentile(samples,.025),4),round(percentile(samples,.975),4)]


def summarize(rows: list[dict], metadata: dict) -> dict:
    summaries = []
    failures = [r for r in rows if r["status"] != "ok"]
    pair_failures = []
    compute_intervals = len(rows) == metadata["expected_rows"]
    for scenario in metadata["scenarios"]:
        for horizon in HORIZONS:
            subset = [r for r in rows if r["scenario_id"]==scenario and r["horizon_minutes"]==horizon]
            by_strategy = {}
            for strategy in STRATEGIES:
                runs = [r for r in subset if r["strategy"]==strategy and r["status"]=="ok"]
                if not runs:
                    continue
                metrics = {}
                for metric in ("completed_handoffs","avg_wait_minutes","p90_wait_minutes","unfinished_backlog","unfinished_wait_lower_bound_mean","unfinished_wait_lower_bound_max","service_group_mean_wait_spread","wall_seconds"):
                    values = [r[metric] for r in runs]
                    metrics[metric] = {"mean":round(statistics.mean(values),4),"min":min(values),"max":max(values),"p90_across_runs":round(percentile(values,.9),4)}
                by_strategy[strategy] = {"runs":len(runs),"metrics":metrics,
                    "constraint_violations":sum(r["constraint_violations"] for r in runs),"invalid_action_attempts":sum(r["invalid_action_attempts"] for r in runs),
                    "trace_audit_errors":sum(len(r["independent_trace_audit_errors"]) for r in runs),"solver_fallbacks":sum(r["solver_fallbacks"] for r in runs),
                    "plan_validation_rejections":sum(r["plan_validation_rejections"] for r in runs)}
            paired = []
            for baseline in ("fifo","priority"):
                baseline_runs = {r["seed"]:r for r in subset if r["status"]=="ok" and r["strategy"]==baseline}
                optimized_runs = {r["seed"]:r for r in subset if r["status"]=="ok" and r["strategy"]=="optimized"}
                seeds = sorted(set(baseline_runs)&set(optimized_runs))
                good_pairs = []
                for seed in seeds:
                    if baseline_runs[seed]["world_sample_hash"] != optimized_runs[seed]["world_sample_hash"]:
                        pair_failures.append({"scenario_id":scenario,"horizon_minutes":horizon,"seed":seed,"baseline":baseline})
                    else:
                        good_pairs.append(seed)
                differences = {}
                for metric in ("completed_handoffs","avg_wait_minutes","p90_wait_minutes","unfinished_backlog","unfinished_wait_lower_bound_mean","unfinished_wait_lower_bound_max","service_group_mean_wait_spread"):
                    values = [optimized_runs[s][metric]-baseline_runs[s][metric] for s in good_pairs]
                    if values:
                        differences[metric] = {"mean_difference":round(statistics.mean(values),4),"min_difference":min(values),"max_difference":max(values),
                            "bootstrap_percentile_95_ci":bootstrap_interval(values,f"{scenario}:{horizon}:{baseline}:{metric}") if compute_intervals else None,
                            "positive":sum(v>0 for v in values),"zero":sum(v==0 for v in values),"negative":sum(v<0 for v in values)}
                paired.append({"baseline":baseline,"paired_seeds":good_pairs,"differences_optimized_minus_baseline":differences})
            summaries.append({"scenario_id":scenario,"horizon_minutes":horizon,"strategies":by_strategy,"paired":paired})
    return {"metadata_file":"metadata.json","raw_file":"runs.jsonl","generated_at":datetime.now(timezone.utc).isoformat(),
            "rows":len(rows),"expected_rows":metadata["expected_rows"],"complete":len(rows)==metadata["expected_rows"],
            "failures":failures,"world_pair_mismatches":pair_failures,"comparisons":summaries,
            "ci_method":"10,000 deterministic paired-seed bootstrap resamples, percentile 2.5/97.5%; no CI when n<10. Computed after the full matrix completes. Descriptive, unadjusted for multiple comparisons.",
            "scope":"Synthetic internal-policy comparison; no commercial product or real terminal was benchmarked."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"evaluation/workbench-2026-10-17")
    parser.add_argument("--workers",type=int,default=2)
    parser.add_argument("--control-seeds",type=int,default=3)
    parser.add_argument("--seed-start",type=int,default=17)
    parser.add_argument("--seed-count",type=int,default=30)
    parser.add_argument("--scenarios",nargs="+",choices=SCENARIOS,default=SCENARIOS)
    args=parser.parse_args()
    if not 1<=args.workers<=4 or not 1<=args.seed_count<=30 or not 1<=args.control_seeds<=30:
        parser.error("workers must be1–4; seed counts1–30")
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    hashes={str(path.relative_to(ROOT)):digest(path) for path in ENGINE_PATHS}
    versions={name:importlib.metadata.version(name) for name in ("ortools","numpy","fastapi","sqlalchemy")}
    config_paths=list((ROOT/"docs/reference-pack/scenarios").glob("*.json"))+list((ROOT/"docs/reference-pack/fixtures").glob("*.json"))
    expected=sum((min(args.control_seeds,args.seed_count) if s=="equal_service_control" else args.seed_count)*len(STRATEGIES)*len(HORIZONS) for s in args.scenarios)
    metadata={"schema":"workbench-benchmark-1","started_at":datetime.now(timezone.utc).isoformat(),"scenarios":args.scenarios,"seed_start":args.seed_start,"seed_count":args.seed_count,"control_seed_count":min(args.control_seeds,args.seed_count),
        "control_reduction_reason":"The equal-service control has constant durations and identical initially ready work. Three seeds retain the deterministic capacity check while avoiding 27 redundant control repeats.",
        "horizons":list(HORIZONS),"strategies":list(STRATEGIES),"profile":"throughput","expected_rows":expected,
        "runtime":{"python":sys.version,"platform":platform.platform(),"machine":platform.machine(),"cpu_count":os.cpu_count(),"process_workers":args.workers,"dependencies":versions},
        "solver":{"workers_per_solve":1,"max_wall_seconds_per_solve":.08,"seed":"world seed","reproducibility_limit":"World samples are deterministic. Bounded wall-clock CP-SAT search can vary with CPU contention; all statuses/fallbacks and results are retained."},
        "engine_hashes":hashes,"benchmark_script_hash":digest(Path(__file__).resolve()),
        "fixture_hashes":{str(path.relative_to(ROOT)):digest(path) for path in sorted(config_paths)},
        "definitions":{"wait":"External arrival to gate-service start among completed handoffs only.","censored_wait":"Elapsed arrival-to-observation lower bound for unfinished arrived containers.","group_wait":"Mean arrival-to-gate-start or observation time across arrived group members, including unfinished/blocked; descriptive, not an eligible-wait guarantee.","group_spread":"Maximum minus minimum group mean wait among groups with arrivals.","paired_unit":"Same scenario, seed and horizon; same world_sample_hash required.","checkpoint_reuse":"One trajectory per policy through minute240, with90/240 checkpoints. Engine planning horizon remains240 in both checkpoints; the minute90 observation is not an artificial close of operations."}}
    try:
        metadata["git_head"]=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
        metadata["git_branch"]=subprocess.check_output(["git","branch","--show-current"],cwd=ROOT,text=True).strip()
    except subprocess.CalledProcessError:
        pass
    raw=output/"runs.jsonl"
    rows=[json.loads(line) for line in raw.read_text().splitlines()] if raw.exists() else []
    oldpath=output/"metadata.json"
    if oldpath.exists():
        previous=json.loads(oldpath.read_text())
        for key in ("engine_hashes","benchmark_script_hash","fixture_hashes","scenarios","seed_start","seed_count","control_seed_count","horizons","strategies","profile"):
            if previous.get(key)!=metadata.get(key):
                raise SystemExit(f"Cannot resume: {key} changed. Use another output directory.")
        metadata["started_at"]=previous["started_at"]
    write_json(oldpath,metadata)
    completed={(r["scenario_id"],r["seed"],r["strategy"]) for r in rows if r["horizon_minutes"]==240}
    seeds=range(args.seed_start,args.seed_start+args.seed_count)
    ordered=[]
    # Finish the two core scenarios first, without selecting outcomes.
    for seed in seeds:
        for scenario in args.scenarios[:2]:
            if scenario == "equal_service_control" and seed >= args.seed_start + min(args.control_seeds, args.seed_count):
                continue
            for strategy in STRATEGIES:
                ordered.append((scenario,seed,strategy,hashes))
    for scenario in args.scenarios[2:]:
        scenario_seeds=range(args.seed_start,args.seed_start+(min(args.control_seeds,args.seed_count) if scenario=="equal_service_control" else args.seed_count))
        for seed in scenario_seeds:
            for strategy in STRATEGIES:
                ordered.append((scenario,seed,strategy,hashes))
    jobs=[job for job in ordered if job[:3] not in completed]
    # Correct ordering also for a custom single-scenario smoke run.
    started=time.monotonic();count=0
    print(json.dumps({"status":"started","worlds_remaining":len(jobs),"expected_rows":expected,"output":str(output),"workers":args.workers}),flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures={executor.submit(execute_world,job):job for job in jobs}
        for future in as_completed(futures):
            job=futures[future]
            try:
                result=future.result()
            except Exception as error:
                result=[{"scenario_id":job[0],"seed":job[1],"strategy":job[2],"horizon_minutes":h,"status":"error","error":f"worker failure: {error}"} for h in HORIZONS]
            with raw.open("a") as handle:
                for row in result:
                    handle.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n")
            rows.extend(result);count+=1
            if count%10==0 or count==len(jobs):
                summary=summarize(rows,metadata);write_json(output/"summary.json",summary)
                print(json.dumps({"status":"progress","worlds_done":count,"worlds_total":len(jobs),"rows":len(rows),"elapsed_seconds":round(time.monotonic()-started,1),"last":job[:3],"failures":len(summary["failures"]),"pair_mismatches":len(summary["world_pair_mismatches"])}),flush=True)
    summary=summarize(rows,metadata);write_json(output/"summary.json",summary)
    metadata["finished_at"]=datetime.now(timezone.utc).isoformat();metadata["this_invocation_wall_seconds"]=round(time.monotonic()-started,3);write_json(oldpath,metadata)
    print(json.dumps({"status":"complete","rows":len(rows),"failures":len(summary["failures"]),"world_pair_mismatches":len(summary["world_pair_mismatches"]),"elapsed_seconds":metadata["this_invocation_wall_seconds"]}),flush=True)
    return 0 if not summary["failures"] and not summary["world_pair_mismatches"] and summary["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
