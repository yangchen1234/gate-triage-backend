# Gate Triage Backend

> **Independent full-stack workbench:** see [README-workbench.md](README-workbench.md) for the PostgreSQL-backed web demo, real-time simulation, CP-SAT scheduling and strategy comparisons on `codex/fullstack-simulation-demo`. The legacy API below and the team's hosted deployment remain separate.

Gate Triage is a Ports & Logistics hackathon prototype for terminal planners. When carrier declarations, scale readings, customs records and reefer sensors disagree, it ranks containers and recommends `release`, `slow`, `inspect` or `reroute` actions for human review. Scenario switches show how the queue changes when lanes close, customs systems go offline or Zone B loses power.

- **Repository:** <https://github.com/yangchen1234/gate-triage-backend>
- **Hosted API:** <https://gate-triage-backend.onrender.com>
- **Interactive API documentation:** <https://gate-triage-backend.onrender.com/docs>
- **Frontend examples:** [JavaScript and curl guide](docs/api-usage.md)

The repository now includes Ryan's scoring engine and **100 synthetic containers**. It does not use live Terminal49 data or execute real port operations. Cloud LLM explanations are optional and are not configured by default. A GitHub update does not update the hosted service until a new Render deployment completes; check `/health` for the running container count and scorer.

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

With the current 100-container dataset and default capacity, Normal saves $770/day in the simulation and Lanes −50% saves $4,249/day. The independent Customs down and Zone B power out presets each save $770/day: they change recommendations but do not further reduce lane capacity in this fee model. These values are calculated, not preset targets.

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

No cloud provider adapter or credentials are included. To connect the team's API, implement a synchronous `explain_many(containers, scenario)` function and set `CLOUD_REASONER=your_module:explain_many`. The adapter owns authentication, request timeouts, retries and cost limits. It must return `{container_id: explanation}` for every selected container; each explanation must be non-empty and at most 2,000 characters.

The API returns the scorer's explanations immediately, then enriches only the top-ranked containers in the background. Cloud output can change explanation text, but cannot change actions or rankings. The original text is retained as `rule_reason`; stale results from an earlier scenario are discarded. On failure, the API keeps the scoring explanations.

`/health` reports the actual state:

- `llm: "template"` when no cloud explanation is available; `llm: "cloud"` after successful enrichment.
- `llm_status`: `disabled`, `pending`, `ready` or `fallback`.
- `llm_configured`: whether an explanation callable was loaded.

Frontend code must support template mode and cloud fallback. There is no built-in Ollama adapter. See the [integration guide](docs/integration.md) for the callable contracts.

## Deployment

The hosted demo runs on Render at <https://gate-triage-backend.onrender.com>. This service was connected using the public repository URL; deploy new commits through the Render service's **Manual Deploy** menu. Confirm the new deployment is live before relying on its data or behavior.

The repository includes a [Dockerfile](Dockerfile) and [Render Blueprint](render.yaml). The Blueprint requests a free instance, listens on `0.0.0.0:$PORT` and uses `/health` for health checks. The same Dockerfile can be used with another compatible hosting platform.

Render's free service may sleep while idle. Open `/health` before the demo and allow time for it to wake up. See [Render's free service documentation](https://render.com/docs/free).

Run **one worker and one instance**. The queue and scenario live in process memory, are shared by all visitors and reset on restart or redeployment. Independent demo sessions or multiple instances require session handling and shared storage.

CORS allows all origins by default, with credentials disabled. Set `CORS_ORIGINS` to restrict access to the frontend's origin. The public demo has no scenario authentication, so visitors can change the shared state.

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
