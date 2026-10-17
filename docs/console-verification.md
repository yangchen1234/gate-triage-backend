# Console release verification — 2026-10-17

Scope: the three-port console on top of Ryan's `ca08d9e` main branch. The independent Workbench simulation/PostgreSQL branch was not merged or modified.

## Observed checks

- Full isolated Python environment: **142 tests passed**. Covers retained legacy API/statistics behavior plus new session/agent boundaries and static-site integration.
- Frontend: **12 tests passed**, TypeScript/Vite production build passed. Tests include credential metadata unwrapping, no API-key browser storage, old-session response suppression, explicit/idempotent model dispatch, recovering a running job after an ambiguous submission, stale approvals, and currency/filter correctness.
- `pnpm audit --prod`: no known production-dependency vulnerabilities reported. This is a package audit result, not a penetration-test claim.
- Actual HTTP on the local Python server and production Docker entry point: all three port profiles retained 100 rows with correct local currencies, plan retries returned the same ID, rules generation made zero model requests, a human decision was recorded, and a subsequent scenario revision rejected stale approval.
- Actual browser controls: switched LAX → SHA → RTM; verified CNY/EUR labels, opened four-source evidence, searched a container down to one row, generated a five-action rules plan, recorded a review note/approval, and disabled remaining old approvals after a customs outage.
- Browser credential workflow used an explicitly synthetic nonfunctional key: submitting emptied the password field and updated configuration metadata without making a model call; disconnect removed configuration. No real Claude key or paid request was used.
- Final web output is `index-B0WuO40P.js` with `index-D3w3c-cp.css`. Docker builds these assets from source rather than committing compiled output.
- `git diff --check` passed. Review checked session isolation, fallback truthfulness, fixed provider endpoint, key-safe errors, bounded invocation, cross-session/stale decision rejection, and race handling.

## Repairs encountered

1. Legacy fee and scenario assertions still described an earlier fixture/default. Fee expectations were independently recalculated from the current raw records and profile tiers; scenario checks now retain the default port field.
2. Passing a priority-sorted queue into FIFO statistics changed tie order. The console now restores source input order for statistics, and a three-port six-lane regression matches the legacy service.
3. Configuration responses contain a `model` wrapper. The client now unwraps it correctly instead of treating a successful key configuration as disconnected.
4. Model errors, malformed JSON, and invalid draft structures now preserve a clearly labeled deterministic/template fallback without exposing provider exception text.
5. Slow requests could overwrite a newer session or a human decision. Token-generation guards, serialized UI mutations, bounded fetches, and stable generation idempotency keys address those races.
6. Final decisions are no longer silently overwritten by an opposing decision. Exact retries recover the existing record; conflicting repeats return 409.

## Limits

This is a synthetic advisory demo with expiring process-memory sessions. It does not validate live Terminal49 data, real port capacity/tariffs, realized savings, enterprise accounts/RBAC, durable database approval history, or multi-instance operation. Real Claude connectivity and its actual cost still require the user's valid key and available model ID. Existing `/health` model fields describe the legacy explanation extension; the console reports its own configuration and actual plan mode separately.
