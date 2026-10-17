"""Regression coverage for asynchronous explanations and smoke-test cleanup."""

from copy import deepcopy

import pytest

from scripts import smoke_api as smoke


def fake_api(monkeypatch, *, restore_fails=False):
    original = {"lanes_open": 3, "customs_online": False, "power_zone_b": True}
    state = deepcopy(original)
    posts = []
    reads = []
    row = {"container_id": "BOX?A#B", "priority": 0.8, "action": "inspect"}

    def get(path):
        reads.append(path)
        if path == "/health":
            return 200, {"status": "ok", "scenario": deepcopy(state)}
        if path == "/containers":
            return 200, [{**row, "reason": "Cloud explanation", "reason_source": "cloud",
                          "rule_reason": "Rule explanation"}]
        if path.startswith("/containers/"):
            return 200, {**row, "reason": "Newer cloud explanation", "reason_source": "cloud",
                         "rule_reason": "Rule explanation"}
        if path == "/stats":
            return 200, {"release": 0, "slow": 0, "inspect": 1, "reroute": 0,
                         **dict.fromkeys(smoke.REQUIRED_STATS_NUMERIC, 0)}
        raise AssertionError("Unexpected test request")

    def post(path, patch):
        assert path == "/scenario"
        posts.append(deepcopy(patch))
        if restore_fails and patch == original:
            return 503, {}
        state.update(patch)
        return 200, [{**row, "reason": "Rule explanation", "reason_source": "scorer"}]

    monkeypatch.setattr(smoke, "get", get)
    monkeypatch.setattr(smoke, "post", post)
    monkeypatch.setattr(smoke, "BASE_URL", "http://localhost:8000")
    return original, state, posts, reads


def test_cloud_text_changes_are_accepted_and_id_is_path_quoted(monkeypatch, capsys):
    original, state, posts, reads = fake_api(monkeypatch)
    smoke.run()
    assert "SMOKE TEST PASSED" in capsys.readouterr().out
    assert state == original
    assert posts[-1] == original
    assert "/containers/BOX%3FA%23B" in reads


def test_restore_failure_never_reports_success(monkeypatch, capsys):
    fake_api(monkeypatch, restore_fails=True)
    with pytest.raises(smoke.SmokeError, match="Restore POST /scenario"):
        smoke.run()
    assert "SMOKE TEST PASSED" not in capsys.readouterr().out


def test_restore_failure_preserves_original_failure(monkeypatch, capsys):
    fake_api(monkeypatch, restore_fails=True)

    def fail_queue():
        raise smoke.SmokeError("Original queue failure")

    monkeypatch.setattr(smoke, "check_containers", fail_queue)
    with pytest.raises(smoke.SmokeError, match="Original queue failure"):
        smoke.run()
    output = capsys.readouterr()
    assert "RESTORE FAILED" in output.err
    assert "SMOKE TEST PASSED" not in output.out


@pytest.mark.parametrize("url", [
    "https://user:secret@example.com", "https://example.com?token=secret",
    "https://example.com#token", "file:///tmp/api", "https://example.com:bad",
])
def test_base_url_rejects_credentials_and_request_arguments(url):
    with pytest.raises(smoke.SmokeError):
        smoke.validate_base_url(url)


@pytest.mark.parametrize("row", [
    None, {"container_id": "A", "priority": float("nan"), "action": "release"},
    {"container_id": "A", "priority": 1.1, "action": "release"},
    {"container_id": "A", "priority": 0.5, "action": "unknown"},
    {"container_id": "", "priority": 0.5, "action": "release"},
])
def test_queue_validation_rejects_malformed_rows(row):
    with pytest.raises(smoke.SmokeError):
        smoke.assert_queue([row], "test")
