"""End-to-end happy-path test (requires the running stack: make infra-up + app up).

Flow exercised (ADR-driven):
  ingest signal -> incident opened -> orchestrator proposes plan -> approve via PDP ->
  executor applies (dry-run runtime) -> incident resolved -> episodic memory updated.

Run with:  AEGIS_RUN_INTEGRATION=1 pytest tests/integration -q
"""
import os
import time
import uuid

import httpx
import pytest

GATEWAY = os.getenv("AEGIS_GATEWAY_URL", "http://localhost:8001")
CONSOLE = os.getenv("AEGIS_CONSOLE_URL", "http://localhost:8002")
TOKEN = os.getenv("AEGIS_INGEST_TOKEN", "dev-ingest-token")


def _wait(predicate, timeout=60, interval=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    raise AssertionError("timed out waiting for condition")


@pytest.mark.integration
def test_full_incident_lifecycle():
    marker = f"E2E-{uuid.uuid4().hex[:6]}"
    with httpx.Client(timeout=15) as c:
        # 1. ingest a signal
        r = c.post(f"{GATEWAY}/v1/signals", headers={"x-aegis-token": TOKEN},
                   json=[{"kind": "alert", "source": "e2e", "service": "db",
                          "title": f"ConnectionPoolExhausted {marker}", "severity": "sev1",
                          "labels": {}}])
        r.raise_for_status()

        # 2. an incident appears
        def find_incident():
            incs = c.get(f"{CONSOLE}/incidents").json()
            return next((i for i in incs if marker in i["title"]), None)
        incident = _wait(find_incident)
        incident_id = incident["incident_id"]

        # 3. orchestrator proposes a plan (or escalates) -> pending plan visible
        def find_plan():
            plans = c.get(f"{CONSOLE}/plans/pending").json()
            return next((p for p in plans if p["incident_id"] == incident_id), None)
        plan = _wait(find_plan, timeout=90)

        # 4. approve -> executor runs -> incident resolves
        c.post(f"{CONSOLE}/plans/decision",
               json={"plan_id": plan["plan_id"], "decision": "approved", "approver": "e2e"}
               ).raise_for_status()

        def resolved():
            inc = c.get(f"{CONSOLE}/incidents/{incident_id}").json()
            return inc["status"] == "resolved"
        assert _wait(resolved, timeout=60)
