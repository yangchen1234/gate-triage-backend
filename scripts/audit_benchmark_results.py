"""Independent arithmetic audit: stdlib only, no simulator/benchmark imports.

This checks saved evidence, not whether the synthetic world matches a real port.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / "evaluation/workbench-2026-10-17"
    raw = folder / "runs.jsonl"
    rows = [json.loads(line) for line in raw.read_text().splitlines() if line.strip()]
    summary = json.loads((folder / "summary.json").read_text())
    failures, checks = [], 0

    def check(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(message)

    keys = [(r["scenario_id"], r["seed"], r["strategy"], r["horizon_minutes"]) for r in rows]
    check(len(rows) == 918 == len(set(keys)), "918 unique checkpoint rows required")
    check(summary["complete"] and not summary["failures"], "run summary must be complete without hidden failures")
    indexed = dict(zip(keys, rows))
    worlds = defaultdict(list)
    for row in rows:
        worlds[row["scenario_id"], row["seed"], row["horizon_minutes"]].append(row)
        check(row["status"] == "ok", f"Failed run {row}")
        check(row["completed_handoffs"] == row["completed_wait_sample_size"], "Completed wait denominator differs")
        check(not row["independent_trace_audit_errors"] and row["constraint_violations"] == 0, "Trace failure")
        check(all(c["minute"] <= row["horizon_minutes"] for c in row["curves"]), "Checkpoint contains future curve data")
        if row["scenario_id"] == "equal_service_control":
            check(row["completed_handoffs"] == 2 * (row["horizon_minutes"] // 5), "Control capacity is wrong")
    for key, records in worlds.items():
        check(len(records) == 3 and len({r["world_sample_hash"] for r in records}) == 1, f"Unpaired world {key}")
        check(len({r["service_sample_hash"] for r in records}) == 1, f"Unpaired duration samples {key}")
    metrics = ["completed_handoffs", "avg_wait_minutes", "p90_wait_minutes", "unfinished_backlog", "unfinished_wait_lower_bound_mean", "unfinished_wait_lower_bound_max", "service_group_mean_wait_spread"]
    observed = []
    for comparison in summary["comparisons"]:
        scenario, horizon = comparison["scenario_id"], comparison["horizon_minutes"]
        for strategy, aggregate in comparison["strategies"].items():
            selected = [r for r in rows if (r["scenario_id"],r["horizon_minutes"],r["strategy"]) == (scenario,horizon,strategy)]
            check(len(selected) == aggregate["runs"], "Aggregate denominator differs")
            for metric in metrics:
                actual = statistics.mean(r[metric] for r in selected)
                check(abs(actual - aggregate["metrics"][metric]["mean"]) < .000051, f"Mean mismatch {scenario}/{horizon}/{strategy}/{metric}")
        for paired in comparison["paired"]:
            seeds = paired["paired_seeds"]
            for metric in metrics:
                differences = [indexed[scenario,s,"optimized",horizon][metric] - indexed[scenario,s,paired["baseline"],horizon][metric] for s in seeds]
                aggregate = paired["differences_optimized_minus_baseline"][metric]
                check(abs(statistics.mean(differences) - aggregate["mean_difference"]) < .000051, "Paired mean mismatch")
                for label, predicate in [("positive",lambda x:x>0),("zero",lambda x:x==0),("negative",lambda x:x<0)]:
                    check(sum(predicate(d) for d in differences) == aggregate[label], "Win / tie / loss mismatch")
            if paired["baseline"] == "fifo":
                observed.append({"scenario":scenario,"horizon":horizon,"completed_difference":round(statistics.mean(indexed[scenario,s,"optimized",horizon]["completed_handoffs"]-indexed[scenario,s,"fifo",horizon]["completed_handoffs"] for s in seeds),4)})
    result = {"method":"Independent stdlib arithmetic, denominator, unique-key and pairing checks; no engine or benchmark helper imported.","raw_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),"checkpoint_rows":len(rows),"worlds":len(rows)//2,"checks":checks,"failures":failures,"observed":observed,"scope":"Saved synthetic results only; not commercial head-to-head performance or physical-port validation."}
    (folder / "independent-check.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("checkpoint_rows","worlds","checks","failures")},indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
