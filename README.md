# Aegis — Autonomous Incident Response & Remediation Platform

Agentic AIOps: ingest live observability signals, correlate them into incidents, diagnose root cause
grounded in your runbooks (RAG), and — under a human approval gate — remediate and verify recovery.

> **Design docs:** `requirements.md`, `architecture.md` (v1.1), `design-review.md`, and the ADR set in
> `docs/adr/`. **Read the ADRs before changing the architecture** — they are binding decisions.

## Status

| Phase | Scope | State |
|---|---|---|
| **1 — Deterministic spine** | Ingest → Kafka → Detect/Correlate → Postgres → Notify + Console, Redis dedup, OTel | **Implemented (this repo)** |
| 2 — Knowledge & RAG | Qdrant + Knowledge Ingestor + RAG Service | Scaffolded (`[ai]` extra), not yet wired |
| 3 — Multi-agent diagnosis | LangGraph Orchestrator + agents (read-only) | Planned |
| 4 — Governed remediation | Policy/Approval + Action Executor + HITL | Planned (approval endpoint returns 501) |

Phase 1 is the **safe, useful base** mandated by ADR-019 / roadmap §2: detection + correlation + paging work
with **zero AI** in the loop, so the platform can never make an incident worse before the agent tier exists.

## Architecture at a glance

```
 sources ──▶ Ingestion Gateway ──▶ Kafka(signals.raw) ──▶ Detection & Correlation ──▶ Postgres
 (OTLP /                (dedup, FastAPI)                       (deterministic, ADR-018)     │
  Alertmanager)                                                                             ▼
                                          Kafka(incidents.lifecycle, keyed by incident_id) ─┤
                                                          │                                  │
                                              Notification worker            Console API (REST + WebSocket)
```

Every hop is OpenTelemetry-traced (Jaeger UI at :16686). Partition keys, topics, and event schemas live in
`src/aegis_common/events.py`.

## Repository layout

```
src/aegis_common/        shared library: config, schemas, events, kafka, db, models, audit, ownership
src/aegis_services/
  ingestion_gateway/     FastAPI intake + dedup + publish               (FR-1)
  detection/             normalize + deterministic correlation worker   (FR-2, ADR-018)
  notification/          lifecycle fan-out / paging                     (FR-6.3)
  console_api/           REST + WebSocket operator console              (FR-6.1)
db/                      Alembic migrations (+ fencing-token sequence)
deploy/local/            docker-compose helpers: topics, otel, topology
scripts/                 init_db.py, send_demo_signals.py
tests/                   pure-logic unit tests (correlation, dedup, hash chain)
docs/adr/                Architecture Decision Records
```

## Quickstart (local)

Prereqs: Docker + Docker Compose, Python 3.10+.

```bash
# 1. Install the package (spine only; add ,ai for Phase 2/3 deps)
make install

# 2. Start backing stores + observability and create Kafka topics
make infra-up

# 3. Create the schema + seed the action catalog/policy
make db-init

# 4. Run the services (each in its own terminal)
make run-ingestion      # :8001
make run-detection
make run-notification
make run-console        # :8002

# 5. Drive the spine end-to-end
make demo               # sends sample signals
curl localhost:8002/incidents | jq
# Live timeline:  websocat ws://localhost:8002/ws/incidents
# Traces:         http://localhost:16686  (Jaeger)
```

The demo sends an `api` alert, a duplicate (dropped by Redis dedup), an adjacent `db` alert (collapsed into
the **same** incident via topology correlation), and an unrelated `payments` alert (a **separate** incident).

## Testing

```bash
make test     # unit tests: correlation rules, dedup fingerprint, audit hash-chain
make lint     # ruff + mypy
```

Pure-logic tests run without infrastructure. Integration tests against the live stack land alongside Phase 2.

## Key design decisions (see `docs/adr/`)

- **ADR-009** ownership = Kafka single-consumer-per-partition + Postgres fencing token (not Redis locks).
- **ADR-005** at-least-once + idempotent handlers (signal_id PK, fingerprint dedup).
- **ADR-013** right-sized topology; agents run in-process in the Orchestrator (Phase 3).
- **ADR-014** hash-chained, tamper-evident audit log.
- **ADR-018** deterministic-first correlation (topology + time window); ML deferred.
- **ADR-019** Aegis degrades safe to deterministic paging; no self-remediation in v1.

## License / stack

Open-source only: FastAPI, PostgreSQL, Redis, Apache Kafka, Qdrant, LangGraph/LangChain, OpenTelemetry,
Ollama-compatible models. Cloud-agnostic, Kubernetes-first (ADR-011).
