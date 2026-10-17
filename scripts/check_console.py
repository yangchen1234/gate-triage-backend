"""Smoke-check an isolated rules-only console session without spending a model key."""
from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def check(base: str) -> dict:
    token = None

    def request(path, method="GET", body=None, revision=None, idem=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Console-Token"] = token
        if revision is not None:
            headers["If-Match"] = str(revision)
        if idem:
            headers["Idempotency-Key"] = idem
        req = Request(base.rstrip("/") + "/api/console" + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
        with urlopen(req, timeout=90) as response:
            assert response.headers["Cache-Control"] == "no-store"
            return json.load(response)

    def completed(job):
        for _ in range(100):
            if job["status"] not in ("queued", "running"):
                assert job["status"] == "succeeded", job.get("error")
                return job
            time.sleep(.1)
            job = request("/plans/" + job["id"])
        raise AssertionError("Rules planner did not finish in time")

    try:
        snapshot = request("/session", "POST")
        token = snapshot.pop("token")
        assert len(snapshot["queue"]) == 100
        assert snapshot["model"]["configured"] is False
        revision = snapshot["revision"]
        ports = []
        for port, currency in [("SHA", "CNY"), ("RTM", "EUR"), ("LAX", "USD")]:
            snapshot = request("/scenario", "POST", {"port": port}, revision)
            revision = snapshot["revision"]
            assert len(snapshot["queue"]) == 100
            assert all(row["currency"] == currency for row in snapshot["queue"])
            assert sum(snapshot["stats"][a] for a in ("release", "slow", "inspect", "reroute")) == 100
            ports.append(port)
        body, idem = {"top_n": 3, "use_model": False}, str(uuid4())
        first = request("/plans", "POST", body, revision, idem)
        retry = request("/plans", "POST", body, revision, idem)
        assert first["id"] == retry["id"]
        job = completed(first)
        assert job["result"]["model_requests"] == 0
        assert job["result"]["agent_mode"] == "deterministic"
        action = job["result"]["actions"][0]
        decision = {"container_id": action["container_id"], "blocker": action["blocker"],
                    "decision": "approved", "note": "Rules-only smoke check in an isolated disposable session."}
        decided = request("/plans/" + job["id"] + "/decisions", "POST", decision, revision)
        assert decided["result"]["actions"][0]["approval"]["status"] == "approved"
        snapshot = request("/scenario", "POST", {"lanes_open": 4}, revision)
        assert request("/plans/" + job["id"])["stale"] is True
        try:
            request("/plans/" + job["id"] + "/decisions", "POST", decision, snapshot["revision"])
            raise AssertionError("Stale approval was accepted")
        except HTTPError as error:
            assert error.code == 409
        return {"checks": "passed", "ports": ports, "containers_per_profile": 100,
                "isolated_session": True, "idempotent_dispatch": True,
                "stale_decision_rejected": True, "model_requests": 0}
    finally:
        if token:
            request("/session", "DELETE")


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"), indent=2))
