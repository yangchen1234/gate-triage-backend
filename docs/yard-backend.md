# Persistent yard backend

The `/?preview=yard` interface now loads inventory and operational state from the
FastAPI application and a SQLite database. It does not generate or persist active
operational state in the browser. Agent generation and its existing API are unchanged;
no yard request calls a model, Terminal49, equipment or a release authority.

## Run locally

From the repository root, start the backend:

```sh
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8010 --workers 1
```

In another terminal:

```sh
cd apps/web
pnpm install --frozen-lockfile
pnpm dev --port 5176 --strictPort
```

Open `http://127.0.0.1:5176/?preview=yard`. Vite proxies `/api` to port 8010.
The header displays **Connected · SQLite** when the server has acknowledged data.
The build also works when served by FastAPI itself (`http://127.0.0.1:8010/?preview=yard`).
The original `/` operations console, `/containers`, `/scenario`, `/plan` and console
API continue to use their existing contracts. There is no new dependency or database login.

## Storage and ownership

`YARD_DATABASE_PATH` defaults to `.local/yard.sqlite3` under the repository. The
ignored database and its WAL files never belong in GitHub. Schema version 1 has
separate relational tables for workspaces, runs, blocks, containers, decisions,
jobs, active resolutions, departures, idempotency records and append-only audit events.
The original generated observation is retained separately from subsequent observations
and verified corrections. All records are **synthetic**, including manually confirmed
permissions in the demo.

A browser receives an opaque, HttpOnly, SameSite=Strict cookie, scoped to `/api/yard`.
Only its SHA-256 digest is stored. It is a demo workspace capability, not a verified
operator identity. Tabs in the same browser share a workspace; separate browsers have
independent workspaces. LA and Rotterdam maintain distinct runs within that workspace.
The capability and demo retention expire after seven days without session renewal.
New-session creation cleans up expired workspaces; at most 100 workspaces are accepted.
The API is not a production authentication or multi-organization authorization system.

The seed generator preserves the original cohorts (LA 1,780 / 12 blocks; Rotterdam
1,142 / 8 blocks). Golden SHA-256 contracts compare every fixture field and advisory
assessment against the original TypeScript implementation for both ports and two seeds.
The server's current and routine assessments drive the UI; the old browser generator
and workflow functions remain reference/test utilities only. Existing localStorage
prototype history is left intact and is **not imported as verified evidence**.

Ryan's original 100-row source fixture and legacy queue are not silently assigned
fictional physical positions: their zone A/B records do not establish bay, row and tier.
The dedicated yard seed is explicitly labeled `yard_seed_v1`. A real source adapter
would need verified identity/location mapping and source freshness before replacing it.

## HTTP contract

All endpoints are under `/api/yard`. Documentation is also in `/docs`.

| Method | Path | Behavior |
|---|---|---|
| POST | `/session` | Create or renew the cookie-scoped workspace; repeat bootstrap preserves it |
| GET | `/health` | SQLite connectivity and synthetic/non-agent mode |
| GET | `/ports` | LA/Rotterdam metadata |
| GET | `/ports/{port}/snapshot` | Consistent complete snapshot; unchanged conditional reads return 304 |
| GET | `/ports/{port}/containers` | Paginated current inventory; number/company/block/exception filters |
| GET | `/ports/{port}/containers/{id}` | Current or departed record and immutable initial observation |
| GET | `/ports/{port}/audit` | Bounded history across current and archived runs for this workspace/port |
| POST | `/ports/{port}/commands` | Validated transactional mutation |

Port values are `la` and `rotterdam`; scenario values are `routine`, `power`,
`congestion` and `combined`. Current-inventory queries exclude departed records.
`container_id` normalizes case, spaces and punctuation; `company` matches carrier
code or name, never cargo ownership. Both fields compose with AND. Default limit
is 100, maximum 200. Audit maximum is 500.

POST requests require `X-Yard-Request: 1`. Commands additionally require:

* `If-Match`: exact quoted ETag from the latest snapshot (`"run-id:revision"`).
* `Idempotency-Key`: one unique 8–128 character request identifier, reused with
  the **same body and original ETag** after an ambiguous response.

The server returns the complete acknowledged snapshot and its new ETag. It owns
timestamps, scenario state, assessments, workflow transitions and inventory. Client
`at`, arbitrary state patches, unknown fields and non-boolean confirmations are rejected.
Invalid commands do not change revision or any record.

Example bodies (all observations and references below are simulated):

```json
{"type":"scenario","scenario":"power"}
{"type":"review","containerId":"SIMU2000895","issue":"power","scenario":"power","choice":"accepted","note":"SIMULATED maintenance handoff"}
{"type":"start","key":"job-key-returned-by-server"}
{"type":"complete_work","key":"job-key-returned-by-server","note":"SIMULATED backup power connected"}
{"type":"verify","key":"job-key-returned-by-server","evidence":"SIMULATED unit-power verification","confirmed":true}
{"type":"gate_out","containerId":"SIMU2000003","scenario":"routine","evidence":"SIMULATED physical exit ticket","clearanceConfirmed":true,"exitConfirmed":true}
{"type":"observe","containerId":"SIMU2000895","issue":"temperature","note":"SIMULATED new telemetry excursion"}
{"type":"reset"}
```

A normal run must be loaded before commands. The issue in a review must be active
in the server's current scenario. A request cannot use a container from another port,
workspace, archived run or a departed record.

## Consistency, failure handling and state transitions

Each mutation uses a SQLite `BEGIN IMMEDIATE` transaction, foreign keys, a unique
occupied-slot index, one active case per container/issue, and one departure per run/ID.
WAL mode and a five-second busy timeout are configured on actual connections.
Expected revision is checked inside the write transaction. Revision, domain records,
audit and idempotency result commit together. A stale client gets 412 and a refresh;
it must review rather than silently reapply its stale intention. A reused request key
with another body/version gets 409. An exact replay returns current data without
another operation, even after a process restart or lost post-commit response.

The workflow is:

1. Accept → **Queued**. Flags and stock do not change.
2. Start → **In progress**.
3. Report a nonempty work summary → **Verify result**.
4. Explicit confirmation plus evidence → **Resolved** for that issue only.
5. Normal containers remain in stock. Gate-out also requires all independent issues
   and accepted tasks cleared, release confirmation, physical-exit confirmation and
   a reference. Only then is the record excluded from active inventory. Last position,
   evidence and earlier decisions remain queryable/audited.

Free modeled tier slots and plug occupancy derive from current stock; they are not
incremented by a client-side counter. Retrying a departure cannot free another slot.
Unit backup power does not restore R1, and a verified alternate pickup does not
reopen a whole region. Positional vacancies remain modeled addresses, not validated
stacking, lifting or rehandling instructions; no equipment move is dispatched.

The **Simulate a new observation** controls record a server-stamped event, preserving
the original observation. Multiple independent issues may coexist. An observation
invalidates only that issue's prior resolution. A resolved case and evidence stay in
history; recurrence requires a new acceptance and unique case key. A fresh observation
while awaiting verification returns the case to work in progress, preventing approval
of an obsolete completion. Non-reefer records reject reefer-only observations.

Regeneration archives the old run instead of deleting its audit. The new run has a
new ID and a higher revision; old requests cannot modify the new cohort even though
synthetic IDs are reused. There is a 40-run-per-workspace demo limit.

## Browser synchronization

Foreground pages check the server every two seconds and on focus. They send
conditional ETags so unchanged state has no snapshot body. Hidden pages pause polling.
Older reads cannot overwrite a newer acknowledged revision. The initial session call
is shared across React StrictMode bootstrap calls.

The UI updates only after a successful server response. During disconnection it
retains the last acknowledged data and disables mutations. Ambiguous saves keep their
original body, version and key and expose **Retry save**, including inside confirmation
dialogs. A completed retry does not duplicate task work or gate-out. The browser does
not pretend that local changes were saved, and it does not fall back to localStorage
as the operational source.

## Deployment and backup

The existing Docker image includes the API, seed generator and web build. A normal
SQLite file survives an application process restart. **Render's free ephemeral
filesystem does not provide durable storage across redeploys/replacement.** Before
using this as a persistent hosted demo, provision a persistent volume and set
`YARD_DATABASE_PATH=/var/data/yard.sqlite3` (or implement/migrate to an external database).
This change does not provision a paid service or change the existing Render/main deployment.
Do not run this SQLite implementation across multiple instances with independent disks.

Create a consistent online backup with SQLite's backup API, including committed WAL:

```sh
.venv/bin/python scripts/backup_yard.py --output .local/backups/yard-before-demo.sqlite3
```

The helper refuses to overwrite files and verifies backup integrity. Back up the
source database through this helper rather than copying only the main file during writes.

References: [SQLite transactions](https://www.sqlite.org/lang_transaction.html),
[Render free-service storage limitations](https://render.com/docs/free#local-files-lost-on-redeploy),
[FastAPI cookies](https://fastapi.tiangolo.com/advanced/response-cookies/),
[FastAPI lifespan testing](https://fastapi.tiangolo.com/advanced/testing-events/).

## Verification

Backend tests cover authoritative validation, independent issues, recurrence,
immutable provenance, restart persistence, command replay, stale revisions,
concurrent departures, rollback on failure, lost post-commit responses, reset archives,
workspace/port boundaries, strict inputs, cookie flags and no agent invocation.
Cross-language fixture and policy fingerprints protect the original demonstrations.
Frontend tests cover cookie bootstrap, non-agent routes, ETags, exact retry headers,
stale-error detail preservation and wrong-workspace/port rejection.

Browser QA exercised a complete work/verification/gate-out flow: resolved stock
remained 1,780 with 812 free slots; physical exit changed stock to 1,779 and free slots
to 813. A second tab automatically saw a task move into progress. Stopping the server
retained data and disabled writes; restart reconnected automatically, and page reload
preserved the departure and task. SQLite integrity checks and an online backup were
also performed. All values are synthetic demonstration results.

Rotterdam was checked in Dutch: 1,142 containers across eight blocks and 658 free
tier slots. Combined disruption changed flagged containers from 47 to 342 without
changing inventory. Switching ports retained the LA departure, active case and routine
scenario independently from Rotterdam's saved scenario.

Validation for this integration: **180 backend tests, 43 frontend tests, and the
TypeScript/production build passed**. Backup tests include live WAL contents,
overwrite protection and cleanup of failed backups. This is a local synthetic demo;
these counts are functional validation, not evidence of production throughput.
