# Measured PostgreSQL port-volume rehearsal

Canonical measurement: `results.json`, seed17, seven-day profile,119,014 synthetic movements /196,371 modeled TEU. The durable worker seeded real PostgreSQL, then84 HTTP scheduling windows advanced10,080min. All source hashes stayed unchanged during the measurement.

- `results.json`: generator metrics, raw HTTP samples, job progress, each120min window, final relational status counts and limits.
- `database-inspection.json`: fresh read-only SQL connection verifies committed totals, completion times and contiguous audit batches; exact EXPLAIN ANALYZE plans included.
- `deployment-observations.json`: measured-build container/host source match at the original observation, one post-run Docker stats sample, and the separately recorded post-measurement read-isolation patch. Neither final-source equality nor peak memory is claimed.
- `source-snapshot/`, `frozen-source-manifest.json`: exact measured model/API/scripts/tests for rerunning or review.
- `post-measurement-read-isolation/`: later API/db source and the small scale GET-read diff. The physical model and migration stayed unchanged; the API source hash changed. Reported timings belong to the frozen build before this patch, and were not remeasured for the final patched GETs.
- [Chinese interpretation](../../docs/scale-evaluation.zh-CN.md).

This is one local synthetic workload, not actual port throughput or a head-to-head comparison with commercial systems. The100-container CP-SAT paired-seed experiment is separate. Do not combine its performance gains with this cohort's count.

Run `.venv/bin/python scripts/benchmark_scale.py --url http://127.0.0.1:8088 --profile la_seven_day --seed 17`; local PostgreSQL is required. It creates an independent workspace and does not write its token to artifacts. Reuse the result's run ID with `scripts/inspect_scale_database.py` and your local `WORKBENCH_DATABASE_URL` environment variable. No URL credential is written to the inspection output.
