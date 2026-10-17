# Synthetic emergency coordination

The emergency workflow is an executable local tool sequence: observe the workspace, assess a geographic scope, retrieve inspectable sources, validate effects, and create a durable internal human follow-up. It uses deterministic policies and the existing constrained simulator. **No LLM, outside notification or physical dispatch occurs.**

## Persistent record and boundaries

Each incident is stored in `Workspace.state.emergency_incidents`, with its report, scope assessment, proposed/actual synthetic effects, scenario-specific response strategy, source references, five workflow stages, human acknowledgement and recovery note. The linked follow-up is a real `CoordinationRequest` database row. Both commit in the same transaction with the workspace revision, audit event and retry receipt.

`spatial.py` owns the incident catalog and geographic applicability. `spatial_simulation.py` applies layered model effects. The coordinator keeps their outputs inspectable and checks that incident actions do not invent completed handoffs, advance time, change site evidence or fabricate provider facts. Recovery may reconcile only already-persisted source envelopes whose payloads and processed hashes match the inbox; a human acknowledgement itself is not a customs clearance.

Unknown scopes, reference-only terminals, warning-only reports and unsupported incident/scope combinations create monitoring and internal follow-up records without unsupported precision-model capacity changes. The [relational volume model](relational-scale.md) has wider executable terminal scope, with a separate scale assessment and phase-specific restrictions. Its metrics and effects remain distinguished from the precision model. Restrictions bind to a particular scale run; replacing that dataset or resetting the precision exercise is rejected until active modeled incidents receive recovery acknowledgement.

Historical retrieval is filtered to the scenario’s curated historical URLs and relevant local product policy. The workflow exposes allowed source IDs and filtered-hit counts so a matching year cannot silently attach an unrelated disaster citation.

Historical incidents explain the scenario class. The 2024 channel obstruction is explicitly Baltimore-inspired and transposed into an LA exercise, not an assertion that the event happened in Los Angeles. Geographic terminal reference points do not certify real gate, crane, road or exclusion-area geometry.

## API

All routes use the existing workspace token. Every mutation requires the current `If-Match` revision and a stable `Idempotency-Key`; exact retries are replayed before checking the now-current revision.

| Method | Workspace-relative route | Contract |
|---|---|---|
| GET | `/incidents` | `data.items`, `data.catalog`, `data.scopes`, explicit synthetic escalation policy |
| POST | `/incidents` | `{scenario_id, scope_id, severity, note}`; severity is `critical`, `restricted` or `watch` |
| POST | `/incidents/{id}/acknowledge` | `{note}` records simulated human ownership; restrictions remain |
| POST | `/incidents/{id}/resolve` | `{acknowledged:true, note:<nonempty recovery note>}` requests simulated recovery |

Create returns 201. Acknowledge and resolve return 200. Mutation responses contain `data.incident` and `data.workspace`, plus the normal metadata envelope. This lets the UI refresh both the map and worklist against the accepted revision.

Incident fields include `assessment`/`impact`, `effects`, `proposed_effects`, `proposal.strategy`, scenario-specific `proposal.actions`, `workflow`, `sources`, `escalation`, `provenance`, and `orchestrator.llm_used=false`.

## Ownership and recovery are separate

Creating an incident records an internal follow-up owned by the scenario's configured role. A separate acknowledgement marks that internal request in progress. It does not remove the incident, restore a resource or alter an independent hold.

The demonstration policy sets an ownership acknowledgement deadline **10 virtual minutes** after the report. `incident_view()` derives overdue status from the larger elapsed precision time or elapsed time in the incident’s same scale run. The seven-day scale clock never advances the 240-minute precision clock. It does not pretend to send a notification. This ten-minute deadline is a versioned synthetic product policy, not an industry-wide requirement.

Resolving requires a real JSON boolean acknowledgement and a nonempty recovery evidence note. The note is an operator-reported assertion inside the simulation, not verified external authority. The effect model removes only that incident's layer. Other active incidents, manual closures and unrelated source outages continue to apply. A resolved internal request alone does not resolve its incident.

## Verification

The emergency integration suite passes **18 checks** with the six-scenario catalog; it is also included in the combined **73-check API/emergency/scale** PostgreSQL run. It exercises actual persisted worlds and linked request rows, covering:

- Five-stage execution, source retrieval, exact retries, database reconnection and map-derived capacity.
- Scoped East closure with West capacity preserved, overlapping restrictions, and manual closure preservation.
- Unknown/reference-only/warning/unsupported scopes with no precision-model side effect.
- Strict human acknowledgement, recovery note requirements, workspace isolation and replay-mode rejection.
- Layered cyber incidents, independent manual source outage, and validated queued-source reconciliation.
- A deliberately unsafe tool result that clears a hold is rejected and rolled back without an accepted incident or internal request.
- Ownership acknowledgement remains distinct from recovery; overdue escalation follows virtual time.

Run the current suite after catalog or model changes:

```bash
.venv/bin/python -m pytest tests/test_workbench_emergency.py -q
```

This verifies the synthetic workflow and its persistence. It does not establish live emergency response readiness, a real navigation plan, a universal safety threshold or a production authorization system.
