"""Closed-loop execution and paired experiments over common random samples."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
from collections import defaultdict

from .engine import (_apply_events, _available_capacity, _eligibility, _event,
                     _observe_arrivals, create_state, percentile, plan, snapshot)


def _store_plan(state: dict, strategy: str, profile: str) -> None:
    result = plan(state, profile, strategy)
    state["plan"] = result
    counts = state["metrics"].setdefault("solver_status_counts", {})
    counts[result["solver_status"]] = counts.get(result["solver_status"], 0) + 1
    state["metrics"]["total_solver_ms"] = round(state["metrics"].get("total_solver_ms", 0) + result["solve_ms"], 2)
    if "FALLBACK" in result["solver_status"]:
        state["metrics"]["solver_fallbacks"] = state["metrics"].get("solver_fallbacks", 0) + 1
    if not result.get("validation", {}).get("valid", True):
        state["metrics"]["plan_validation_rejections"] = state["metrics"].get("plan_validation_rejections", 0) + 1


def _resources_free(state: dict, resource_ids: list[str], physical: bool = True) -> bool:
    used = defaultdict(int)
    for active in state["running"]:
        for rid in active["resource_ids"]:
            used[rid] += 1
    return all(used[rid] < _available_capacity(state, state["resources"][rid], physical=physical) for rid in resource_ids)


def _cancel_unavailable(state: dict) -> bool:
    changed = False
    for active in list(state["running"]):
        unavailable = any(_available_capacity(state, state["resources"][rid], physical=True) == 0 for rid in active["resource_ids"])
        c = state["containers"][active["container_id"]]
        if active["kind"] == "gate_handoff" and _eligibility(state, c, include_lane=False, physical=True)["status"] != "allowed":
            unavailable = True
        if unavailable:
            state["running"].remove(active)
            state["operations"][active["task_id"]]["status"] = "pending"
            active["status"] = "interrupted"
            active["interrupted_at_min"] = state["clock_min"]
            state["execution_log"].append(active)
            if active["kind"] == "gate_handoff":
                c["gate_started_min"] = None
            state["metrics"]["new_information_rejections"] += 1
            _event(state, "operation.interrupted", "Operation paused by a changed physical condition", f"{active['kind'].replace('_', ' ')} interrupted; no handoff counted. Resource or permission must become valid before restart.", c["container_id"], "Synthetic world executor")
            changed = True
    return changed


def _finish(state: dict) -> bool:
    changed = False
    for active in list(state["running"]):
        if active["end_min"] > state["clock_min"]:
            continue
        state["running"].remove(active)
        original = state["operations"][active["task_id"]]
        original["status"] = "completed"
        active["status"] = "completed"
        state["execution_log"].append(active)
        c = state["containers"][active["container_id"]]
        if active["kind"] == "gate_handoff":
            # Final validation protects throughput accounting from double count.
            eligibility = _eligibility(state, c, include_lane=False, physical=True)
            if eligibility["status"] != "allowed" or c["completed_at_min"] is not None:
                state["metrics"]["invalid_action_attempts"] += 1
                original["status"] = "pending"
                active["status"] = "rejected"
                _event(state, "operation.rejected", "Handoff rejected by execution guard", "; ".join(eligibility["reasons"]), c["container_id"])
                continue
            c["completed_at_min"] = state["clock_min"]
            state["completed"].append({"container_id": c["container_id"], "at_min": state["clock_min"], "start_min": active["start_min"], "arrival_min": c["arrival_at_min"], "resource_ids": active["resource_ids"]})
            _event(state, "handoff.completed", "Valid simulated handoff completed", "One final handoff counted. Verification and coordination tasks do not count as throughput.", c["container_id"])
        else:
            c["task_status"][active["task_id"]] = "waiting_external"
            _event(state, "operation.completed", f"{active['kind'].replace('_', ' ').title()} service completed", "Service time is complete; issue resolution still requires a compatible verified observation. Other holds remain unchanged.", c["container_id"])
        changed = True
    return changed


def _dispatch(state: dict) -> bool:
    current = state.get("plan")
    if not current or not current.get("validation", {}).get("valid", True):
        return False
    started = False
    for proposed in current["operations"]:
        # Pull an already selected, fully ready operation forward when a real
        # resource becomes idle.  The same work-conserving dispatch rule applies
        # to all policies; no future arrivals or observations are introduced.
        original = state["operations"][proposed["task_id"]]
        if original["status"] != "pending":
            continue
        if any(state["operations"][pid]["status"] != "completed" for pid in original.get("predecessors", [])):
            continue
        c = state["containers"][original["container_id"]]
        if not _resources_free(state, proposed["resource_ids"], physical=True):
            continue
        if original["kind"] == "gate_handoff" and _eligibility(state, c, include_lane=False, physical=True)["status"] != "allowed":
            continue
        end = state["clock_min"] + original["duration"]
        # It is legitimate to start a job which finishes after the observation
        # horizon; it remains unfinished and cannot count as completed output.
        active = {**proposed, "start_min": state["clock_min"], "end_min": end, "status": "running"}
        state["running"].append(active)
        original["status"] = "running"
        if original["kind"] == "gate_handoff":
            c["gate_started_min"] = state["clock_min"]
        _event(state, "operation.started", f"{original['kind'].replace('_', ' ').title()} started", f"Resources: {', '.join(active['resource_ids'])}. Actual sampled service duration is revealed only when work begins.", c["container_id"])
        started = True
    return started


def advance(state: dict, minutes: int, strategy: str = "optimized", profile: str = "throughput") -> None:
    if state["mode"] != "SIMULATION":
        raise ValueError("Physical execution requires SIMULATION mode")
    target = min(state["clock_min"] + minutes, state["horizon_minutes"])
    if target <= state["clock_min"]:
        return
    from .spatial_simulation import advance_spatial_operations
    advance_spatial_operations(state)
    if not state.get("plan") or state["plan"]["strategy"] != strategy or state["plan"]["profile"] != profile:
        _store_plan(state, strategy, profile)
    _dispatch(state)
    while state["clock_min"] < target:
        state["clock_min"] += 1
        # Physical enforcement occurs before a delayed incident notice reaches
        # the policy.  It prevents unsafe execution without granting foresight.
        changed = _cancel_unavailable(state)
        changed = _finish(state) or changed
        changed = _apply_events(state) or changed
        changed = _observe_arrivals(state) or changed
        # Separate synthetic vessel work uses dedicated resources and the same
        # clock. Its progress never manufactures tracked-cohort handoffs or
        # triggers an unrelated gate-policy replan.
        advance_spatial_operations(state)
        changed = _cancel_unavailable(state) or changed
        if changed or state["clock_min"] % state["config"]["planning"]["replan_minutes"] == 0:
            _store_plan(state, strategy, profile)
        if state["clock_min"] < state["horizon_minutes"]:
            _dispatch(state)
        if state["clock_min"] % 5 == 0 or state["clock_min"] == target:
            curve = {"minute": state["clock_min"], "completed_handoffs": len(state["completed"]),
                     "backlog": sum(c["arrived"] and c["completed_at_min"] is None for c in state["containers"].values())}
            if state["curves"] and state["curves"][-1]["minute"] == curve["minute"]:
                state["curves"][-1] = curve
            else:
                state["curves"].append(curve)
    _event(state, "clock.advanced", f"Virtual clock advanced to minute {state['clock_min']}", f"Observed arrivals, received evidence, resource changes and actual completions processed using {strategy} scheduling.")


def run_experiment(scenario_id: str, seeds: list[int], horizon_minutes: int = 240) -> dict:
    if not seeds or len(seeds) > 30 or any(type(s) is not int for s in seeds):
        raise ValueError("Experiments require 1–30 integer seeds")
    if len(set(seeds)) != len(seeds) or any(s < 0 or s > 2147483647 for s in seeds):
        raise ValueError("Use distinct seeds between 0 and 2147483647 for independent paired worlds")
    if type(horizon_minutes) is not int or not 1 <= horizon_minutes <= 240:
        raise ValueError("Experiment horizon must be 1–240 minutes")
    strategies = []
    all_runs = {}
    for strategy in ("fifo", "priority", "optimized"):
        runs = []
        for seed in seeds:
            state = create_state(scenario_id, seed)
            advance(state, horizon_minutes, strategy)
            snap = snapshot(state)
            waits = [row["start_min"] - row["arrival_min"] for row in state["completed"]]
            runs.append({"seed": seed, "completed_handoffs": len(state["completed"]),
                         "avg_wait_minutes": snap["overview"]["avg_wait_minutes"], "p90_wait_minutes": snap["overview"]["p90_wait_minutes"],
                         "unfinished_backlog": snap["overview"]["backlog"],
                         "unfinished_wait_lower_bound_mean": snap["metrics"]["unfinished_wait_lower_bound_mean"],
                         "constraint_violations": state["metrics"]["constraint_violations"],
                         "invalid_action_attempts": state["metrics"]["invalid_action_attempts"],
                         "new_information_rejections": state["metrics"]["new_information_rejections"],
                         "solver_status": state["plan"]["solver_status"], "curves": state["curves"],
                         "solver_status_counts": state["metrics"].get("solver_status_counts", {}),
                         "solver_fallbacks": state["metrics"].get("solver_fallbacks", 0),
                         "plan_validation_rejections": state["metrics"].get("plan_validation_rejections", 0),
                         "solver_configuration": {"workers": 1, "max_seconds_per_plan": .08},
                         "world_sample_hash": hashlib.sha256(json.dumps({oid: op["duration"] for oid, op in sorted(state["operations"].items())}, sort_keys=True).encode()).hexdigest(),
                         "observed_wait_samples": len(waits), "policy_version": "observed-interval-1",
                         "recovery": {"status": "not_identifiable", "minutes": None, "reason": "A paired normal-world recovery target is not configured; no recovery-time claim is made."}})
        all_runs[strategy] = runs
        completions = [r["completed_handoffs"] for r in runs]
        curve_minutes = sorted({c["minute"] for r in runs for c in r["curves"]})
        curves = []
        for minute in curve_minutes:
            samples = [next((c for c in r["curves"] if c["minute"] == minute), None) for r in runs]
            samples = [s for s in samples if s]
            curves.append({"minute": minute, "completed_handoffs": round(statistics.mean(s["completed_handoffs"] for s in samples),2), "backlog": round(statistics.mean(s["backlog"] for s in samples),2)})
        strategies.append({"strategy": strategy, "completed_handoffs": round(statistics.mean(completions),2),
                           "completed_handoffs_min": min(completions), "completed_handoffs_max": max(completions),
                           "throughput_across_runs_p90": percentile(completions, .9),
                           "avg_wait_minutes": round(statistics.mean(r["avg_wait_minutes"] for r in runs),2),
                           "p90_wait_minutes": round(statistics.mean(r["p90_wait_minutes"] for r in runs),2),
                           "unfinished_backlog": round(statistics.mean(r["unfinished_backlog"] for r in runs),2),
                           "constraint_violations": sum(r["constraint_violations"] for r in runs), "curves": curves, "runs": runs})
    paired = []
    for baseline in ("fifo", "priority"):
        diffs = [opt["completed_handoffs"] - base["completed_handoffs"] for opt, base in zip(all_runs["optimized"], all_runs[baseline])]
        mean = statistics.mean(diffs)
        margin = 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else None
        paired.append({"baseline": baseline, "metric": "completed_handoffs", "mean_difference": round(mean,2),
                       "min_difference": min(diffs), "max_difference": max(diffs),
                       "confidence_interval_95_normal_approx": [round(mean-margin,2),round(mean+margin,2)] if margin is not None else None,
                       "runs_improved": sum(d > 0 for d in diffs), "runs_tied": sum(d == 0 for d in diffs), "runs_worse": sum(d < 0 for d in diffs),
                       "per_seed": [{"seed": seed, "difference": d} for seed,d in zip(seeds,diffs)]})
    assumptions = [
        "Synthetic comparative experiment; no measured real-world savings or throughput improvement is claimed.",
        "All policies receive identical per-operation service samples keyed by seed and operation ID, and identical observation timing.",
        "Baselines skip blocked work and use exactly the same resource, permission and execution guards as the optimizer.",
        "CP-SAT uses one worker and a bounded wall-clock solve; fallback and non-optimal statuses are retained.",
        "Individual completed-container wait P90 differs from throughput P90 across independent runs; unfinished waits remain censored.",
    ]
    return {"scenario_id": scenario_id, "seeds": seeds, "horizon_minutes": horizon_minutes,
            "strategies": strategies, "paired_results": paired, "assumptions": assumptions,
            "negative_control_expected_handoffs": min(100, 2 * (horizon_minutes // 5)) if scenario_id == "equal_service_control" else None,
            "semantics": "Actual simulated completion counts, never projected schedule capacity."}
