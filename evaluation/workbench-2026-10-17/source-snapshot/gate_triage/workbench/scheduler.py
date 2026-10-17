"""Observed-state scheduling with CP-SAT and independently validated baselines."""
from __future__ import annotations

import time
import hashlib
import json
from collections import defaultdict
from typing import Any

from .engine import _available_capacity, _eligibility, _priority

PROFILES = {"throughput", "balanced", "recovery"}
STRATEGIES = {"optimized", "fifo", "priority"}


def state_fingerprint(state: dict) -> str:
    """Bind a candidate to observed decision inputs, excluding hidden events."""
    inputs = {"clock": state["clock_min"], "mode": state["mode"], "resources": state["resources"],
              "running": state["running"], "provider_online": state["provider_online"],
              "customs_online": state["customs_online"], "power_enabled": state["power_enabled"],
              "containers": {key: {field: c[field] for field in ("provider", "site", "prerequisites", "arrived", "arrival_at_min", "completed_at_min")} for key,c in state["containers"].items()},
              "operations": {key: op["status"] for key,op in state["operations"].items()}}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _expected_duration(state: dict, operation: dict) -> int:
    model = state["config"]["duration_models"][operation["duration_model"]]
    # The planner receives a distribution, never the future sampled service time.
    return max(1, int(round(sum(model["minutes"]) / len(model["minutes"]))))


def candidates(state: dict) -> tuple[list[dict], list[dict]]:
    jobs, skipped = [], []
    for op in state["operations"].values():
        if op["status"] != "pending":
            continue
        c = state["containers"][op["container_id"]]
        if not c["arrived"]:
            continue
        if op["kind"] == "gate_handoff":
            eligibility = _eligibility(state, c, include_lane=False)
            if eligibility["status"] != "allowed":
                skipped.append({"task_id": op["id"], "container_id": c["container_id"], "reasons": eligibility["reasons"]})
                continue
        choices = [rid for rid in op["resource_options"] if rid in state["resources"] and _available_capacity(state, state["resources"][rid]) > 0]
        required = [rid for rid in op.get("requires_all", [])]
        if not choices or any(rid not in state["resources"] or _available_capacity(state, state["resources"][rid]) <= 0 for rid in required):
            skipped.append({"task_id": op["id"], "container_id": c["container_id"], "reasons": ["Required compatible resource unavailable in the observed snapshot"]})
            continue
        jobs.append({**op, "choices": choices, "required": required, "expected_duration": _expected_duration(state, op),
                     "priority_score": _priority(state, c)[1], "priority_band": _priority(state, c)[0],
                     "arrival": c["arrival_at_min"], "group": c["stakeholder_group"]})
    return jobs, skipped


def _reward(job: dict, profile: str, now: int) -> int:
    age = max(0, now - job["arrival"])
    gate = job["kind"] == "gate_handoff"
    critical = job["kind"] == "reefer_check" and job["priority_band"] == "critical"
    reward = 120000 if gate else 20000
    if critical:
        reward = 250000
    reward += min(age, 240) * (700 if profile == "balanced" else 350 if profile == "recovery" else 100)
    reward += job["priority_score"] * (40 if profile == "balanced" else 10)
    return reward


def _result(state: dict, profile: str, strategy: str, operations: list[dict], skipped: list[dict], status: str,
            elapsed: float, optimal: bool, objective: float | None = None, bound: float | None = None) -> dict:
    gate_count = sum(op["kind"] == "gate_handoff" for op in operations)
    return {"solver_status": status, "optimality_proven": optimal, "profile": profile, "strategy": strategy,
            "input_clock_min": state["clock_min"], "horizon_minutes": min(60, state["horizon_minutes"] - state["clock_min"]),
            "input_state_hash": state_fingerprint(state),
            "operations": sorted(operations, key=lambda op: (op["start_min"], op["resource_ids"], op["id"])), "unscheduled": skipped,
            "objective_values": {"projected_handoffs": gate_count, "projected_service_checks": len(operations) - gate_count,
                                 "weighted_policy_objective": objective, "best_bound": bound},
            "solve_ms": round(elapsed * 1000, 2), "policy_version": "observed-interval-1", "solver_threads": 1,
            "semantics": "Projected operations from currently observed work only. This is not actual completed throughput.",
            "validation": {"valid": True, "errors": []}}


def _operation(job: dict, start: int, end: int, resources: list[str]) -> dict:
    return {"id": f"planned:{job['id']}:{start}", "task_id": job["id"], "container_id": job["container_id"],
            "resource_ids": resources, "start_min": int(start), "end_min": int(end), "kind": job["kind"], "status": "projected"}


def validate_plan(state: dict, result: dict) -> list[str]:
    """Independent integer-time occupancy and prerequisite checker (not solver code)."""
    errors = []
    if result.get("input_state_hash") and result["input_state_hash"] != state_fingerprint(state):
        errors.append("Plan input evidence or resource state is stale")
    now = state["clock_min"]
    end = now + result["horizon_minutes"]
    occupancy: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    index = {op["task_id"]: op for op in result["operations"]}
    for op in state["running"]:
        for rid in op["resource_ids"]:
            for minute in range(now, op["end_min"]):
                occupancy[rid][minute] += 1
    seen = set()
    for op in result["operations"]:
        task_id = op["task_id"]
        original = state["operations"].get(task_id)
        if task_id in seen:
            errors.append(f"Duplicate operation {task_id}")
        seen.add(task_id)
        if not original:
            errors.append(f"Unknown operation {task_id}")
            continue
        if original["status"] != "pending":
            errors.append(f"Operation {task_id} is not pending")
        c = state["containers"][original["container_id"]]
        if not c["arrived"]:
            errors.append(f"Operation {task_id} uses an unobserved arrival")
        if not now <= op["start_min"] < op["end_min"] <= end:
            errors.append(f"Operation {task_id} lies outside the planning horizon")
        if not any(rid in original["resource_options"] for rid in op["resource_ids"]):
            errors.append(f"Operation {task_id} lacks a compatible resource")
        if not set(original.get("requires_all", [])) <= set(op["resource_ids"]):
            errors.append(f"Operation {task_id} lacks a jointly required resource")
        if original["kind"] == "gate_handoff" and _eligibility(state, c, include_lane=False)["status"] != "allowed":
            errors.append(f"Operation {task_id} violates current departure prerequisites")
        for pred in original.get("predecessors", []):
            prior = state["operations"][pred]
            running = next((r for r in state["running"] if r["task_id"] == pred), None)
            if prior["status"] == "completed":
                pass
            elif pred in index:
                if index[pred]["end_min"] > op["start_min"]:
                    errors.append(f"Operation {task_id} starts before {pred} completes")
            elif running:
                if running["end_min"] > op["start_min"]:
                    errors.append(f"Operation {task_id} starts before running prerequisite completes")
            else:
                errors.append(f"Operation {task_id} has an unscheduled prerequisite")
        for rid in op["resource_ids"]:
            if rid not in state["resources"]:
                errors.append(f"Unknown resource {rid}")
                continue
            for minute in range(op["start_min"], op["end_min"]):
                occupancy[rid][minute] += 1
    for rid, minutes in occupancy.items():
        capacity = _available_capacity(state, state["resources"][rid])
        # In-flight work may be interrupted by a newly reported closure. It is
        # cancelled by the executor, and cannot make new planned work feasible.
        if any(value > capacity for value in minutes.values()):
            errors.append(f"Resource {rid} exceeds its available capacity")
    return list(dict.fromkeys(errors))


def _greedy(state: dict, profile: str, strategy: str, jobs: list[dict], skipped: list[dict]) -> dict:
    started = time.perf_counter()
    now, until = state["clock_min"], min(state["clock_min"] + 60, state["horizon_minutes"])
    occupancy: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    finished = {oid: now for oid, op in state["operations"].items() if op["status"] == "completed"}
    for op in state["running"]:
        finished[op["task_id"]] = op["end_min"]
        for rid in op["resource_ids"]:
            for t in range(now, op["end_min"]):
                occupancy[rid][t] += 1
    if strategy == "fifo":
        pending = sorted(jobs, key=lambda j: (j["arrival"], j["container_id"], j["kind"] == "gate_handoff", j["id"]))
    elif strategy == "priority":
        pending = sorted(jobs, key=lambda j: (-j["priority_score"], j["arrival"], j["kind"] == "gate_handoff", j["id"]))
    else:
        pending = sorted(jobs, key=lambda j: (-_reward(j, profile, now) / j["expected_duration"], j["arrival"], j["id"]))
    operations = []
    while pending:
        progressed = False
        for job in list(pending):
            if any(p not in finished for p in job.get("predecessors", [])):
                continue
            earliest = max([now] + [finished[p] for p in job.get("predecessors", [])])
            duration = job["expected_duration"]
            possible = []
            for choice in job["choices"]:
                resources = list(dict.fromkeys([choice] + job["required"]))
                for start in range(earliest, until - duration + 1):
                    if all(all(occupancy[r][t] < _available_capacity(state, state["resources"][r]) for t in range(start, start + duration)) for r in resources):
                        possible.append((start, choice, resources))
                        break
            if possible:
                start, _, resources = min(possible)
                operation = _operation(job, start, start + duration, resources)
                operations.append(operation)
                finished[job["id"]] = start + duration
                for r in resources:
                    for t in range(start, start + duration):
                        occupancy[r][t] += 1
            else:
                skipped.append({"task_id": job["id"], "container_id": job["container_id"], "reasons": ["No capacity in the current planning window"]})
            pending.remove(job)
            progressed = True
        if not progressed:
            for job in pending:
                skipped.append({"task_id": job["id"], "container_id": job["container_id"], "reasons": ["Prerequisite is blocked or outside the planning window"]})
            break
    return _result(state, profile, strategy, operations, skipped, "GREEDY_FEASIBLE", time.perf_counter()-started, False)


def make_plan(state: dict, profile: str = "throughput", strategy: str = "optimized") -> dict:
    if profile not in PROFILES or strategy not in STRATEGIES:
        raise ValueError("Unknown policy profile or scheduling strategy")
    if state["mode"] != "SIMULATION":
        return _result(state, profile, strategy, [], [{"reasons": ["Replay mode projects source evidence; physical scheduling is disabled"]}], "REPLAY_ONLY", 0, False)
    jobs, skipped = candidates(state)
    if not jobs or state["clock_min"] >= state["horizon_minutes"]:
        return _result(state, profile, strategy, [], skipped, "NO_ELIGIBLE_WORK", 0, True)
    if strategy != "optimized":
        result = _greedy(state, profile, strategy, jobs, skipped)
        errors = validate_plan(state, result)
        result["validation"] = {"valid": not errors, "errors": errors}
        if errors:
            result["operations"] = []
            result["solver_status"] = "REJECTED_BY_VALIDATOR"
        return result
    try:
        from ortools.sat.python import cp_model
    except ImportError as exc:
        raise RuntimeError("OR-Tools is required for the optimized scheduler") from exc
    started = time.perf_counter()
    now, until = state["clock_min"], min(state["clock_min"] + 60, state["horizon_minutes"])
    model = cp_model.CpModel()
    intervals: dict[str, list[Any]] = defaultdict(list)
    variables = {}
    for op in state["running"]:
        if op["end_min"] > now:
            for rid in op["resource_ids"]:
                intervals[rid].append(model.NewIntervalVar(now, op["end_min"]-now, op["end_min"], f"running:{op['task_id']}:{rid}"))
    objective = []
    for job in jobs:
        oid = job["id"]
        duration = job["expected_duration"]
        selected = model.NewBoolVar(f"selected:{oid}")
        start = model.NewIntVar(now, until, f"start:{oid}")
        end = model.NewIntVar(now, until, f"end:{oid}")
        model.Add(end == start + duration).OnlyEnforceIf(selected)
        model.Add(start == now).OnlyEnforceIf(selected.Not())
        model.Add(end == now).OnlyEnforceIf(selected.Not())
        alternatives = {}
        for rid in job["choices"]:
            chosen = model.NewBoolVar(f"uses:{oid}:{rid}")
            alternatives[rid] = chosen
            intervals[rid].append(model.NewOptionalIntervalVar(start, duration, end, chosen, f"interval:{oid}:{rid}"))
        model.Add(sum(alternatives.values()) == selected)
        for rid in job["required"]:
            intervals[rid].append(model.NewOptionalIntervalVar(start, duration, end, selected, f"joint:{oid}:{rid}"))
        reward = _reward(job, profile, now)
        objective.append(selected * reward - (end-now) * (8 if profile == "balanced" else 1))
        variables[oid] = (selected, start, end, alternatives, job)
    for oid, (selected, start, end, alternatives, job) in variables.items():
        for pred in job.get("predecessors", []):
            previous = state["operations"][pred]
            if previous["status"] == "completed":
                continue
            running = next((op for op in state["running"] if op["task_id"] == pred), None)
            if running:
                model.Add(start >= running["end_min"]).OnlyEnforceIf(selected)
            elif pred in variables:
                model.Add(selected <= variables[pred][0])
                model.Add(start >= variables[pred][2]).OnlyEnforceIf(selected)
            else:
                model.Add(selected == 0)
    for rid, resource_intervals in intervals.items():
        cap = _available_capacity(state, state["resources"][rid])
        model.AddCumulative(resource_intervals, [1] * len(resource_intervals), cap)
    model.Maximize(sum(objective))
    # A feasible, work-conserving incumbent is available before search.  Hints
    # prevent a short solve budget from inventing avoidable idle periods in
    # large symmetric equal-service controls.
    incumbent = _greedy(state, profile, "optimized", jobs, [])
    hinted = {operation["task_id"]: operation for operation in incumbent["operations"]}
    for oid, (selected, start, end, alternatives, job) in variables.items():
        operation = hinted.get(oid)
        model.AddHint(selected, int(operation is not None))
        model.AddHint(start, operation["start_min"] if operation else now)
        model.AddHint(end, operation["end_min"] if operation else now)
        for rid, chosen in alternatives.items():
            model.AddHint(chosen, int(operation is not None and rid in operation["resource_ids"]))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = .08
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = state["seed"] % 2147483647
    status = solver.Solve(model)
    if status not in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        result = _greedy(state, profile, "optimized", jobs, skipped)
        result["solver_status"] = f"{solver.StatusName(status)}_GREEDY_FALLBACK"
        result["fallback_reason"] = "CP-SAT returned no feasible incumbent within the deterministic single-worker budget"
        result["optimality_proven"] = False
        result["solve_ms"] = round((time.perf_counter()-started)*1000,2)
    else:
        operations = []
        for oid, (selected, start, end, alternatives, job) in variables.items():
            if solver.Value(selected):
                resources = [rid for rid, chosen in alternatives.items() if solver.Value(chosen)] + job["required"]
                operations.append(_operation(job, solver.Value(start), solver.Value(end), resources))
            else:
                skipped.append({"task_id": oid, "container_id": job["container_id"], "reasons": ["Not selected within current resource window and policy objective"]})
        result = _result(state, profile, strategy, operations, skipped, solver.StatusName(status), time.perf_counter()-started,
                         status == cp_model.OPTIMAL, solver.ObjectiveValue(), solver.BestObjectiveBound())
    errors = validate_plan(state, result)
    result["validation"] = {"valid": not errors, "errors": errors}
    if errors:
        result["operations"] = []
        result["solver_status"] = "REJECTED_BY_VALIDATOR"
        result["optimality_proven"] = False
    return result
