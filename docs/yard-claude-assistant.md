# Yard Claude assistant

The container inspector now includes an optional Claude panel for an active exception.
The operator can ask a bounded question, generate proposed checks, inspect cited source
facts, and edit/copy an unsent fault-report email. Opening the panel, polling, switching
containers, and changing scenarios never initiate a model request.

## Local connection

The local `.env` is private, ignored by Git and Docker, and created with mode `0600`.
It is not part of this repository. Use the worktree containing this document, not a
different checkout. The required variables are:

```dotenv
ANTHROPIC_API_KEY=YOUR_CLAUDE_KEY
ANTHROPIC_MODEL=claude-sonnet-4-6
CONSOLE_TEAM_ACCESS_CODE=YOUR_SEPARATE_PRIVATE_CODE_AT_LEAST_16_CHARACTERS
YARD_DATABASE_PATH=.local/yard.sqlite3
```

Use a model ID available to the Anthropic account. The access code is independent
of the provider key. Do not replace it with an API key. Existing process environment
variables take precedence over `.env` values.

```sh
.venv/bin/python scripts/run_yard.py --check-env
.venv/bin/python scripts/run_yard.py
```

The check only reports field presence/format; it neither prints credentials nor calls
the provider. Restart the backend after saving `.env`. In the yard inspector, expand
**Claude connection**, enter the separate access code, and click **Connect team Claude**.
Select an exception, optionally enter a question, and explicitly click **Generate with
Claude**. The session's authorization lasts up to 15 minutes. Configuring credentials
does not verify provider billing, model access or quota; the first explicit generation
may still fail with a sanitized error.

On Render, set the same three variables in the service environment. `.env` is local
only and is never uploaded. This branch does not alter main or the Render deployment.
The optional personal-key form reuses the existing temporary console credential
store, never browser persistence or SQLite. Production/public demo access continues
to require an authorized session; setting only a provider key never enables public spending.

## Data and API contract

The existing Ryan planner remains independent. The yard assistant does not invent a
physical mapping between that feed and the LA/Rotterdam seed. It reads the selected
container and current run from SQLite under one consistent snapshot.

`POST /api/yard/ports/{port}/advisories` requires:

- The yard workspace's HttpOnly cookie and `X-Yard-Request: 1`.
- An authorized `X-Console-Token`, obtained through the existing console connection.
- The current quoted yard ETag in `If-Match` and a unique `Idempotency-Key`.
- JSON `{ "containerId": "SIMU…", "issue": "temperature", "question": "…" }`.

The question is optional, limited to 800 characters. Extra fields, client-supplied
facts, foreign/departed containers, and inactive issues are rejected. The server
builds nine numbered facts from the current container, location, scenario, independent
exceptions, observations, deterministic assessment and recorded task stages. Only
this narrow context and the optional question are sent to Claude; the full inventory,
workspace capability, access code, prior operator notes and provider key are not part
of the prompt. Provider authentication is sent only in its authorization header.

The endpoint returns a persisted `running` job with HTTP 202. Read it using
`GET /api/yard/ports/{port}/advisories/{id}`. Reload/reselection restores the latest
job from `GET /api/yard/ports/{port}/advisories?container_id=…&issue=…`.
Drafts are scoped by workspace, port and run. SQLite schema version 2 adds the
advisory table without discarding version-1 inventory or workflow evidence.

The provider adapter makes exactly one non-streaming request to the fixed
`https://api.anthropic.com/v1/messages` destination. A forced formatting tool returns
structured advisory text; it executes no operational tool. The request has a
25-second HTTP timeout, 5-second connection timeout, 1,800 output-token cap,
64,000-byte response cap, no redirects, no environment proxy and no SDK/transport retries.
English and Dutch outputs follow the selected port. Tool output is validated for
shape, lengths, recognized fact references, container identity, single-line subject,
and accidental credential inclusion. Recipient role and escalation level are supplied
by the server, never selected by the model. Urgent/important exceptions use
`supervisor_now`; otherwise they use `responsible_team`. These are demo policies,
not a certified emergency SOP.

## Reliability and authority

- Repeating the same key/body/ETag returns the same durable job without another paid
  request. Reusing a key for different input is rejected. A lost response is recovered
  through the latest-job read; **Check the same request** reuses the original intent.
- Reads and completed drafts survive restarts. Unfinished jobs are marked interrupted
  on startup and never automatically resubmitted to Claude.
- Any changed run/revision marks an old draft stale. The UI retains it for inspection
  but disables copying until the operator generates a current draft. This conservative
  invalidation includes unrelated changes in the same yard run.
- The existing console gate, 15-minute key authorization, 4 requests/minute,
  12 model jobs/session, 24 model jobs/IP/hour and two concurrent model slots are
  shared with the original planner. Each yard workspace stores up to 24 advisory jobs.
- Provider failures, quota/format errors and truncation produce a failed job with a
  sanitized message. No template is mislabeled as a successful Claude response.
- Generating a draft does not alter the yard revision, task stage, exception,
  clearance or gate-out. Nothing is emailed, released or physically controlled.
  Generated prose can still be wrong and requires operator review. Evidence IDs
  identify supplied facts; they do not prove every generated statement follows from them.
- SQLite is for a single service instance with a persistent filesystem. The storage
  restrictions in [yard-backend.md](yard-backend.md) still apply.

References: [Claude Messages API](https://platform.claude.com/docs/en/api/messages/create),
[tool-use formatting](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use).

## Validation

Tests cover scoped context, explicit invocation, no mutation of inventory,
independent restrictions, exact retries, duplicate concurrent submissions, sanitized
failures, persisted/restarted jobs, stale inputs, workspace/port isolation, Dutch
context, shared model budgets, provider response validation, revoked access,
and frontend transport/freshness handling. Provider tests use mocks and make no
paid requests. Live Claude output remains unverified until a user connects and
explicitly generates a draft.

Validation for this change: **194 backend tests, 47 frontend tests and the production
build passed**. Browser checks confirmed the unconnected generation button is disabled,
the connection panel opens, Dutch labels follow Rotterdam, and the saved inventory
survived the schema upgrade. No live Claude call was made for this validation.
