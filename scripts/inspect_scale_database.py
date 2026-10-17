"""Read-only persisted scale-run totals and PostgreSQL EXPLAIN ANALYZE.

The connection URL comes from the named environment variable and is never
printed or written. Plans describe the current local database/cache only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import time

from sqlalchemy import create_engine, text


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--output",default="evaluation/scale-2026-10-17/database-inspection.json")
    parser.add_argument("--database-url-env",default="WORKBENCH_DATABASE_URL")
    args=parser.parse_args()
    if args.database_url_env not in os.environ:parser.error("Set the requested local PostgreSQL URL environment variable")
    engine=create_engine(os.environ[args.database_url_env])
    if engine.dialect.name!="postgresql":parser.error("This inspection requires actual PostgreSQL")
    started=time.perf_counter()
    with engine.connect() as connection,connection.begin():
        connection.execute(text("SET TRANSACTION READ ONLY"))
        run=connection.execute(text("SELECT id,workspace_id,profile,seed,status,clock_min,horizon_minutes,total_records,revision,next_sequence,resource_state FROM wb_scale_runs WHERE id=:run_id"),{"run_id":args.run_id}).mappings().one()
        counts=connection.execute(text("SELECT status,COUNT(*) AS records,SUM(teu) AS teu FROM wb_scale_movements WHERE run_id=:run_id GROUP BY status ORDER BY status"),{"run_id":args.run_id}).mappings().all()
        aggregate=connection.execute(text("SELECT COUNT(*) AS records,SUM(teu) AS teu,COUNT(*) FILTER (WHERE completed_min > :clock) AS future_completions,COUNT(*) FILTER (WHERE status='completed' AND completed_min IS NULL) AS missing_completion_times,SUM(pg_column_size(m)) AS composite_row_bytes FROM wb_scale_movements AS m WHERE run_id=:run_id"),{"run_id":args.run_id,"clock":run["clock_min"]}).mappings().one()
        audit=connection.execute(text("SELECT COUNT(*) AS batch_events,MIN(sequence) AS first_sequence,MAX(sequence) AS last_sequence,MAX(at_min) AS latest_clock FROM wb_scale_events WHERE run_id=:run_id"),{"run_id":args.run_id}).mappings().one()
        cohort_runs=connection.scalar(text("SELECT COUNT(DISTINCT run_id) FROM wb_scale_movements"))
        relation=connection.execute(text("SELECT pg_total_relation_size('wb_scale_movements') AS movements_all_runs_total_bytes,pg_indexes_size('wb_scale_movements') AS movements_all_runs_index_bytes,pg_total_relation_size('wb_scale_events') AS events_all_runs_total_bytes")).mappings().one()
        queries={
            "first_page":"SELECT * FROM wb_scale_movements WHERE run_id=:run_id ORDER BY arrival_min,id LIMIT 100",
            "middle_page":"SELECT * FROM wb_scale_movements WHERE run_id=:run_id ORDER BY arrival_min,id OFFSET :offset LIMIT 100",
            "terminal_page":"SELECT * FROM wb_scale_movements WHERE run_id=:run_id AND terminal_id='terminal-fenix' ORDER BY arrival_min,id LIMIT 100",
            "bounded_candidates":"SELECT * FROM wb_scale_movements WHERE run_id=:run_id AND terminal_id='terminal-fenix' AND status!='completed' AND arrival_min<=:clock ORDER BY CASE WHEN status='in_service' THEN 0 ELSE 1 END,blocked,arrival_min,id LIMIT 2000",
        }
        plans={}
        for name,query in queries.items():
            plan=connection.scalar(text("EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "+query),{"run_id":args.run_id,"offset":run["total_records"]//2,"clock":run["clock_min"]})
            plans[name]={"sql":query,"parameters":{"run_id":args.run_id,"offset":run["total_records"]//2,"clock":run["clock_min"]},"plan":plan}
        version=connection.scalar(text("SELECT version()"))
    engine.dispose()
    assert aggregate["records"]==run["total_records"]
    assert aggregate["future_completions"]==0 and aggregate["missing_completion_times"]==0
    assert audit["last_sequence"]-audit["first_sequence"]+1==audit["batch_events"]
    report={"at_utc":datetime.now(timezone.utc).isoformat(),"command":sys.argv,"postgresql_version":version,"client_platform":platform.platform(),
            "run":dict(run),"counts_by_status":[dict(row) for row in counts],"aggregate":dict(aggregate),"audit":dict(audit),
            "all_runs_relation_sizes":{**dict(relation),"cohort_runs":cohort_runs,"scope":"Entire current public relations across all retained runs, including indexes/TOAST where applicable; not exclusive per-run disk or memory."},
            "queries":plans,"wall_seconds":time.perf_counter()-started,
            "verified":["Fresh SQL connection reads committed run/rows/resource state after HTTP requests completed.","Relational row count matches persisted run total.","No completed timestamp exceeds persisted clock; no completed row lacks its time.","Audit batch-event sequence is contiguous."],
            "limits":["This is a fresh-connection persistence inspection, not an app/PostgreSQL crash-recovery test.","EXPLAIN ANALYZE measures a warm local database; results are not a production SLA.","Composite row-size sum is not relation disk footprint; relation sizes include all retained runs."]}
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print(f"Verified {aggregate['records']:,} committed rows / {aggregate['teu']:,} modeled TEU, clock={run['clock_min']}, {audit['batch_events']} persisted audit batches")
    print(f"Saved {output}")


if __name__=="__main__":main()
