"""Release integration checks: the shareable site and legacy API coexist safely."""
from fastapi.testclient import TestClient

import main


def test_public_legacy_plan_never_uses_deployment_model_credentials(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.anthropic.com/v1/")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-do-not-transmit")
    seen = []

    def fake_agent(containers, scenario, top_n=5, *, cfg="would-read-env"):
        seen.append(cfg)
        return {"actions": [], "agent_mode": "deterministic"}

    monkeypatch.setattr("gate_triage.agent.run_agent", fake_agent)
    with TestClient(main.create_app()) as client:
        response = client.get("/plan")
        assert response.status_code == 200
        assert response.json()["agent_mode"] == "deterministic"
        assert seen == [None]
        assert "synthetic-do-not-transmit" not in response.text


def test_static_console_headers_and_api_routes_are_independent(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text('<html><div id="root"></div></html>')
    (assets / "release-test.js").write_text("export const release = true;")
    monkeypatch.setattr(main, "WEB_DIST", dist)
    with TestClient(main.create_app()) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="root"' in page.text
        assert page.headers["cache-control"] == "no-store"
        assert "connect-src 'self'" in page.headers["content-security-policy"]
        assert page.headers["x-content-type-options"] == "nosniff"
        asset = client.get("/assets/release-test.js")
        assert asset.status_code == 200
        assert "immutable" in asset.headers["cache-control"]
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/unknown-api-route").status_code == 404


def test_missing_web_build_does_not_break_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "WEB_DIST", tmp_path / "not-built")
    with TestClient(main.create_app()) as client:
        assert client.get("/").status_code == 503
        assert client.get("/health").status_code == 200
