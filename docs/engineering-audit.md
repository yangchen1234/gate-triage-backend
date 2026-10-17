# Gate Triage engineering audit

Audit date: October 17, 2026. Baseline: `40b7a76`, plus the corrective source changes described below. This is a review of the local, synthetic workbench; it does not certify a terminal operating system or live port deployment.

## Acceptance result and evidence

The reviewed backend passes **43 API integration checks**, including real PostgreSQL and separate operating-system processes, and **13 selected simulation-invariant checks**. The PostgreSQL checks create a unique temporary schema and remove only that test schema. They do not reset the demo database or delete existing workspaces.

| Check | Observed result | What it establishes |
|---|---|---|
| API suite with `WORKBENCH_TEST_POSTGRES_URL` configured | 43 passed in 18.30 seconds | Workspace isolation, retries, transaction rollback, durable jobs, request lifecycle, malformed-input rejection and database-specific checks |
| Selected engine tests: `negative_control or replay_seek or same_clock or hold` | 13 passed in 7.74 seconds | Control-world capacity, replay isolation, independent restrictions and stale-plan guards |
| Two independent Python processes create with one retry key | Both return 201 and the same workspace/token; one row exists | PostgreSQL retry serialization works beyond a Python mutex |
| Two independent processes write against revision 1 | One 200, one 412; stored revision is 2 | PostgreSQL row locking and revision checks prevent lost updates |
| Inject an exception after request insertion/revision update, before audit/receipt completion | Entire transaction rolls back; the same retry key can subsequently succeed | A failed internal request leaves no orphan row, consumed receipt or partial revision |
| Expired job owner tries to finish, then a valid claimant retries | Expired completion is ignored; valid claim completes once with one success audit | Durable job completion is fenced by current owner, status and unexpired lease |
| PostgreSQL server playback advances and is then paused | Clock progress and revisions persist; subsequent paused ticks leave both unchanged | The JSON playback predicate and durable world update work on PostgreSQL, not only SQLite |
| Docker Compose inspection during this audit | App and PostgreSQL healthy; both bound to loopback; PostgreSQL named volume present | The running demo uses a real separate database, not an in-memory browser substitute |

The previous Docker image was deliberately tested using a **new audit-only workspace**. An array command name, an array plan and a non-finite extra value each returned HTTP 500. The corrected source returns 422 and preserves the original revision/audit count in regression tests. Existing user workspaces were not used for these failure reproductions.

**Deployment closure:** these results validate the corrected source. Rebuild the application image and rerun the smoke test before treating the running image as updated. The subsequent emergency/relational-scale pass completed **73 combined checks with PostgreSQL configured**, including a durable-worker-generated 119,014-row SQL cohort. See [the relational subsystem evidence](relational-scale.md) and [the emergency workflow](emergency-workflow.md).

## Confirmed defects corrected

Severity refers to this application's data and result integrity. No physical terminal equipment or government system is connected.

| Finding | Severity | Correction | Regression evidence |
|---|---|---|---|
| Malformed command names/plans escaped validation as 500; unknown fields and non-finite JSON could reach PostgreSQL writes | P2 | Validate registered command names/fields, finite values and plan object shape before dispatch | `test_malformed_commands_return_validation_error_without_writes` |
| Simulated customs observations accepted string booleans; malformed hold items could crash projection. A string such as `"false"` could be treated as truthy | P1 for model integrity | Require boolean/null pickup fields, object/null hold structures, numeric measurements and actual boolean verification flags | `test_simulated_evidence_cannot_bypass_types_or_crash_projection` |
| A finishing job checked lease ownership through an ordinary read, then performed an unfenced ORM update; expired owners were not excluded | P1 for durable-job integrity | Commit the result with one SQL compare-and-set on job ID, current owner, running status and unexpired lease. Only a successful update writes the completion audit | `test_expired_completion_cannot_commit_before_recovery`, real-PostgreSQL counterpart |
| Playback read and locked every simulation workspace, including paused ones, on each worker iteration | P2 | Query only workspaces whose persisted playback flag is true. Batch faster playback into at most one publication per second | Reviewed SQL filter plus persisted playback/start-stop tests; no production-scale throughput claim |
| A plan job could be read through the experiments/exports path; supplied run IDs were accepted without checking their workspace | P2 | Verify route-specific result type and supplied run ownership | `test_result_specific_route_and_run_id_are_not_silently_ignored` |
| Adopting a fully current, metadata-created development database stamped the initial migration, then tried to recreate its newer table | P2 | Stamp the current migration head only after the existing column-complete development schema check | `test_current_metadata_schema_can_be_adopted_and_reopened` |
| SQLite did not enforce its declared request/workspace foreign key, unlike PostgreSQL | P2 | Enable SQLite foreign-key enforcement on every connection | `test_sqlite_enforces_declared_request_foreign_key`, real-PostgreSQL constraint check |
| Non-ASCII webhook signatures could throw instead of returning an authentication failure; notification IDs were not bounded to the database contract | P2 | Validate hexadecimal signature shape before constant-time comparison; validate string notification IDs and serialize duplicate receipt insertion in PostgreSQL | Signature, signed delivery, duplicate and conflicting-ID tests |
| The API accepted an experiment horizon up to 480 minutes although the engine supported at most 240; repeated seeds could masquerade as independent repeated worlds | P2 | Reject unsupported horizons, duplicate seeds and out-of-range seeds before queue insertion | `test_invalid_experiment_parameters_rejected_before_queueing` |

The first schema's descriptive workspace references remain largely application-enforced; the request table has a declared foreign key. Enabling SQLite foreign keys does not invent constraints absent from the schema. The tests distinguish these guarantees rather than calling all references database-enforced.

## Extension corrections

The strict command audit initially excluded the already-supported `provider` evidence kind. The deployed smoke check caught this regression. The registry now accepts provider deadline/fee observations and source business timestamps while retaining strict availability/hold validation; a positive LFD/fee API regression verifies the independent hold stays in force.

Cross-context scale review also corrected three concrete issues before acceptance: FIFO candidate SQL no longer prefilters by priority; restrictions bind to their generating run instead of carrying a future incident minute into a fresh run; and precision reset cannot erase an unresolved modeled incident. Compatible incident scopes now have phase-specific effects rather than treating wind, road closure and channel blockage as the same whole-terminal shutdown. A horizon-complete clock rejects an advance without an artificial event. See the scale API regression tests for the reproductions.

## Cross-stack consistency

The UI and backend agree on `throughput`, `balanced`, `recovery` profiles and `optimized`, `fifo`, `priority` strategies. A computed candidate is a persisted job result. Selecting it requires a completed job belonging to the workspace, its input revision and a current workspace revision. Changing evidence at the **same virtual minute** makes the earlier candidate stale. Selecting a plan does not advance time; the simulator starts work only when its clock advances and execution guards pass.

Internal coordination requests have their own durable lifecycle and status history. Creating, progressing or resolving a request changes the workspace revision and audit trail, but leaves the entire underlying simulation/provider state unchanged. Requests are not notifications, bookings, customs clearances or work performed by outside parties. The tests check this separation using the actual stored state and the multi-issue container's independent departure restrictions.

Two frontend issues were reported to the frontend owner during this audit:

- Retain a logical mutation's retry key when a response is lost; generating a new key for a manual retry can duplicate an already committed internal request.
- Ignore a same-workspace response whose revision is below the revision already displayed; a delayed poll or an exact historical retry response can otherwise rewind the screen temporarily.

The frontend owner implemented pending-key retention, one transport retry using the original prepared request, and monotonic revision application. Their `pnpm --dir apps/web test:session` run reported **10 passing checks**, including lost-response/manual-retry key reuse, prepared-header retry and monotonic revisions. This is separately reported frontend evidence, not part of the backend's 43 checks. Browser validation remains a distinct acceptance activity.

## Model guarantees and the limits of comparison

The simulation's equal-service control has two lanes, five-minute service and sufficient ready demand. All three policies complete exactly **96 handoffs in 240 minutes** in that configured control. That is a closed-model arithmetic check, not a claim about a real terminal's capacity.

The comparison uses identical synthetic service samples, arrivals, resource constraints and observed-information timing for each paired seed. FIFO and priority baselines skip blocked work and share the same execution guards. Completed gate handoffs count as throughput; inspections, contacts and projected plan operations do not. Historical full-out reports are distinct from newly simulated completions. Completed-container waiting statistics and unfinished wait lower bounds remain separate.

The larger evaluation and its raw runs belong in [the simulation evaluation](simulation-evaluation.zh-CN.md). This audit does not substitute unit-test counts for experimental performance results, and does not treat a simulation win as proof of real-world throughput improvement.

Several choices differ from the full aspirational specification:

- The current CP-SAT objective is a transparent weighted objective. It is not a proven lexicographic optimum, a hard maximum-wait guarantee or a guarantee against starvation.
- Running work is protected by execution guards; a five-minute freeze for all pending plan commitments is not implemented.
- Recovery time remains unidentifiable unless a normal-world target is explicitly configured. No recovery-time improvement is claimed from the current output alone.
- Interrupted modeled operations restart under the current world model. This is a declared simulation assumption, not an assertion about every terminal procedure.
- Road capacity, equipment, independent scale observations and temperatures are labeled synthetic operational inputs. Terminal49 carrier weight and equipment type do not supply those measurements.

These are bounded implementation/model limits requiring separate design work if made product requirements. They must not be described as already proven by a benchmark against a mature logistics platform.

## Deployment and operational boundary

The supplied Compose stack has a non-root application container, a separate PostgreSQL 17 container, health checks, a named database volume and loopback-bound ports. Alembic versions `wb_0001`, `wb_0002` and `wb_0003` upgrade the isolated `wb_*` schema. The legacy `main.py` application and its hosted deployment remain separate.

The worker is embedded in one application process. Jobs use SQL leases and resumable claims, while playback pauses on application restart instead of inventing elapsed-world progress. This single-process local deployment is the accepted topology. Starting another instance currently performs the same playback-pause recovery, so this is not a tested active/active clock service or a high-availability terminal controller.

Workspace access is an anonymous browser-held capability for synthetic rehearsals. Production users, organizational RBAC, account provisioning and live-account authorization are not implemented by that capability. Live Terminal49 workspace creation remains disabled; the read-only adapter and verified webhook inbox establish a boundary, not a validated account integration. No cloud LLM is used by the local source search.

Observed Docker health and persistent database rows establish that the demo runs and stores its work. They do not establish a production load envelope, disaster-recovery objective, availability SLA, penetration-test certification or regulatory approval. The delivered system makes none of those claims.

## Reproduce the checks

```bash
# Offline/SQLite checks: the three explicit PostgreSQL checks skip without a URL.
.venv/bin/python -m pytest tests/test_workbench_api.py -q

# Use the local PostgreSQL URL already configured for development.
# Tests create/drop their own randomly named schema, not the demo schema.
WORKBENCH_TEST_POSTGRES_URL="$WORKBENCH_DATABASE_URL" \
  .venv/bin/python -m pytest tests/test_workbench_api.py -q

.venv/bin/python -m pytest tests/test_workbench_engine.py \
  -k 'negative_control or replay_seek or same_clock or hold' -q

docker compose -f compose.workbench.yml ps
.venv/bin/python scripts/check_workbench.py
```

The pytest run emitted one existing FastAPI/Starlette test-client deprecation warning about its HTTPX test transport. It did not hide a test failure. Dependency/tooling maintenance is separate from the passing application checks above.
