# Gate Triage Workbench

An isolated, full-stack operations rehearsal for a Port of Los Angeles container-terminal exception coordinator. It combines inspectable evidence, parallel coordination tasks, permission checks, resource-constrained planning and event-driven simulation. All default data is synthetic.

This branch leaves the existing `main.py` API and the team's hosted application unchanged. The new entry point is `workbench_main:app`.

![Operations workbench](docs/screenshots/workbench.png)

## Run with Docker

Requirements: Docker Desktop / Docker Engine with Compose. No Terminal49 account, LLM account or cloud database login is required.

```bash
docker compose -f compose.workbench.yml up --build -d
```

Open [the workbench](http://127.0.0.1:8088) or [the API documentation](http://127.0.0.1:8088/docs). PostgreSQL runs in a separate named volume; restarting the app retains workspaces, evidence, audit events and jobs.

```bash
docker compose -f compose.workbench.yml logs -f app
docker compose -f compose.workbench.yml down
```

`down` keeps the database volume. Removing the volume deletes local rehearsal history. The app and database bind to loopback only. Set `WORKBENCH_DB_PASSWORD` before any deployment beyond this machine.

## Local development

Use Python 3.12+, Node 24 and pnpm 11.25.0.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-workbench.txt
docker compose -f compose.workbench.yml up -d db
cd apps/web
pnpm install --frozen-lockfile
pnpm build
cd ../..
export WORKBENCH_DATABASE_URL='postgresql+psycopg://gate_triage:gate_triage_local@127.0.0.1:54329/gate_triage'
.venv/bin/uvicorn workbench_main:app --host 127.0.0.1 --port 8088
```

For frontend hot reload use `pnpm dev` in `apps/web`; Vite proxies `/api` to the backend. The single-origin production build is served by FastAPI. If no database URL is set, an explicit local SQLite fallback is available; the delivered demo uses PostgreSQL.

## Try the rehearsal

1. Open Operations. Search the full 100-container cohort and inspect the multi-issue container `TRXU7731902`.
2. Check each issue's evidence, next action, responsible role and independent departure blockers. Claiming a task does not clear its evidence requirement.
3. Open Simulation. Play the server clock, change speed, pause, or advance time. Inject a scoped East gate closure and observe West gate work continue.
4. Inject delayed or duplicate messages, then recover the feed. Known restrictions should remain intact and the counters explain what happened.
5. Submit explicitly simulated verification evidence. A normal temperature does not remove a customs hold or authorize a movement.
6. Run Experiments. Compare FIFO, priority and constraint optimization with the same fixture, seed, information and capacity. Results may tie or get worse; the app does not invent improvement percentages.
7. Search the source library. This is local source retrieval without an LLM. Historical sources explain scenarios, not present port conditions.

The Operations layout takes interaction cues from the supplied Port Optimizer screenshot: scope selection, dense sortable worklists, row selection, column preferences and a request dialog. Select containers to save an internal coordination request and track its status. Requests are database records inside this rehearsal; they do not send messages, create bookings or remove holds.

Use **Change scenario → Recent rehearsals → Resume** to return to earlier workspaces. Their access tokens stay in this browser's local storage; use the same browser and origin to retain access. Temporary connection errors keep the saved workspace instead of silently creating a replacement.

## Architecture

- React / TypeScript / Vite web interface.
- FastAPI workspace-scoped API, optimistic revisions, idempotent writes and SSE revision notifications.
- PostgreSQL via SQLAlchemy; durable workspace snapshots plus queryable evidence, tasks, audit events, retry receipts, webhook inbox and leased jobs.
- Server-side playback and discrete-event world; independent, observed-time evidence updates.
- OR-Tools CP-SAT optional intervals and resource constraints, with solver status and plan validation.
- Local BM25 source retrieval; no cloud generation is required or claimed.

The worker is part of the local application process. Playback pauses after a server restart, avoiding invisible catch-up. This is a local demonstration deployment, not a high-availability port control system.

## Data and safety boundaries

Terminal49 is the only intended live external business provider. Its reported availability does not authorize physical departure. Weight, temperature, lanes, equipment and road events in this demo belong to a separately labeled simulation overlay. No physical equipment, customs systems, bookings, payments or external messages are controlled.

Live credentials remain unconfigured by default. The adapter and signed webhook inbox provide an integration boundary, not a claim that the team account or live coverage has been validated. Actual live activation needs account permissions, HTTPS, a secret-management setup and access controls.

Historical inspirations include the 2024 battery-truck incident, the 2017 terminal cyber disruption, 2021 long-dwell congestion and a 2023 weather-warning control. Scenario timings, containers and operational impacts are synthetic. The proposed 2021 additional dwell fee was never activated and is not counted as accrued savings.

## Verification and design

```bash
.venv/bin/python -m pytest -q
cd apps/web
pnpm test:session
pnpm build
```

See [the technical specification](docs/gate-triage-technical-specification.zh-CN.md), [the realtime decision contract](docs/realtime-decision-contract.zh-CN.md), [reference fixtures](docs/reference-pack/README.md) and [the verification record](docs/workbench-verification.md).
