"""Seed a couple of runbooks into the Knowledge Ingestor so RAG has grounding (FR-4).

    python scripts/seed_runbooks.py     # requires the knowledge service on :8003
"""
from __future__ import annotations

import os
import httpx

KNOWLEDGE = os.getenv("AEGIS_KNOWLEDGE_URL", "http://localhost:8003")

RUNBOOKS = [
    {"source": "runbook/db-pool-exhausted", "service": "db", "system": "postgres",
     "tags": ["database", "connections"],
     "text": "# DB Connection Pool Exhausted\n"
             "Step 1: Check active connections and pool saturation.\n"
             "Step 2: If saturated due to load, scale the api deployment replicas.\n"
             "Step 3: If a leak, restart the offending deployment to reset connections.\n"
             "## Verify\nConfirm pool utilisation drops and latency recovers."},
    {"source": "runbook/api-high-latency", "service": "api", "system": "service",
     "tags": ["latency"],
     "text": "# API High Latency\n"
             "Step 1: Check recent deploys for regressions.\n"
             "Step 2: If a bad deploy, roll back to the previous revision.\n"
             "Step 3: If cache cold, clear and warm the cache.\n"
             "## Verify\nLatency p99 returns under SLO."},
]


def main() -> None:
    with httpx.Client(base_url=KNOWLEDGE, timeout=60) as c:
        for rb in RUNBOOKS:
            r = c.post("/v1/runbooks", json=rb)
            r.raise_for_status()
            print(f"ingested {rb['source']}: {r.json()}")


if __name__ == "__main__":
    main()
