# Workbench verification record

Date: 2026-10-17 · Branch: `codex/fullstack-simulation-demo`.

This record describes an isolated local rehearsal, not validation of a real terminal deployment. The legacy `main.py`, Ryan's original cohort and the team's hosted Render service remain separate.

## Environment

- macOS host, Python 3.12, Node 24 and pnpm 11.25.0.
- PostgreSQL 17 in a Docker named volume, bound to `127.0.0.1:54329`.
- New FastAPI entry point `workbench_main:app`, web and API on `127.0.0.1:8088`.
- SQLAlchemy / Alembic migrations `wb_0001` and `wb_0002`; application tables use the `wb_` prefix.
- Synthetic fixtures: 100 containers per cohort and six scenarios, with separate provider-shaped and operational evidence.

## Automated checks

The suite covers existing API behavior and the new engine, persistence and source retrieval. Final totals and Docker checks are recorded below after the last build.

- Resource and permission guards, independent issues, late observations, duplicate envelopes, delayed-feed recovery, per-field ordering and timestamps.
- CP-SAT interval validation, common random samples, scoped road disruption, backwards-compatible persisted-state upgrades and replay isolation.
- Workspace token isolation, stale revisions, exact retry receipts, concurrent writes, durable jobs, expired leases, candidate-plan validation and server playback.
- Signed webhook acceptance, duplicates and conflicting event IDs.
- Internal coordination requests: validation, persistence, isolation, idempotency, status history and unchanged provider/departure facts.
- Source retrieval: inspectable passages, explicit no-LLM behavior and empty results for unrelated queries.

## Real PostgreSQL HTTP checks

`scripts/check_workbench.py` creates its own synthetic workspace and checks the running service. It does not print or store its workspace token.

Verified on the host-backed PostgreSQL application: readiness, wrong-token rejection, state persistence, mutation retry before revision validation, stale-write rejection, authenticated SSE push, server playback and pause, successful durable CP-SAT jobs and source retrieval. Request lifecycle checks are also included in the script.

The application was restarted during development and existing workspace progress survived. Alembic adopted the initial local development schema without dropping its rows; the request migration adds its own table.

## Browser checks

Tested in Chrome at desktop width and in the narrow in-app browser:

- Four views open and load backend data.
- Full worklist search, gate and cargo scope, sorting, column selection and lifecycle categories.
- Select two containers, create an internal reefer coordination request, move it to in progress and reload the page. The request and status remain saved.
- Inspect the multi-issue container, submit a normal reefer reading, see its open-issue count drop while customs, weight and movement restrictions remain.
- Inject an East closure; two West lanes remain available. Advance the world and receive updated actual results.
- Run a one-seed paired experiment from the UI and render real results.
- Search `RAG` in the source library and receive an attributable local passage, with `No LLM` displayed.
- Create a second scenario, resume the first through Recent rehearsals and recover the original in-progress request and minute-15 world. Browser-only access records remain isolated from URLs and repository files.
- Execute a 90-minute incident experiment from the final Docker-served UI: 31 / 30 / 31 completed handoffs with 66 / 67 / 66 unfinished backlog and zero constraint violations (FIFO / priority / optimized).

## Calibration and outcome interpretation

The equal-service control completes exactly **96** valid handoffs for FIFO, priority and optimized policies in 240 minutes: two lanes, five-minute service and 100 initial ready containers. It demonstrates the modeled capacity bound, not an optimization gain.

Seed 17 at a 90-minute horizon produced 40 / 39 / 43 handoffs for normal operations and 31 / 30 / 31 for the incident scenario (FIFO / priority / optimized). In the incident run, optimized waiting was worse than FIFO. These results demonstrate that gains are not guaranteed. Four-hour cohort runs can converge to the same final count as feasible work runs out. Treat bounded solver timing as a source of possible plan variation across machines.

## Deliberate limits

- Terminal49 live access and account field coverage have not been activated or validated. The adapter and signed inbox are implemented; live anonymous workspace projection remains disabled.
- The local UI uses workspace capability tokens, not production user accounts or a complete organizational RBAC system.
- The worker is a local application thread with a durable SQL queue. This is not a tested multi-replica high-availability system. Playback pauses after a process restart.
- Source retrieval is local BM25 over curated passages and source metadata. No LLM generation, embeddings or external model call is claimed.
- Scheduling has transparent weighted objectives, not a lexicographic guarantee or hard maximum-wait service guarantee. Pending plans can change; in-progress work remains constrained.
- Waiting means/P90 describe completed samples. Unfinished backlog and censored wait lower bounds are separate. No exact external-versus-internal truck queue split is modeled.
- A recovery-time KPI is `not_identifiable` without a configured normal-service target.
- Interrupted physical work restarts in the synthetic model. Weight tolerances and temperature thresholds are explicit demo policies.
- Internal coordination requests neither contact outside parties nor modify operational permissions. No real equipment, bookings, payments or customs systems are controlled.

## Final execution results

- `python -m pytest -q`: **163 passed** in 15.72 seconds; one existing Starlette/httpx test-client deprecation warning.
- `pnpm test:session`: **4 passed**. Retaining access across creation/resume, migrating older sessions and isolating invalid entries are covered.
- TypeScript and Vite production build: **passed**, both locally and in the multi-stage Docker build.
- Reference-pack schema and semantic validator: **passed** for all six scenarios and three 100-record cohorts.
- `docker compose -f compose.workbench.yml up -d --build app`: **passed**. Both app and PostgreSQL containers reported healthy.
- `python scripts/check_workbench.py` against the Docker application: **passed**. Actual PostgreSQL, request lifecycle, dynamic provider LFD/fee updates preserving holds, authenticated SSE, playback, revision/idempotency behavior, durable CP-SAT jobs and source retrieval were exercised.
- Browser navigation, forms and persisted-state checks described above: **passed**. Screenshots are in `docs/screenshots/`.

The local demo is running in Docker at `http://127.0.0.1:8088`. No new cloud account, paid service, live API key or database login was required. Hosted team deployment was not changed. GitHub CI execution is separate from these observed local checks.
