# Reproducible evidence

- `workbench-2026-10-17/`: canonical paired strategy experiment, 459 worlds / 918 checkpoints. Raw JSONL, summaries, source snapshots, trace audit, paired uncertainty and independent arithmetic checks are retained.
- `scale-2026-10-17/`: canonical real-PostgreSQL seven-day workload measurement, 119,014 movement rows. Raw HTTP samples, SQL inspection, source snapshots and post-measurement patch provenance are retained.
- Folders explicitly marked `preflight` are development diagnostics, not final performance claims.

Both studies use synthetic operating assumptions. Official Port of Los Angeles TEU totals calibrate volume only. Neither study benchmarks a commercial product or proves real-terminal capacity, safety or production latency. Read the corresponding reports in `docs/` before quoting numbers.
