"""Reproduce bounded generation and optional actual PostgreSQL HTTP load rehearsal.

Creates a separate synthetic workspace. Its bearer token remains in memory and
is never printed or stored. These are local descriptive timings, not a port
capacity validation, SLA, or comparison to a commercial product.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time
import tracemalloc
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gate_triage.workbench.scale_simulation import (TERMINAL_IDS, get_profile, initial_resource_state,
    iter_movement_batches, profile_catalog, schedule_window)


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict:
    files = ["gate_triage/workbench/scale_simulation.py", "gate_triage/workbench/scale.py", "gate_triage/workbench/migrations/versions/wb_0003_port_scale.py", "scripts/benchmark_scale.py", "tests/test_scale_simulation.py"]
    return {name: digest_file(ROOT / name) for name in files if (ROOT / name).exists()}


def distribution(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    def percentile(fraction):
        point = (len(ordered)-1)*fraction
        low = math.floor(point);high = math.ceil(point)
        return ordered[low] + (ordered[high]-ordered[low])*(point-low)
    return {"n": len(values), "mean_ms": statistics.mean(values), "p50_ms": percentile(.5), "p95_ms": percentile(.95), "min_ms": ordered[0], "max_ms": ordered[-1], "samples_ms": values}


def generator_benchmark(seed: int) -> dict:
    results = []
    for config in profile_catalog():
        counts = Counter();terminals = Counter();categories = Counter();daily = Counter();sizes = Counter()
        count = teu = maximum_batch = 0;stream_hash = hashlib.sha256();sample_rows = []
        tracemalloc.start();started = time.perf_counter()
        for batch in iter_movement_batches(config["id"], seed, batch_size=1000):
            maximum_batch = max(maximum_batch, len(batch))
            for row in batch:
                count += 1;teu += row["teu"]
                terminals[row["terminal_id"]] += 1;categories[row["category"]] += 1
                daily[row["payload"]["day_index"]] += row["teu"];sizes[row["teu"]] += 1
                counts["synthetic_prerequisite_blocked"] += int(row["blocked"])
                stream_hash.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()+b"\n")
                if config["id"] == "la_seven_day" and row["arrival_min"] <= 120:
                    sample_rows.append(row)
        elapsed = time.perf_counter()-started
        _, peak = tracemalloc.get_traced_memory();tracemalloc.stop()
        assert count == config["record_count"] and teu == config["generated_teu_total"]
        assert all(value == config["daily_teu_target"] for value in daily.values())
        assert maximum_batch <= 1000 and set(terminals) == set(TERMINAL_IDS)
        result = {"profile": config["id"], "seed": seed, "records": count, "teu": teu, "wall_seconds": elapsed,
                  "records_per_second": count/elapsed, "python_tracemalloc_peak_bytes": peak,
                  "maximum_batch_rows": maximum_batch, "terminal_records": dict(terminals),
                  "category_records": dict(categories), "daily_teu": dict(daily), "equipment_teu_units": dict(sizes),
                  "prerequisite_blocked_records": counts["synthetic_prerequisite_blocked"], "ordered_stream_sha256": stream_hash.hexdigest()}
        if sample_rows:
            samples=[];reference=None
            for _ in range(20):
                before=time.perf_counter()
                computed=schedule_window(sample_rows, 0, 120, initial_resource_state())
                samples.append((time.perf_counter()-before)*1000)
                trace=json.dumps(computed,sort_keys=True,separators=(",", ":"))
                if reference is None:reference=trace
                else:assert reference==trace, "Deterministic bounded model changed without changed inputs"
            result["bounded_window"]={"input_rows":len(sample_rows), "from_min":0, "to_min":120,
                                      "metrics":computed["metrics"], "latency":distribution(samples),
                                      "trace_sha256":hashlib.sha256(reference.encode()).hexdigest(),
                                      "resource_state_bytes":len(json.dumps(computed["resource_state"]).encode())}
        results.append(result)
        print(f"Generated {config['id']}: {count:,} records / {teu:,} synthetic TEU in {elapsed:.3f}s",flush=True)
    return {"profiles":results,"memory_measurement":"tracemalloc peak covers this Python benchmark process; not the HTTP server, PostgreSQL, OS cache or production peak"}


def observed_rss(pid: int | None) -> int | None:
    if pid is None:return None
    try:return int(subprocess.check_output(["ps","-o","rss=","-p",str(pid)],text=True).strip())*1024
    except (ValueError,subprocess.CalledProcessError):return None


def api_benchmark(args, progress: dict) -> dict:
    import httpx
    config=get_profile(args.profile);requests=[];polls=[];paging=[];advances=[]
    progress.update({"status":"running","requests":requests,"job_polls":polls,"paging_samples":paging,"advance_samples":advances,
                     "profile":args.profile,"seed":args.seed,"expected_records":config["record_count"],"expected_teu":config["generated_teu_total"]})
    rss_before=observed_rss(args.server_pid)
    with httpx.Client(base_url=args.url.rstrip('/')+"/api/v1",timeout=args.request_timeout) as client:
        def request(method,path,*,body=None,headers=None,label=None):
            started=time.perf_counter()
            response=client.request(method,path,json=body,headers=headers)
            elapsed=(time.perf_counter()-started)*1000
            item={"method":method,"path":path,"label":label,"status":response.status_code,"latency_ms":elapsed,"response_bytes":len(response.content)}
            requests.append(item)
            if response.status_code>=400:
                try:item["error"]=response.json().get("error",{})
                except ValueError:item["error"]={"message":"Non-JSON HTTP failure"}
            response.raise_for_status()
            return response.json(),item
        ready,_=request("GET","/health/ready",label="readiness")
        assert ready["data"]["database"]=="postgresql", "The HTTP benchmark requires actual PostgreSQL"
        created,_=request("POST","/workspaces",body={"name":"Reproducible seven-terminal scale benchmark","mode":"SIMULATION","scenario_id":"normal_operations","seed":args.seed},headers={"Idempotency-Key":str(uuid.uuid4())},label="workspace_create")
        workspace=created["data"];path="/workspaces/"+workspace["id"]
        progress["workspace_id"]=workspace["id"]
        auth={"X-Workspace-Token":workspace["workspace_token"]};revision=created["meta"]["revision"]
        def write(suffix,body,label):
            nonlocal revision
            result,sample=request("POST",path+suffix,body=body,headers={**auth,"If-Match":str(revision),"Idempotency-Key":str(uuid.uuid4())},label=label)
            revision=result["meta"]["revision"]
            return result,sample
        queued,_=write("/scale",{"profile":args.profile,"seed":args.seed},"scale_enqueue")
        job_id=queued["data"]["job_id"];run_id=queued["data"]["run_id"]
        progress.update({"run_id":run_id,"job_id":job_id})
        seed_started=time.perf_counter();deadline=seed_started+args.job_timeout
        while True:
            result,sample=request("GET",path+"/jobs/"+job_id,headers=auth,label="job_poll")
            job=result["data"];polls.append({"elapsed_seconds":time.perf_counter()-seed_started,"status":job["status"],"progress":job["progress"]})
            if job["status"] in {"succeeded","failed"}:break
            if time.perf_counter()>deadline:raise TimeoutError("Scale generation job did not finish within the explicit benchmark timeout")
            time.sleep(.25)
        assert job["status"]=="succeeded", job.get("error")
        seed_seconds=time.perf_counter()-seed_started
        progress["seed_job_observed_wall_seconds"]=seed_seconds
        seeded,_=request("GET",path+"/scale",headers=auth,label="scale_summary_seeded")
        revision=seeded["meta"]["revision"];initial=seeded["data"]
        assert initial["summary"]["total_records"]==config["record_count"]
        assert initial["summary"]["teu_total"]==config["generated_teu_total"]
        assert len(initial["summary"]["terminals"])==7
        assert initial["run"]["id"]==run_id
        cases=[("first_page","/scale/containers?limit=100"),("middle_page",f"/scale/containers?limit=100&offset={config['record_count']//2}"),("terminal_page","/scale/containers?limit=100&terminal_id=terminal-fenix")]
        for label,suffix in cases:
            for index in range(args.samples):
                result,sample=request("GET",path+suffix,headers=auth,label=label)
                page=result["data"]
                assert len(page["items"])<=100 and page["limit"]==100
                paging.append({"case":label,"sample":index,**sample})
        target_horizon=min(config["horizon_minutes"],args.advance_minutes or config["horizon_minutes"])
        elapsed_minutes=0
        while elapsed_minutes<target_horizon:
            minutes=min(120,target_horizon-elapsed_minutes)
            result,sample=write("/scale/advance",{"minutes":minutes},"advance_window")
            data=result["data"];clock=data["run"]["clock_min"]
            assert clock==elapsed_minutes+minutes
            counts=data["summary"]["counts_by_status"]
            assert sum(counts.values())==config["record_count"]
            assert data["summary"]["total_records"]==config["record_count"]
            assert data["summary"]["teu_total"]==config["generated_teu_total"]
            assert data["changed_records"]<=14000
            advances.append({"from_min":elapsed_minutes,"to_min":clock,"changed_records":data["changed_records"],"counts_by_status":counts,"completed_movements":data["summary"]["completed_movements"],**sample})
            elapsed_minutes=clock
            if len(advances)%12==0:print(f"PostgreSQL scale clock {clock}/{target_horizon}; completed synthetic movements {data['summary']['completed_movements']:,}",flush=True)
        final,_=request("GET",path+"/scale",headers=auth,label="scale_summary_final")
        audit,_=request("GET",path+"/scale/events?limit=100",headers=auth,label="scale_audit_page")
        completed,_=request("GET",path+"/scale/containers?limit=100&status=completed",headers=auth,label="completed_page")
        assert all(r["completed_min"] is not None and r["completed_min"]<=elapsed_minutes for r in completed["data"]["items"])
        assert completed["data"]["total"]==final["data"]["summary"]["completed_movements"]
        assert audit["data"]["total"]==len(advances)+1
        rss_after=observed_rss(args.server_pid)
        return {"status":"passed","base_url":args.url,"database":ready["data"]["database"],"workspace_id":workspace["id"],"run_id":run_id,"job_id":job_id,
                "profile":args.profile,"seed":args.seed,"expected_records":config["record_count"],"expected_teu":config["generated_teu_total"],
                "seed_job_observed_wall_seconds":seed_seconds,"job_polls":polls,"initial_summary":initial["summary"],"final_summary":final["data"]["summary"],
                "final_clock_min":elapsed_minutes,"audit_batch_events":audit["data"]["total"],"paging_samples":paging,
                "paging_latency_by_case":{label:distribution([row["latency_ms"] for row in paging if row["case"]==label])for label,_ in cases},
                "advance_samples":advances,"advance_latency":distribution([row["latency_ms"]for row in advances]),"requests":requests,
                "server_rss_observed_before_bytes":rss_before,"server_rss_observed_after_bytes":rss_after,
                "server_rss_measurement":"Two point-in-time process RSS readings only; not peak or PostgreSQL memory. null means unmeasured.",
                "limits":["Single local client, descriptive request timing; no concurrency, load SLA or production network claim.",
                          "Database-backed cohort rows are paged; each local scheduling window selects at most 2,000 rows per terminal.",
                          "Coarse movement service slots and terminal allocations are synthetic; this does not benchmark real port throughput.",
                          "No global CP-SAT solve of the full cohort and no commercial-product head-to-head comparison."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="evaluation/scale-2026-10-17")
    parser.add_argument("--url",help="Optional running PostgreSQL workbench URL; omit for generator-only measurement")
    parser.add_argument("--profile",default="la_seven_day",choices=[p["id"]for p in profile_catalog()])
    parser.add_argument("--seed",type=int,default=17)
    parser.add_argument("--samples",type=int,default=20)
    parser.add_argument("--advance-minutes",type=int,default=0,help="0 means run the complete selected horizon")
    parser.add_argument("--request-timeout",type=float,default=90)
    parser.add_argument("--job-timeout",type=float,default=300)
    parser.add_argument("--server-pid",type=int)
    args=parser.parse_args()
    if not 1<=args.samples<=100:parser.error("Use 1–100 request samples per paging case")
    if not 0<=args.seed<=2147483647:parser.error("Seed outside supported range")
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    manifest=source_hashes();started=time.perf_counter()
    report={"started_at_utc":datetime.now(timezone.utc).isoformat(),"command":sys.argv,"source_hashes_at_start":manifest,
            "environment":{"python":sys.version,"platform":platform.platform(),"machine":platform.machine(),"cpu_count":__import__('os').cpu_count()},
            "status":"running","failures":[],"assumptions":get_profile(args.profile)["assumptions"]}
    try:
        report["generator"]=generator_benchmark(args.seed)
        if args.url:
            report["api"]={}
            report["api"]=api_benchmark(args, report["api"])
        report["status"]="passed"
    except Exception as exc:
        report["status"]="failed";report["failures"].append({"type":type(exc).__name__,"message":str(exc)})
        raise
    finally:
        report["wall_seconds"]=time.perf_counter()-started
        report["source_hashes_at_end"]=source_hashes()
        report["source_unchanged_during_measurement"]=report["source_hashes_at_start"]==report["source_hashes_at_end"]
        # ru_maxrss is process lifetime high-water, not isolated phase memory.
        rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report["benchmark_process_lifetime_max_rss_bytes"]=rss if sys.platform=="darwin" else rss*1024
        report["finished_at_utc"]=datetime.now(timezone.utc).isoformat()
        (output/"results.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
        print(f"Saved {output/'results.json'} ({report['status']})",flush=True)
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":raise SystemExit(main())
