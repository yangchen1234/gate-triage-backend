"""API contract, atomic scenario changes, and optional explanation isolation."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
from threading import Event
from time import perf_counter

from fastapi.testclient import TestClient
import pytest

from gate_triage.config import Settings
from gate_triage.score import score
from gate_triage.models import DEFAULT_SCENARIO
from gate_triage.service import QueueService
from main import create_app


@pytest.fixture
def rows():
    source = Path(__file__).resolve().parents[1] / "data" / "containers.json"
    return json.loads(source.read_text(encoding="utf-8"))


@pytest.fixture
def make_settings(tmp_path, rows):
    def make(data=None, **overrides):
        path = tmp_path / "containers.json"
        path.write_text(json.dumps(rows if data is None else data), encoding="utf-8")
        return Settings(containers_file=path, **overrides)

    return make


def expanded_rows(rows, count):
    result = []
    for index in range(count):
        row = deepcopy(rows[index % len(rows)])
        row["container_id"] = f"DEMO{index:07d}"
        result.append(row)
    return result


def assert_ranked(queue):
    assert isinstance(queue, list)
    priorities = [row["priority"] for row in queue]
    assert priorities == sorted(priorities, reverse=True)


def assert_raw_fields_preserved(original, actual):
    """Scoring may enrich source records, but must retain every input field."""
    for field, value in original.items():
        if field == "sources":
            for name, source in value.items():
                if source is None:
                    assert actual[field][name] is None
                else:
                    for key, raw_value in source.items():
                        assert actual[field][name][key] == raw_value
                    assert 0 <= actual[field][name]["trust"] <= 1
        else:
            assert actual[field] == value


def test_frontend_routes_preserve_raw_fields_and_default_statistics(rows, make_settings):
    rows[0]["partner_extension"] = {"reference": "keep-this-field"}
    settings = make_settings(rows)
    with TestClient(create_app(settings)) as client:
        response = client.get("/containers")
        assert response.status_code == 200
        queue = response.json()
        assert_ranked(queue)
        assert len(queue) == len(rows) == 100
        by_id = {row["container_id"]: row for row in queue}
        for original in rows:
            actual = by_id[original["container_id"]]
            assert_raw_fields_preserved(original, actual)
            assert actual["reason"]
            assert all(0 <= actual[field] <= 1 for field in ("priority", "urgency", "conflict_score"))
            detail = client.get(f"/containers/{original['container_id']}")
            assert detail.status_code == 200
            assert detail.json() == actual

        stats = client.get("/stats").json()
        actions = ("release", "slow", "inspect", "reroute")
        assert {action: stats[action] for action in actions} == {
            action: sum(row["action"] == action for row in queue) for action in actions
        }
        assert sum(stats[action] for action in actions) == len(rows)
        assert stats["reroute"] == 0
        assert stats["scenario"] == DEFAULT_SCENARIO
        capacity = DEFAULT_SCENARIO["lanes_open"] * settings.containers_per_lane_per_day
        fifo = sorted(rows, key=lambda row: datetime.fromisoformat(row["arrived_at"]))
        baseline = sum(Decimal(str(row["demurrage_usd_per_day"])) for row in fifo[capacity:])
        optimized = sum(Decimal(str(row["demurrage_usd_per_day"])) for row in queue[capacity:])
        assert Decimal(str(stats["baseline_demurrage_usd_per_day"])) == baseline
        assert Decimal(str(stats["optimized_demurrage_usd_per_day"])) == optimized
        assert Decimal(str(stats["savings_usd_per_day"])) == baseline - optimized
        health = client.get("/health").json()
        assert health["status"] == "ok"
        assert health["container_count"] == len(rows)
        assert health["llm"] == "template"
        assert health["llm_status"] == "disabled"
        assert health["llm_configured"] is False


def test_partial_scenario_updates_merge_current_state_and_return_direct_array(make_settings):
    with TestClient(create_app(make_settings())) as client:
        first = client.post("/scenario", json={"power_zone_b": False})
        assert first.status_code == 200
        assert_ranked(first.json())
        second = client.post("/scenario", json={"lanes_open": 4})
        assert second.status_code == 200
        assert_ranked(second.json())
        assert second.json() == client.get("/containers").json()
        expected = {**DEFAULT_SCENARIO, "lanes_open": 4, "power_zone_b": False}
        assert client.get("/stats").json()["scenario"] == expected
        assert client.get("/health").json()["scenario"] == expected
        assert client.post("/scenario", json={}).json() == second.json()
        assert client.post("/scenario", json={"lanes_open": 0}).status_code == 200
        assert client.get("/stats").json()["scenario"]["lanes_open"] == 0


@pytest.mark.parametrize("patch", [
    {"lanes_open": True}, {"lanes_open": False}, {"lanes_open": 4.0},
    {"lanes_open": 4.5}, {"lanes_open": -1}, {"lanes_open": 9},
    {"lanes_open": "4"}, {"lanes_open": None},
    {"customs_online": 1}, {"customs_online": "false"}, {"customs_online": None},
    {"power_zone_b": 0}, {"power_zone_b": "true"}, {"power_zone_b": None},
    {"unknown_parameter": True},
])
def test_invalid_scenarios_are_rejected_without_changing_state(make_settings, patch):
    app = create_app(make_settings())
    with TestClient(app) as client:
        before = app.state.service.snapshot()
        assert client.post("/scenario", json=patch).status_code == 422
        assert app.state.service.snapshot() == before


def test_not_found_and_cors_allow_frontend_without_credentials(make_settings):
    with TestClient(create_app(make_settings())) as client:
        response = client.get("/containers/does-not-exist")
        assert response.status_code == 404
        assert response.json() == {"detail": "Container not found"}
        preflight = client.options("/scenario", headers={
            "Origin": "https://team-frontend.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "*"
        assert "access-control-allow-credentials" not in preflight.headers
        assert "POST" in preflight.headers["access-control-allow-methods"]


def test_reads_use_cached_scores_and_scenario_update_rescores_once(rows, make_settings):
    calls = []

    def counting_scorer(container, scenario):
        calls.append((container["container_id"], deepcopy(scenario)))
        return score(container, scenario)

    with TestClient(create_app(make_settings(), scorer=counting_scorer)) as client:
        assert len(calls) == len(rows)
        for route in ("/containers", f"/containers/{rows[0]['container_id']}", "/stats", "/health"):
            assert client.get(route).status_code == 200
        assert len(calls) == len(rows)
        assert client.post("/scenario", json={"lanes_open": 4}).status_code == 200
        assert len(calls) == 2 * len(rows)
        assert all(scenario["lanes_open"] == 4 for _, scenario in calls[len(rows):])


def test_mid_batch_scoring_failure_rolls_back_every_visible_state(rows, make_settings):
    def failing_scorer(container, scenario):
        if not scenario["customs_online"] and container["container_id"] == rows[2]["container_id"]:
            raise RuntimeError("provider detail must not leak")
        return score(container, scenario)

    app = create_app(make_settings(), scorer=failing_scorer)
    with TestClient(app) as client:
        before = app.state.service.snapshot()
        response = client.post("/scenario", json={"lanes_open": 4, "customs_online": False})
        assert response.status_code == 503
        assert "provider detail" not in response.text
        assert app.state.service.snapshot() == before
        assert client.get("/containers").json() == before.queue
        assert client.get("/stats").json() == before.stats
        assert client.get("/health").json()["generation"] == before.generation


def test_scorer_inputs_and_returned_snapshots_cannot_mutate_cached_sources(rows, make_settings):
    observations = []

    def mutating_scorer(container, scenario):
        observations.append((deepcopy(container), deepcopy(scenario)))
        result = score(container, scenario)
        container["sources"]["carrier"]["trust"] = -999
        scenario["lanes_open"] = -999
        return result

    service = QueueService(make_settings(), scorer=mutating_scorer)
    untouched = deepcopy(service.snapshot())
    exposed = service.snapshot()
    exposed.queue[0]["sources"]["carrier"]["trust"] = -123
    exposed.scenario["lanes_open"] = -123
    exposed.stats["scenario"]["lanes_open"] = -123
    assert service.snapshot() == untouched
    changes = {"lanes_open": 4}
    service.update(changes)
    assert changes == {"lanes_open": 4}
    assert [item for item, _ in observations] == rows + rows
    assert all(scenario == DEFAULT_SCENARIO for _, scenario in observations[:len(rows)])
    assert all(scenario == {**DEFAULT_SCENARIO, "lanes_open": 4} for _, scenario in observations[len(rows):])
    actual = service.snapshot()
    original_by_id = {row["container_id"]: row for row in rows}
    for row in actual.queue:
        assert_raw_fields_preserved(original_by_id[row["container_id"]], row)
    assert actual.scenario == {**DEFAULT_SCENARIO, "lanes_open": 4}
    assert actual.stats["scenario"] == actual.scenario


def test_one_hundred_container_api_rescore_finishes_within_one_second(rows, make_settings):
    settings = make_settings(expanded_rows(rows, 100))
    with TestClient(create_app(settings)) as client:
        start = perf_counter()
        response = client.post("/scenario", json={"lanes_open": 4, "power_zone_b": False})
        elapsed = perf_counter() - start
        assert response.status_code == 200
        assert len(response.json()) == 100
        assert_ranked(response.json())
        assert elapsed < 1.0, f"100-container update took {elapsed:.3f}s"


def test_concurrent_scenario_writes_preserve_both_partial_changes(make_settings):
    entered, release, second_started = Event(), Event(), Event()

    def blocking_scorer(container, scenario):
        if scenario["lanes_open"] == 4 and scenario["power_zone_b"] and not entered.is_set():
            entered.set()
            assert release.wait(5), "test did not release first scorer"
        return score(container, scenario)

    service = QueueService(make_settings(), scorer=blocking_scorer)

    def second_update():
        second_started.set()
        return service.update({"power_zone_b": False})

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(service.update, {"lanes_open": 4})
        try:
            assert entered.wait(2)
            second = pool.submit(second_update)
            assert second_started.wait(2)
        finally:
            release.set()
        first.result(timeout=5)
        second.result(timeout=5)
    final = service.snapshot()
    assert final.generation == 3
    assert final.scenario == {**DEFAULT_SCENARIO, "lanes_open": 4, "power_zone_b": False}
    assert final.stats["scenario"] == final.scenario


def test_cloud_background_path_enriches_only_top_twenty_without_changing_decisions(rows, make_settings):
    calls = []

    def cloud_reasoner(selected, scenario):
        calls.append([row["container_id"] for row in selected])
        # Provider inputs must be copies: an overeager adapter cannot alter decisions.
        for row in selected:
            row["priority"] = -1
            row["action"] = "untrusted-action"
            row["sources"]["carrier"]["trust"] = -1
        scenario["lanes_open"] = -1
        return {row["container_id"]: f"Cloud explanation for {row['container_id']}" for row in selected}

    settings = make_settings(expanded_rows(rows, 25))
    expected_stats = QueueService(settings).update({"lanes_open": 4}).stats
    app = create_app(settings, reasoner=cloud_reasoner)
    with TestClient(app) as client:
        response = client.post("/scenario", json={"lanes_open": 4})
        assert response.status_code == 200
        before = response.json()
        after = client.get("/containers").json()
        assert calls
        assert all(len(selected) == 20 for selected in calls)
        assert [row["container_id"] for row in before[:20]] in calls
        for index, (original, enriched) in enumerate(zip(before, after, strict=True)):
            for field, value in original.items():
                if field not in {"reason", "reason_source"}:
                    assert enriched[field] == value
            if index < 20:
                assert enriched["reason_source"] == "cloud"
                assert enriched["rule_reason"] == original["reason"]
                assert enriched["reason"].startswith("Cloud explanation")
            else:
                assert enriched == original
        health = client.get("/health").json()
        assert health["llm"] == "cloud"
        assert health["llm_status"] == "ready"
        assert health["llm_configured"] is True
        assert health["scenario"]["lanes_open"] == 4
        assert client.get("/stats").json() == expected_stats


def test_stale_cloud_result_cannot_replace_a_new_scenario(make_settings):
    entered, release = Event(), Event()

    def delayed_reasoner(selected, scenario):
        entered.set()
        assert release.wait(5), "test did not release reasoner"
        return {row["container_id"]: "Explanation for outdated scenario" for row in selected}

    service = QueueService(make_settings(), reasoner=delayed_reasoner)
    with ThreadPoolExecutor(max_workers=1) as pool:
        cloud = pool.submit(service.enrich_reasons, 1)
        try:
            assert entered.wait(2)
            current = service.update({"lanes_open": 4})
        finally:
            release.set()
        cloud.result(timeout=5)
    assert service.snapshot() == current
    assert current.generation == 2
    assert current.llm == "template"
    assert current.llm_status == "pending"


@pytest.mark.parametrize("failure", ["exception", "missing_reason", "empty_reason"])
def test_cloud_failures_keep_rule_reasons_and_report_fallback(make_settings, failure, caplog):
    def bad_reasoner(selected, scenario):
        if failure == "exception":
            raise RuntimeError("secret-provider-token")
        if failure == "missing_reason":
            return {}
        return {row["container_id"]: "" for row in selected}

    service = QueueService(make_settings(), reasoner=bad_reasoner)
    before = service.snapshot()
    service.enrich_reasons(before.generation)
    after = service.snapshot()
    assert after == replace(before, llm="template", llm_status="fallback")
    assert "secret-provider-token" not in caplog.text
