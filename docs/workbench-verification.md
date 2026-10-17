# Workbench verification record

Date: 2026-10-17 · Branch: `codex/fullstack-simulation-demo`.

This record describes an isolated local rehearsal, not validation of a real terminal deployment. The legacy `main.py`, Ryan's original cohort and the team's hosted Render service remain separate.

## Current acceptance — map, emergency and port-scale extension

- Complete Python suite with isolated real PostgreSQL checks enabled: **248 passed**, 54.36 seconds. One Starlette/httpx test-client deprecation warning remains.
- A final presentation correction makes scale-only incidents describe their actual phase restrictions rather than the precision model's monitoring fallback. The **19 relevant emergency/map checks** passed again after this correction; physics and database schema were unchanged.
- Frontend regression suite: **11 passed**; TypeScript and final multi-stage Docker production build passed. Runtime web bundle: `index-D0ybS25a.js`.
- PostgreSQL migrations through **wb_0003_port_scale** applied without resetting existing workspaces. Both Docker services are healthy and bound to loopback.
- Live HTTP smoke passed: scoped token access, durable retry receipts, stale revisions, unchanged permissions after request resolution, provider LFD/fee updates, authenticated SSE, server playback, validated planning jobs and attributable source retrieval.
- Final source includes the reset guard, source-update compatibility fix, independent scale-run incident boundaries, phase-specific disaster effects, current effective map urgency, and PostgreSQL repeatable-read map/scale responses. Regression tests exercise the actual read/write interleaving.
- Browser acceptance used real web controls to generate **119,014 rows / 196,371 synthetic TEU** in PostgreSQL, advance the scale clock, view all seven SQL terminal aggregates, focus APM on the map and open its filtered paged records. Auto advance issued actual serialized API windows, then paused; progress remained saved after app reconstruction and reload. The precision clock stayed separate.
- A scoped West-access incident closed the remaining two lanes in an existing East-disruption exercise. Human ownership acknowledgement left capacity closed; explicit West recovery restored only the West lanes. East restrictions and independent holds remained.
- Map zoom/pan/focus, optional hide/show, real OSM basemap attribution, synthetic area selection, separate performed-work/readiness counts, compact disaster-specific strategy, internal escalation and required recovery notes were checked in desktop and narrow browser layouts.

The saved **459-world / 918-checkpoint** strategy experiment has no failed or mismatched runs. A separate stdlib audit recomputed means, denominators, unique keys, pair matching and win/tie/loss counts from raw JSONL: **5,264 checks, zero discrepancies**. This is scoped arithmetic verification, not an overall accuracy score. Gains, ties, losses and unfinished waits are retained. See [simulation evaluation](simulation-evaluation.zh-CN.md).

The seven-day real-PostgreSQL benchmark completed all 84 advance windows. It stored 119,014 movement rows and 85 audit batches; final status totals were 114,130 completed, 4,577 blocked, 248 queued and 59 in service. These reconcile exactly. Local measured seed time was 8.877 seconds; page-query P95 ranged from 24.42 to 166.80 ms and 120-minute advance P95 was 741.66 ms. Timings refer to the frozen measured build before the final read-consistency patch, not a production SLA or a commercial comparison. Source snapshots, subsequent patch provenance, raw samples and fresh-connection SQL checks are preserved in [scale evaluation](scale-evaluation.zh-CN.md).

Terminal49 remains unconnected and `llm_used=false`, as explicitly requested for this demo. Large-scale flow is an assumed phase/slot model, not global optimal crane planning or real concurrent terminal inventory. All disaster strategies are generic exercise policies, with cited background and human authority boundaries.

## Environment

- macOS host, Python 3.12, Node 24 and pnpm 11.25.0.
- PostgreSQL 17 in a Docker named volume, bound to `127.0.0.1:54329`.
- New FastAPI entry point `workbench_main:app`, web and API on `127.0.0.1:8088`.
- SQLAlchemy / Alembic migrations `wb_0001`, `wb_0002`, `wb_0003`; application tables use the `wb_` prefix.
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

## Initial delivery results (superseded by current acceptance above)

- `python -m pytest -q`: **163 passed** in 15.72 seconds; one existing Starlette/httpx test-client deprecation warning.
- `pnpm test:session`: **4 passed**. Retaining access across creation/resume, migrating older sessions and isolating invalid entries are covered.
- TypeScript and Vite production build: **passed**, both locally and in the multi-stage Docker build.
- Reference-pack schema and semantic validator: **passed** for all six scenarios and three 100-record cohorts.
- `docker compose -f compose.workbench.yml up -d --build app`: **passed**. Both app and PostgreSQL containers reported healthy.
- `python scripts/check_workbench.py` against the Docker application: **passed**. Actual PostgreSQL, request lifecycle, dynamic provider LFD/fee updates preserving holds, authenticated SSE, playback, revision/idempotency behavior, durable CP-SAT jobs and source retrieval were exercised.
- Browser navigation, forms and persisted-state checks described above: **passed**. Screenshots are in `docs/screenshots/`.

The local demo is running in Docker at `http://127.0.0.1:8088`. No new cloud account, paid service, live API key or database login was required. Hosted team deployment was not changed. GitHub CI execution is separate from these observed local checks.
