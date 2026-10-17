# Gate Triage

Gate Triage is a Ports & Logistics hackathon prototype for terminal planners. When carrier declarations, scale readings, customs records and reefer sensors disagree, it ranks containers and recommends `release`, `slow`, `inspect` or `reroute` actions for human review. Scenario switches show how the queue changes when lanes close, customs systems go offline or Zone B loses power.

The web console now adapts the existing Workbench design to Ryan's 100-container dataset and planner. Switch among **Los Angeles (LAX), Shanghai (SHA), and Rotterdam (RTM)**, inspect source evidence, generate a plan, and review draft outreach before recording an internal decision. Each browser session has its own scenario. The separate PostgreSQL Workbench, map, and time-stepped simulation remain outside this release.

- **Repository:** <https://github.com/yangchen1234/gate-triage-backend>
- **Hosted API:** <https://gate-triage-backend.onrender.com>
- **Web console:** <https://gate-triage-backend.onrender.com/>
- **Interactive API documentation:** <https://gate-triage-backend.onrender.com/docs>
- **Frontend examples:** [JavaScript and curl guide](docs/api-usage.md)
- **Where the money figures come from:** [Tariff assumptions](docs/tariff-assumptions.md) — one example public tariff per port, what it covers and what it does not. Also returned as `tariff_basis` / `data_note` on `/plan` and in every `decision_trace`.

The repository includes Ryan's scoring engine and **100 synthetic containers**, re-evaluated under three port profiles. These are what-if configurations of one dataset, not live containers in three ports. It does not use live Terminal49 data or execute real port operations. Rules-only mode works without a key. For a shared team Claude connection, the service owner sets `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, and a private `CONSOLE_TEAM_ACCESS_CODE` in **Render → Environment**. Teammates enter only that access code in the web console; the API key never enters the browser. All three values are required, and a key alone does not enable public model use. Per-session personal keys remain an advanced option. Configuration is not a live model-access check; generation reports the actual mode and any fallback. See the [agent and credential contract](docs/agent-console.md).

## Run locally

Use Python 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

Open <http://localhost:8000/docs> to try the endpoints. Run the automated tests with:

```bash
python -m pytest -q
```

To build the web console (Node 24 and pnpm 11.25.0):

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm build
```

Start the Python server from the repository root as above and open <http://localhost:8000/>. For a full production-equivalent build, use `docker build -t gate-triage .` then `docker run --rm -p 127.0.0.1:8000:8000 gate-triage`.

With the server running, verify the real HTTP flow using the smoke-test CLI originally implemented by IBM Bob:

```bash
python scripts/smoke_api.py http://127.0.0.1:8000
```

The script checks the endpoints, all four scenario presets, queue ordering, action counts and the fee calculation. It temporarily changes the shared scenario and restores the original state afterward. A failed restoration also makes the check fail.

## API contract

| Method | Path | Response |
|---|---|---|
| `GET` | `/containers` | Container array, sorted by descending `priority` |
| `GET` | `/containers/{container_id}` | Full container with source evidence and explanations; `404` if missing |
| `POST` | `/scenario` | Merge scenario fields, rescore and return the new container array |
| `GET` | `/stats` | Action counts, FIFO and priority-queue fees, savings and current scenario |
| `GET` | `/health` | Status, scorer, container count, scoring time and explanation mode |
| `GET` | `/plan` | Legacy rules-only action list, independent single-fix estimates, and draft outreach |
| `POST` | `/plan/approve` | Legacy shared in-memory decision; no message is sent |
| `GET` | `/plan/approvals` | Legacy shared decisions |

The web console uses isolated authenticated endpoints under `/api/console`, not the legacy shared scenario. Create a session, authorize its team connection or configure an optional personal key, explicitly dispatch a plan, poll the returned job, then record a decision. See [the full flow](docs/agent-console.md#agent-api-flow) and `/docs`. Model calls require a console token, an authorized team connection or personal session key, an explicit generation request, and the current revision. Page refresh and job polling do not trigger new model calls.

Container records retain their original data fields, including `container_id`, `cargo_type`, `consignee_type`, `sources`, `demurrage_usd_per_day`, `free_days_left`, `zone` and `arrived_at`. The scorer adds source `trust` values and the fields `priority`, `urgency`, `conflict_score`, `action` and `reason`. Scores range from 0 to 1. Non-refrigerated containers have `sources.reefer: null`.

The default scenario is:

```json
{"lanes_open":8,"customs_online":true,"power_zone_b":true}
```

`POST /scenario` accepts partial updates. Sending `{"lanes_open":4}` preserves the current customs and power settings. Send all three default values to reset the scenario. `lanes_open` must be an integer from 0 to 8; the other fields must be JSON booleans. Unknown fields, explicit `null` values and invalid types return `422`. If rescoring fails, the API returns `503` and preserves the previous scenario, queue and statistics.

| Demo preset | `lanes_open` | `customs_online` | `power_zone_b` |
|---|---:|---|---|
| Normal | 8 | `true` | `true` |
| Lanes −50% | 4 | `true` | `true` |
| Customs down | 8 | `false` | `true` |
| Zone B power out | 8 | `true` | `false` |

Use complete presets for mutually exclusive buttons, or partial updates for switches that can be combined.

```bash
curl http://localhost:8000/health
curl http://localhost:8000/containers
curl -X POST http://localhost:8000/scenario \
  -H 'Content-Type: application/json' \
  -d '{"lanes_open":4,"customs_online":true,"power_zone_b":true}'
curl http://localhost:8000/stats
```

Replace `http://localhost:8000` with the hosted API URL for frontend integration. Refresh `/stats` after changing a scenario. See the [frontend guide](docs/api-usage.md) for React and JavaScript examples.

## Scoring and fee simulation

The default scorer is `gate_triage.score:score`, contributed by Ryan. It distinguishes conflicting source reports from individual warning signals, calculates source trust and urgency, then assigns a priority and advisory action. Normal-day weights emphasize cost and overdue containers; disruption weights emphasize cargo criticality, consignee needs and refrigeration risks.

When customs is offline, the engine waits for clearance verification before recommending gate release. It can still recommend an onsite move to powered storage for an unheld reefer. Known holds remain blocked, and power-loss warnings stay visible even when a hold or conflict takes precedence.

The `/stats` endpoint compares two queue orders over one day:

- Daily capacity is `lanes_open × CONTAINERS_PER_LANE_PER_DAY`, with 12 containers per lane by default.
- `baseline_demurrage_usd_per_day` sums the daily fees of containers left after serving the FIFO queue, ordered by `arrived_at`.
- `optimized_demurrage_usd_per_day` uses descending `priority` instead.
- `savings_usd_per_day` is baseline minus optimized cost. It may be positive, zero or negative; the priority engine also considers safety and critical cargo.

All four action types participate in this simplified capacity calculation. A simulated processed container is not a customs release authorization. The supplied `demurrage_usd_per_day` value is summed directly; `free_days_left` affects scoring but is not applied as another fee discount. Arrival ties preserve input order, and dates without time zones are interpreted as UTC.

These are synthetic scenario estimates, not measured savings or validated operational forecasts. The calculation does not model every restriction of a real terminal.

Amounts depend on the selected port profile, scoring version, and scenario. The console shows modeled queue fees separately from the agent's independent single-fix estimates. Neither number proves jointly feasible departures or realized savings. Profile tariffs and approximate FX are synthetic demonstration assumptions, not live quotes or an actual port invoice.

## Configuration and extensions

The app reads environment variables at startup. It does **not** automatically load `.env`; export variables in your shell or set them in the deployment platform. See [.env.example](.env.example). Keep API keys in local environment variables or deployment secrets, and never commit them.

| Variable | Default | Purpose |
|---|---|---|
| `CONTAINERS_FILE` | `data/containers.json` in this repository | JSON array loaded at startup |
| `SCORER` | `gate_triage.score:score` | Synchronous `score(container, scenario)` callable |
| `CONTAINERS_PER_LANE_PER_DAY` | `12` | Daily capacity per open lane |
| `CORS_ORIGINS` | `*` | Comma-separated frontend origins |
| `CLOUD_REASONER` | Unset | Optional `module:explain_many` callable |
| `LLM_REASON_LIMIT` | `20` | Number of top-ranked containers to explain, from 1 to 20 |

To replace the dataset, set `CONTAINERS_FILE` and restart the service. Each record needs a unique, non-empty `container_id`, an ISO 8601 `arrived_at` and a non-negative numeric `demurrage_usd_per_day`, plus the fields required by the selected scorer. Preserve the source schema when integrating with the frontend.

A replacement scorer may return only computed fields or a complete container. The API merges the result with the original record, preserving fields the scorer does not return. It must preserve `container_id`, return finite scores between 0 and 1, a supported action and a non-empty reason. GET requests read cached results; scenario updates rescore the dataset atomically.

### Optional cloud explanations

No legacy `CLOUD_REASONER` adapter or credentials are included. This optional extension is separate from the console's session-scoped Claude planner. To connect a protected legacy explanation service, implement a synchronous `explain_many(containers, scenario)` function and set `CLOUD_REASONER=your_module:explain_many`. The adapter owns authentication, request timeouts, retries and cost limits. It must return `{container_id: explanation}` for every selected container; each explanation must be non-empty and at most 2,000 characters.

The API returns the scorer's explanations immediately, then enriches only the top-ranked containers in the background. Cloud output can change explanation text, but cannot change actions or rankings. The original text is retained as `rule_reason`; stale results from an earlier scenario are discarded. On failure, the API keeps the scoring explanations.

`/health` reports the actual state:

- `llm: "template"` when no cloud explanation is available; `llm: "cloud"` after successful enrichment.
- `llm_status`: `disabled`, `pending`, `ready` or `fallback`.
- `llm_configured`: whether an explanation callable was loaded.

Frontend code must support template mode and cloud fallback. There is no built-in Ollama adapter. See the [integration guide](docs/integration.md) for the callable contracts.

## Deployment

The hosted demo runs on Render at <https://gate-triage-backend.onrender.com>. The service is connected to GitHub and follows `main` with **On Commit** automatic builds and deployments. Confirm the new deployment is live before relying on its data or behavior.

The repository includes a [Dockerfile](Dockerfile) and [Render Blueprint](render.yaml). The Blueprint requests a free instance, listens on `0.0.0.0:$PORT` and uses `/health` for health checks. The same Dockerfile can be used with another compatible hosting platform.

Render's free service may sleep while idle. Open `/health` before the demo and allow time for it to wake up. See [Render's free service documentation](https://render.com/docs/free).

Run **one worker and one instance**. The new web console has isolated expiring process-memory sessions; its keys, scenarios, jobs, and decisions reset on restart or redeployment. Legacy endpoints retain their shared process-memory scenario and approvals. Durable storage and multi-instance session routing are outside this release. The independent local Workbench branch retains its PostgreSQL implementation.

CORS allows all origins by default, with credentials disabled. Set `CORS_ORIGINS` to restrict legacy frontend origins. New console operations require `X-Console-Token`; CORS is not authentication. Legacy scenario writes remain public, so existing legacy clients share state. Public `GET /plan` is rules-only and never uses a deployment's model key. Do not enable a paid legacy `CLOUD_REASONER` on the public demo without separately protecting the legacy routes.

After deployment, run:

```bash
python scripts/smoke_api.py https://gate-triage-backend.onrender.com
```

Run this before recording or presenting: it temporarily changes the shared scenario while exercising the four presets.

## Team workflow

```bash
git clone https://github.com/yangchen1234/gate-triage-backend.git
cd gate-triage-backend
```

The repository is public and can be shared directly with teammates. For push access, invite each teammate through **Settings → Collaborators → Add people**; they must accept the invitation. Use separate branches and pull requests to coordinate changes. The frontend can be deployed separately and configured with the backend base URL.

## Contributions and responsible use

Ryan contributed the dataset and current scoring engine. Codex assisted with API implementation, service integration, fee statistics, deployment configuration, testing and documentation. IBM Bob's IDE agent originally implemented `scripts/smoke_api.py`; Codex subsequently reviewed it, corrected asynchronous explanation comparisons and scenario restoration handling, and added regression coverage. The [IBM Bob record](docs/ibm-bob.md) documents that contribution.

Gate Triage provides recommendations and a synthetic simulation for human review. It does not clear customs holds, authorize physical container release or control terminal equipment. Source evidence and rule explanations remain available to support review. Live Terminal49 integration and real operational validation are future work.
