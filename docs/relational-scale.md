# Relational port-volume rehearsal

This subsystem runs a second, explicitly synthetic movement-flow model beside the 100-container precision exercise. It stores movements in PostgreSQL rows, pages them through bounded APIs and aggregates their state with SQL. It does not expand the precision snapshot into a 119,000-item JSON document or claim a whole-port CP-SAT schedule.

## Calibration and units

The [Port of Los Angeles 2025 statistics](https://portoflosangeles.org/business/statistics/container-statistics/historical-teu-statistics-2025) report 10,239,318.40 annual TEU and 1,019,837.30 July TEU. Annual-average and July-average daily TEU calibrate these generated cohorts:

| Profile | Modeled duration | Synthetic movement records | Modeled TEU |
|---|---:|---:|---:|
| `la_average_day` | 1 day | 17,002 | 28,053 |
| `la_peak_month_day` | 1 day | 19,938 | 32,898 |
| `la_seven_day` | 7 days | 119,014 | 196,371 |

Assumptions are inspectable in `GET /scale`: approximately 65% forty-foot and 35% twenty-foot records, equal movement allocation across seven real terminal identifiers, deterministic synthetic arrivals and dwell, twelve invented service slots per terminal and three-to-nine-minute service samples. Category TEU proportions follow the annual aggregate; largest-remainder allocation preserves each generated TEU total.

These are flow records. They are **not** historical individual container records, simultaneous yard inventory, actual terminal market shares, measured equipment capacity or live Terminal49 data. Terminal49 does not provide the invented scale measurements, gate service slots, crane geometry or temperature data used by the separate precision exercise.

## Persistence and generation

Alembic `wb_0003` adds three tables:

- `wb_scale_runs`: profile, seed, generation state, independent clock, resource state and provenance.
- `wb_scale_movements`: composite run/record key, unique run/container number, terminal, phase timing, TEU, status and last event sequence. Terminal/status, arrival and ready-time indexes support bounded queries.
- `wb_scale_events`: append-only sequenced cohort/window events. HTTP responses expose counts and bounded details rather than returning the entire stored update batch.

Database checks constrain TEU to one or two, registered statuses, positive service duration, ordered arrival/ready/completion timing, bounded run clocks and nonnegative event counts. Foreign keys bind movements/events to their run and runs to their workspace.

Creating a run commits its durable `scale_seed` job, workspace revision, audit record and retry receipt together. The worker streams batches of 1,000 inserts into one cohort transaction. A failed generation rolls the cohort back and records a failed run. A recovered job reuses a fully ready run without duplicate rows or duplicate seed events. PostgreSQL publishes job progress in separate short transactions; SQLite skips intermediate progress writes to avoid locking its own bulk transaction.

## API contract

All routes are relative to `/api/v1/workspaces/{workspace_id}`. Workspace-token access applies throughout. Writes require current `If-Match` and a stable `Idempotency-Key`; an accepted retry is replayed before the revision check.

| Method | Route | Input / result |
|---|---|---|
| GET | `/scale` | Profiles, current run, SQL summary and explicit model limitations |
| POST | `/scale` | `{profile,seed}` → 202 durable job, run ID and expected record count |
| GET | `/scale/containers` | `offset`, `limit` 1–100, optional `terminal_id`, `status`, `query` → items/total/offset/limit |
| GET | `/scale/events` | Bounded event summary page |
| POST | `/scale/advance` | `{minutes:1..120}` → accepted run clock, SQL summary, changed-record count and current restrictions |
| GET | `/jobs/{job_id}` | Durable job status, progress and result |

Seeds and advance minutes require JSON integers; booleans, fractional values and coerced strings are rejected. At the horizon, advance returns `409 SCALE_HORIZON_REACHED` without consuming a revision or inventing a zero-progress event.

PostgreSQL scale/map reads begin a `REPEATABLE READ` transaction before their first query. Workspace metadata, run clock, page counts and grouped movement totals therefore share one MVCC snapshot even if an advance commits mid-request. The reader does not lock out that writer. This concurrent-reader guarantee is tested against PostgreSQL; the SQLite fallback is not presented as the same deployment guarantee.

A generated run replaces the *current view*, while earlier relational records remain stored. No historical-run browser is claimed. Replacement generation is rejected with `409 SCALE_INCIDENT_ACTIVE` while the current run has an unresolved modeled incident. Resolve it or create a separate workspace for an independent rehearsal. Precision reset is similarly blocked while an active modeled incident remains, and preserves the independent scale-run pointers after recovery.

## Independent clock and bounded execution

The seven-day scale clock is independent of the precision world's 240-minute horizon. Advancing 120 scale minutes does not advance the precision containers. The workspace stores only the current scale run ID and clock as small context pointers.

Each scale advance locks the workspace and run, selects at most 2,000 unfinished arrived records per terminal, always includes active service first, then uses arrival/ID order. This selection matches the current FIFO policy; it does not secretly use priority to prefilter a FIFO queue. The local phase/slot simulator computes changes only inside that bounded window. The API validates unique returned IDs, selected-record membership, status values and completed times before committing SQL changes, run state, an immutable window event, workspace revision and retry receipt in one transaction.

The resource state is persisted, so a long service is not counted as complete merely because a window ended. Permanent unknown prerequisites remain blocked. Interrupted work restarts after recovery under the declared model assumption. The scheduler rejects a window that omits a persisted active-service record. SQL status counts, not speculative window deltas, determine the displayed aggregate.

The independent incident acknowledgement deadline uses the larger elapsed time from the precision context or the incident's **same scale run**. Creating a new run does not turn an old incident minute into future information in the new clock.

## Different disasters produce different phase effects

Only compatible, known geographic scopes receive bulk effects. A battery incident reported at a reefer zone does not close the entire terminal. A single earthquake-inspected asset is handled by the precision asset model; the coarse bulk model only accepts terminal/port earthquake scope.

| Scenario | Bulk phase response | Work that can continue |
|---|---|---|
| Battery/access closure | Interrupt import gate-out service and block export gate-in arrivals occurring after the recorded incident minute | Already-arrived export vessel-load work |
| Wind | Interrupt export vessel-load work and block future import unload arrivals | Gate-out for imports already in the modeled yard |
| Channel obstruction | Block future modeled import arrivals | Already-arrived yard and gate work; no fabricated closure of every crane |
| Exit congestion | Reduce slots eligible for gate-out, preserving export load slots | Other phases under their existing restrictions |
| Cyber/data outage | Mark source freshness unknown; preserve known prerequisite blockers | Known permitted physical work, without inferring fresh clearance |
| Earthquake asset inspection | Close the selected terminal/port's coarse synthetic service pool | Other terminals outside the accepted scope |

`phase_incidents` retain their original scale start minute. Overlapping incident layers compose; resolving one removes only that report. Restrictions are bound to their `scale_run_id`, preventing a prior run's minute-60 incident from entering a new run at minute zero. Watch reports and unsupported combinations remain monitoring-only. All effects are simulations; historical references never establish current closure or confer release authority.

The map uses the incident's derived effective display severity. An overdue human acknowledgement can therefore turn a restricted marker critical. This denotes response urgency under our synthetic follow-up policy; it does not invent a worsening hazard, change the reported severity or silently tighten the applied operational restriction.

## Verification evidence

The combined backend API/emergency/scale suite passed **73 checks with real PostgreSQL configured**, including a separate-schema 119,014-row worker-generated cohort, exact 196,371 TEU, offset-100,000 pagination and guarded execution. That test also verified the precision cohort remained 100 records. It removed only its randomly named test schema.

Additional focused tests cover phase-scope applicability, 10-minute acknowledgement escalation while only the scale clock advances, atomic failed generation, deterministic retry reuse, strict input types, horizon rejection, replacement-run protection and reset protection. `scripts/benchmark_scale.py` records independent measured results; local timings are workload-dependent and are not a production SLA or evidence of improvement over a mature terminal platform.

Map integration checks additionally reconcile all seven terminal SQL counts, keep the precision clock and its 100-container cohort separate, preserve unknown reference-terminal precision metrics, enforce scoped token access, distinguish satisfied evidence checks from completed work, and read legacy vessel workorders through the compatibility snapshot without writing an upgrade during GET.

The PostgreSQL test also interleaves an actual API advance between a read transaction's initial context read and its later aggregate read: that reader retains the old clock/counts, the writer commits, and a fresh reader sees the new progress. This checks snapshot coherence rather than merely inspecting an isolation-level setting.

```bash
WORKBENCH_TEST_POSTGRES_URL="$WORKBENCH_DATABASE_URL" \
  .venv/bin/python -m pytest tests/test_workbench_scale.py \
    tests/test_workbench_api.py tests/test_workbench_emergency.py -q
```
