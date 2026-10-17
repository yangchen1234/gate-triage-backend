"""Non-destructive smoke checks against a running local workbench.

Creates its own synthetic workspace. Tokens remain in process memory and are
never printed. This is also a reproducible check of the real PostgreSQL path.
"""
from __future__ import annotations

import argparse
import time
import uuid

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8088")
    args = parser.parse_args()
    with httpx.Client(base_url=args.url + "/api/v1", timeout=30) as client:
        ready = client.get("/health/ready")
        ready.raise_for_status()
        assert ready.json()["data"]["database"] == "postgresql", "Run this check with PostgreSQL configured"
        create_key = str(uuid.uuid4())
        body = {"name": "Automated integration rehearsal", "mode": "SIMULATION", "scenario_id": "battery_truck_access_2024", "seed": 17}
        response = client.post("/workspaces", json=body, headers={"Idempotency-Key": create_key})
        response.raise_for_status()
        workspace = response.json()["data"]
        path = "/workspaces/" + workspace["id"]
        auth = {"X-Workspace-Token": workspace["token"]}

        def read():
            r = client.get(path, headers=auth)
            r.raise_for_status()
            return r.json()["data"]

        def post(suffix, command):
            current = read()
            headers = {**auth, "If-Match": str(current["revision"]), "Idempotency-Key": str(uuid.uuid4())}
            r = client.post(path + suffix, json=command, headers=headers)
            r.raise_for_status()
            return r, headers

        assert client.get(path, headers={"X-Workspace-Token": "invalid"}).status_code == 404
        result, headers = post("/commands", {"command": "advance", "minutes": 15})
        repeat = client.post(path + "/commands", json={"command": "advance", "minutes": 15}, headers=headers)
        assert repeat.status_code == 200 and repeat.json() == result.json()
        assert read()["snapshot"]["clock_min"] == 15
        stale = client.post(path + "/commands", json={"command": "incident", "status": "closed"}, headers={**headers, "Idempotency-Key": str(uuid.uuid4())})
        assert stale.status_code == 412
        print("PASS PostgreSQL, token isolation, committed retry receipt, revision conflict")

        hero_before = next(c for c in read()["snapshot"]["containers"] if c["container_id"] == "TRXU7731902")
        response, _ = post("/requests", {"title": "Verify independent blockers", "owner_role": "terminal_operations", "service_kind": "readiness_review", "comment": "Integration rehearsal only", "container_ids": ["TRXU7731902"]})
        request_id = response.json()["data"]["id"]
        revision = read()["revision"]
        resolved = client.patch(path + "/requests/" + request_id, json={"status": "resolved"}, headers={**auth, "If-Match": str(revision), "Idempotency-Key": str(uuid.uuid4())})
        resolved.raise_for_status()
        stored = client.get(path + "/requests", headers=auth).json()["data"]["items"]
        assert stored[0]["status"] == "resolved"
        hero_after = next(c for c in read()["snapshot"]["containers"] if c["container_id"] == "TRXU7731902")
        assert hero_before["departure"] == hero_after["departure"]
        print("PASS persistent internal request lifecycle without changing departure facts")

        post("/commands", {"command": "evidence", "container_id": "TRXU7731902", "kind": "provider", "values": {"pickup_lfd": "2026-10-18", "fees_at_pod_terminal": [{"name": "Synthetic fee", "amount": 75, "currency": "USD"}]}})
        updated = next(c for c in read()["snapshot"]["containers"] if c["container_id"] == "TRXU7731902")
        assert updated["lfd"] == "2026-10-18" and updated["fees"][0]["amount"] == 75
        assert "Reported customs hold remains in effect" in updated["departure"]["reasons"]
        print("PASS realtime provider deadline/fee update retains independent customs hold")

        # Read the actual authenticated event stream, then create another revision.
        with client.stream("GET", path + "/stream", headers=auth, timeout=10) as stream:
            stream.raise_for_status()
            data_events = 0
            for line in stream.iter_lines():
                if line.startswith("data:"):
                    data_events += 1
                    if data_events == 1:
                        post("/commands", {"command": "feed", "action": "duplicate"})
                    if data_events == 2:
                        break
        print("PASS authenticated SSE revision push")

        post("/playback", {"playing": True, "speed": 5, "tick_minutes": 1, "strategy": "optimized", "profile": "balanced"})
        time.sleep(1.2)
        # A live clock can win a revision race; reread rather than overwrite it.
        for attempt in range(5):
            try:
                post("/playback", {"playing": False, "speed": 5, "tick_minutes": 1})
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 412 or attempt == 4:
                    raise
        stopped = read()
        assert stopped["snapshot"]["clock_min"] > 15
        time.sleep(.5)
        assert read()["snapshot"]["clock_min"] == stopped["snapshot"]["clock_min"]
        print("PASS durable server clock, live advance and pause")

        response, _ = post("/plan-jobs", {"profile": "balanced", "strategy": "optimized"})
        job_id = response.json()["data"]["id"]
        for _ in range(100):
            job = client.get(path + "/jobs/" + job_id, headers=auth).json()["data"]
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(.1)
        assert job["status"] == "succeeded", job.get("error")
        assert job["result"]["validation"]["valid"]
        print("PASS durable job and independently validated CP-SAT plan")
        search = client.get("/knowledge/search", params={"q": "customs hold"}).json()["data"]
        assert not search["llm_used"] and search["items"]
        print("PASS inspectable local source retrieval (no LLM)")


if __name__ == "__main__":
    main()
