# Three-port console and agent contract

This release adapts the existing Workbench interface to Ryan's scoring dataset and planner. It deliberately does not deploy the separate PostgreSQL Workbench, time-stepped simulator, port-scale generator, or Los Angeles map extension.

## What is being demonstrated

The 100 synthetic source records are re-evaluated under the LAX, SHA, or RTM profile. This is a three-port what-if comparison of one cohort, not live coverage of three ports. Currency, free-time assumptions, modeled fees, agency names, and draft language come from `gate_triage/port_profiles.py`. Terminal49 is not connected.

The worklist exposes source observations and advisory actions. A `release` recommendation is not a customs authorization, verified appointment, physical gate departure, or executed throughput. Customs outages require clearance verification. Independent holds remain in force.

Queue fee statistics and planner counterfactuals answer different questions. Queue statistics allocate a simplified daily capacity to the ranked list. The agent separately tests whether fixing one blocker could move that container into the modeled release capacity. Summing independent fixes does not establish a jointly feasible schedule or realized financial savings.

## Browser workflow

1. Open `/`. The console creates an isolated session and reads its queue. It never changes the legacy shared `/scenario`.
2. Select Los Angeles, Shanghai, or Rotterdam. Scenario controls change lanes, customs availability, and Zone B power only in this session.
3. Search or filter the worklist and inspect a container's source evidence.
4. Open **Action assistant**. Generate a rules-only plan first. No paid API is called on page load, refresh, polling, or port changes.
5. The service owner configures `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, and `CONSOLE_TEAM_ACCESS_CODE` in Render Environment, then saves and deploys. In **Connection settings**, teammates enter only the private team access code to authorize this session. The API key remains on Render. A personal session-only key is available as an advanced alternative. Configuration does not prove model access until generation succeeds.
6. Choose Claude and explicitly generate a plan. The browser polls the existing job; it does not create another paid generation for each poll.
7. Inspect the deterministic before/after estimates, model/tool trace, model mode, and draft. Approve or reject an action with an optional note. The application never sends the draft, removes a hold, or controls equipment.
8. Change the port or scenario. Prior plans remain inspectable but are stale and cannot be approved.
9. Disconnect Claude to revoke this session's shared-model access or remove its personal key. Render's environment key remains on Render until the owner changes it. An already-running provider request may complete; disconnecting cannot unsend data already transmitted.

## Session and credential boundaries

The browser stores only its opaque console token in `sessionStorage`, never a Claude key or team access code. In shared mode, the key/model/team code come from Render Environment; all three must be valid before the connection is available. The private team code is checked with a constant-time comparison and attempt limits. Authorization lasts 15 minutes within the current session. Only job dispatch reads the server-held key. Neither the key nor access code is returned in API responses or saved in a plan, trace, public error, or Git.

For an optional personal key, the browser submits it once over the same-origin connection and the backend keeps it in this expiring session's memory. Use HTTPS outside localhost and a project-specific Anthropic key with a provider-side spend cap. A team access code is not an individual identity or an organizational role system; share it only with people permitted to consume the team's model budget.

Sessions, per-session authorizations, personal keys, and approval records are volatile. Restart, redeploy, or session expiry resets them. Render's saved environment configuration persists across deployments, so an authorized teammate can create a new session and re-enter the team code. This is not the PostgreSQL persistence supplied by the separate Workbench branch. Run one application instance and one Uvicorn worker. Cross-instance session routing and organizational user accounts are outside this release.

Calls are authenticated with `X-Console-Token`. A token grants access to its own session and must be treated as a credential. Scenario revision checks reject stale writes; idempotency keys prevent duplicate plan dispatch. The service bounds session creation, concurrent model jobs, model requests, output tokens, and request timeouts. These controls reduce abuse; provider-side spend caps remain necessary because application request limits are not exact currency budgets.

The allowed provider endpoint is Anthropic's official HTTPS API. The browser cannot supply a base URL. The current compatibility adapter omits unsupported sampling/JSON-mode parameters and validates returned content. Tool names and arguments are bounded; deterministic calculations select the final action list. Provider failures yield clearly labeled deterministic/template fallback with sanitized errors.

## Agent API flow

All console endpoints use `/api/console`. Request and response schemas are available in `/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /ports` | Public three-port metadata and simulation notice |
| `POST /session` | Create isolated queue/session and receive its token once |
| `GET /session` | Read the current session, queue, scenario, and model metadata |
| `DELETE /session` | Disconnect and close this session |
| `POST /scenario` | Change the session's scenario with `If-Match` |
| `PUT /agent/config` | Configure a session-only Claude key/model; never echoes the key |
| `PUT /agent/team` | Authorize this session to use Render's model with `{access_code}` |
| `DELETE /agent/config` | Revoke this session's authorization or remove its personal key |
| `POST /plans` | Explicitly dispatch one plan; requires revision and idempotency key |
| `GET /plans` | List saved plan jobs in this session |
| `GET /plans/{id}` | Poll one existing job and inspect its result |
| `POST /plans/{id}/decisions` | Record a current plan's internal approval or rejection |

For authenticated operations, send the token returned by `POST /session` as `X-Console-Token`. Send the current revision in `If-Match` for scenario mutations and plan/decision writes. For plan creation, generate an `Idempotency-Key` UUID once and retain it for a retry of that same request. Poll the returned ID rather than resubmitting the operation. A changed scenario requires a new plan.

Legacy `/containers`, `/scenario`, `/stats`, `/health`, `/plan`, and approval routes are retained for the team's existing clients. Public legacy `GET /plan` is rules-only even if model environment variables are configured; it does not spend a shared deployment key. The legacy scenario and approvals remain shared process-memory data and are not used by the new console.

## Deployment

The Dockerfile builds the React frontend with Node/pnpm, then copies only its compiled output into the Python runtime. `main:app` serves both frontend and API on Render's `$PORT`. No new database, paid service, or model credential is required for rules-only operation. Render follows `main` with On Commit deployment; wait for a successful deployment before sharing the updated URL.

Keep actual keys and team codes out of `render.yaml`, `.env.example`, issue reports, screenshots, frontend build variables, and GitHub. In Render Environment, add the variable names, let the owner paste the secrets directly, then select **Save, rebuild, and deploy**. Use an exact Claude model ID available to the account. An unset/invalid access code or model fails closed even when a provider key is present. A custom code must contain at least 16 non-whitespace characters.

## Acceptance checks

Backend tests cover legacy compatibility, port-specific scoring, session isolation and expiry, secret-safe validation, authenticated reads/writes, scenario revisions, plan idempotence, bounded dispatch, model fallback, and stale approvals. Frontend tests and TypeScript production builds cover state helpers and request behavior. Browser acceptance covers three-port switching, scenario changes, source inspection, rules plan generation, approval/rejection, stale results, and key configuration/disconnection without a paid request.

Actual Claude generation requires the user's key and available model ID. Stubbed model tests verify adapter behavior; they are not evidence of a successful live Anthropic request or a guaranteed API bill.
