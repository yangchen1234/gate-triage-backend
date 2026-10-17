#!/usr/bin/env python3
"""Deployment smoke-test for the Gate Triage API.

Usage:
    python scripts/smoke_api.py [BASE_URL]

Exits 0 on full pass, nonzero on any failure.
Standard library only; no third-party dependencies required.
"""

import json
import math
import sys
import urllib.request
import urllib.error
from urllib.request import Request
from urllib.parse import quote, urlsplit

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 5  # seconds

SCENARIO_PRESETS = [
    ("Normal",             {"lanes_open": 8, "customs_online": True, "power_zone_b": True}),
    ("Lanes -50%",         {"lanes_open": 4, "customs_online": True, "power_zone_b": True}),
    ("Customs down",       {"lanes_open": 8, "customs_online": False, "power_zone_b": True}),
    ("Zone B power out",   {"lanes_open": 8, "customs_online": True, "power_zone_b": False}),
]

REQUIRED_STATS_NUMERIC = (
    "baseline_demurrage_usd_per_day",
    "optimized_demurrage_usd_per_day",
    "savings_usd_per_day",
)

STATS_ACTION_KEYS = ("release", "slow", "inspect", "reroute")
EXPLANATION_FIELDS = {"reason", "reason_source", "rule_reason"}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def validate_base_url(value: str) -> str:
    """Accept an HTTP(S) service URL without secrets or request arguments."""
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme in {"http", "https"} and bool(parts.hostname)
            and parts.username is None and parts.password is None
            and "?" not in value and "#" not in value
            and not any(char.isspace() or ord(char) < 32 for char in value)
        )
        # Accessing port also rejects malformed or out-of-range ports.
        parts.port
    except ValueError:
        valid = False
    expect(valid, "BASE_URL must be an HTTP(S) URL without credentials, query or fragment")
    return value.rstrip("/")


def _request(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    """Return (status_code, parsed_json). Raises SmokeError on network/TLS problems."""
    url = BASE_URL + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        # HTTPError is a valid HTTP response (4xx/5xx); parse it.
        try:
            payload = json.loads(exc.read().decode())
        except Exception:
            payload = None
        return exc.code, payload
    except urllib.error.URLError:
        raise SmokeError(f"{method} request failed: network or TLS error") from None
    except Exception:
        raise SmokeError(f"{method} request failed: invalid response or transport error") from None


def get(path: str) -> tuple[int, object]:
    return _request("GET", path)


def post(path: str, body: dict) -> tuple[int, object]:
    return _request("POST", path, body)


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

class SmokeError(Exception):
    """Non-zero exit with a concise message; no raw provider text."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def expect_status(actual: int, expected: int, context: str) -> None:
    expect(actual == expected, f"{context}: expected HTTP {expected}, got {actual}")


def assert_queue(queue: object, context: str) -> list:
    """Validate queue is a non-empty list with descending priorities."""
    expect(isinstance(queue, list), f"{context}: response must be a JSON array")
    expect(len(queue) > 0, f"{context}: queue must not be empty")
    priorities = []
    seen_ids = set()
    for row in queue:
        expect(isinstance(row, dict), f"{context}: every item must be a JSON object")
        identifier = row.get("container_id")
        expect(isinstance(identifier, str) and bool(identifier.strip()),
               f"{context}: every item must have a non-empty container_id")
        expect(identifier not in seen_ids, f"{context}: container_id values must be unique")
        seen_ids.add(identifier)
        expect(row.get("action") in STATS_ACTION_KEYS,
               f"{context}: every item must have a valid action")
        p = row.get("priority")
        expect(
            isinstance(p, (int, float)) and not isinstance(p, bool)
            and 0 <= p <= 1 and math.isfinite(p),
            f"{context}: every priority must be a finite number between 0 and 1",
        )
        priorities.append(p)
    sorted_desc = sorted(priorities, reverse=True)
    expect(
        priorities == sorted_desc,
        f"{context}: priorities are not in descending order: {priorities}",
    )
    return queue


def stable_fields(row: dict) -> dict:
    """Cloud explanation text may change between otherwise identical reads."""
    return {key: value for key, value in row.items() if key not in EXPLANATION_FIELDS}


def assert_stats(stats: object, queue: list, context: str) -> None:
    """Validate action counts, numeric fields, and savings formula."""
    expect(isinstance(stats, dict), f"{context}/stats: expected a JSON object")

    # Action counts must match the queue.
    for action in STATS_ACTION_KEYS:
        expect(action in stats, f"{context}/stats: missing action key '{action}'")
        expect(isinstance(stats[action], int) and not isinstance(stats[action], bool)
               and stats[action] >= 0,
               f"{context}/stats: '{action}' count must be a non-negative integer")
        counted = sum(1 for row in queue if row.get("action") == action)
        expect(
            stats[action] == counted,
            f"{context}/stats: '{action}' count {stats[action]} != queue count {counted}",
        )

    # Required numeric fields must be finite numbers.
    for field in REQUIRED_STATS_NUMERIC:
        expect(field in stats, f"{context}/stats: missing field '{field}'")
        value = stats[field]
        expect(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value),
            f"{context}/stats: '{field}' must be a finite number, got {value!r}",
        )

    # savings == baseline - optimized  (tolerate normal float rounding)
    baseline = stats["baseline_demurrage_usd_per_day"]
    optimized = stats["optimized_demurrage_usd_per_day"]
    savings = stats["savings_usd_per_day"]
    expected_savings = baseline - optimized
    # Use a relative tolerance scaled to the magnitude, with a minimum absolute floor.
    tolerance = max(1e-9, abs(expected_savings) * 1e-9)
    expect(
        abs(savings - expected_savings) <= tolerance,
        (
            f"{context}/stats: savings {savings} != baseline {baseline} - "
            f"optimized {optimized} = {expected_savings}"
        ),
    )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_health() -> None:
    status, body = get("/health")
    expect_status(status, 200, "GET /health")
    expect(isinstance(body, dict), "GET /health: expected a JSON object")
    expect(body.get("status") == "ok", f"GET /health: status != 'ok', got {body.get('status')!r}")
    print("  /health                OK")


def check_containers() -> list:
    status, body = get("/containers")
    expect_status(status, 200, "GET /containers")
    queue = assert_queue(body, "GET /containers")
    print(f"  /containers            OK  ({len(queue)} containers, descending priority)")
    return queue


def check_container_by_id(queue: list) -> None:
    """Spot-check the top-priority container by ID."""
    container_id = queue[0]["container_id"]
    status, body = get(f"/containers/{quote(container_id, safe='')}")
    expect_status(status, 200, f"GET /containers/{container_id}")
    expect(isinstance(body, dict), f"GET /containers/{container_id}: expected a JSON object")
    expect(
        body.get("container_id") == container_id,
        f"GET /containers/{container_id}: container_id mismatch in response",
    )
    # Cloud explanations may complete between the list and detail requests.
    expect(
        stable_fields(body) == stable_fields(queue[0]),
        f"GET /containers/{container_id}: detail does not match the queue entry",
    )
    print(f"  /containers/{{id}}       OK  (id={container_id})")


def check_stats(queue: list, label: str) -> dict:
    status, body = get("/stats")
    expect_status(status, 200, f"GET /stats ({label})")
    assert_stats(body, queue, f"GET /stats ({label})")
    print(f"  /stats                 OK  (savings={body['savings_usd_per_day']})")
    return body


def apply_scenario(label: str, patch: dict) -> list:
    status, body = post("/scenario", patch)
    expect_status(status, 200, f"POST /scenario ({label})")
    queue = assert_queue(body, f"POST /scenario ({label})")
    print(f"  POST /scenario         OK  ({label}: {len(queue)} items, descending priority)")
    return queue


def read_current_scenario() -> dict:
    """Return the current scenario dict from /health."""
    status, body = get("/health")
    expect_status(status, 200, "GET /health (reading current scenario)")
    expect(isinstance(body, dict) and "scenario" in body,
           "GET /health: response missing 'scenario' field")
    scenario = body["scenario"]
    expect(isinstance(scenario, dict),
           f"GET /health: 'scenario' must be an object, got {type(scenario).__name__}")
    lanes = scenario.get("lanes_open")
    expect(isinstance(lanes, int) and not isinstance(lanes, bool) and 0 <= lanes <= 8
           and isinstance(scenario.get("customs_online"), bool)
           and isinstance(scenario.get("power_zone_b"), bool),
           "GET /health: scenario must contain the three valid scenario fields")
    return scenario


def restore_scenario(original: dict) -> None:
    """POST /scenario with exactly the original values (send all three fields)."""
    # Always send all three known fields so we get a full reset regardless of
    # which fields the presets changed.
    patch = {
        k: v for k, v in original.items()
        if k in ("lanes_open", "customs_online", "power_zone_b")
    }
    status, _ = post("/scenario", patch)
    expect_status(status, 200, "Restore POST /scenario")
    restored = read_current_scenario()
    expect(restored == original, "Restore verification failed: scenario differs from its starting state")
    print(f"Scenario restored: {restored}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run() -> None:
    global BASE_URL
    BASE_URL = validate_base_url(BASE_URL)
    print(f"Gate Triage smoke test → {BASE_URL}\n")

    # Read and save the starting scenario before touching anything.
    original_scenario = read_current_scenario()
    print(f"Starting scenario: {original_scenario}\n")

    failure = None
    try:
        # --- Static GET checks -------------------------------------------------
        print("── Static endpoint checks ──────────────────────────────────────")
        check_health()
        queue = check_containers()
        check_container_by_id(queue)
        check_stats(queue, "baseline")
        print()

        # --- Frontend preset scenarios ----------------------------------------
        print("── Scenario preset checks ──────────────────────────────────────")
        for label, patch in SCENARIO_PRESETS:
            new_queue = apply_scenario(label, patch)
            # After each POST /scenario the GET /containers must agree.
            status, live_queue = get("/containers")
            expect_status(status, 200, f"GET /containers after scenario '{label}'")
            live_queue = assert_queue(live_queue, f"GET /containers after scenario '{label}'")
            expect(
                [stable_fields(row) for row in live_queue]
                == [stable_fields(row) for row in new_queue],
                f"Scenario '{label}': POST body and GET /containers disagree",
            )
            # Stats must be consistent with the returned queue.
            check_stats(new_queue, label)
        print()

    except (SmokeError, KeyboardInterrupt) as exc:
        failure = exc
    finally:
        # Always restore, even on failure.
        print("── Restoring original scenario ─────────────────────────────────")
        try:
            restore_scenario(original_scenario)
        except SmokeError as restore_failure:
            if failure is not None:
                print(f"RESTORE FAILED: {restore_failure}", file=sys.stderr)
            else:
                failure = restore_failure

    if failure is not None:
        raise failure

    print("═══════════════════════════════════════════════════════════════════")
    print("SMOKE TEST PASSED")
    print(f"  Checked: /health, /containers, /containers/{{id}}, /stats")
    print(f"  Scenarios: {', '.join(label for label, _ in SCENARIO_PRESETS)}")
    print("═══════════════════════════════════════════════════════════════════")


if __name__ == "__main__":
    try:
        expect(len(sys.argv) <= 2, "Usage: python scripts/smoke_api.py [BASE_URL]")
        if len(sys.argv) == 2:
            BASE_URL = sys.argv[1]
        run()
    except SmokeError as exc:
        print(f"\nSMOKE TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
