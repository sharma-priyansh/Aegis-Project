"""Send sample signals to a running Ingestion Gateway to exercise the spine end-to-end.

Demonstrates: dedup (the duplicate is dropped), topology correlation (api + db collapse
into one incident), and a separate unrelated incident (payments).

    python scripts/send_demo_signals.py
Watch the detection + notification logs and GET http://localhost:8002/incidents.
"""
from __future__ import annotations

import os

import httpx

GATEWAY = os.getenv("AEGIS_GATEWAY_URL", "http://localhost:8001")
TOKEN = os.getenv("AEGIS_INGEST_TOKEN", "dev-ingest-token")


def signal(service: str, title: str, severity: str = "sev2", **labels) -> dict:
    return {
        "kind": "alert",
        "source": "demo",
        "service": service,
        "title": title,
        "severity": severity,
        "labels": labels,
    }


def main() -> None:
    headers = {"x-aegis-token": TOKEN}
    batch = [
        signal("api", "HighLatency", "sev2", region="us"),
        signal("api", "HighLatency", "sev2", region="us"),  # duplicate -> deduped
        signal("db", "ConnectionPoolExhausted", "sev1"),     # adjacent to api -> same incident
        signal("payments", "ChargeFailures", "sev1"),        # unrelated -> separate incident
    ]
    with httpx.Client(base_url=GATEWAY, headers=headers, timeout=10) as client:
        resp = client.post("/v1/signals", json=batch)
        resp.raise_for_status()
        print("ingest result:", resp.json())


if __name__ == "__main__":
    main()
