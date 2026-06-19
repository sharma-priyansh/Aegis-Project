# Aegis — Autonomous Incident Response & Remediation Platform

Agentic AIOps: ingest live observability signals, correlate them into incidents, diagnose
root cause grounded in your runbooks (RAG), propose a remediation plan, and — under a
policy-driven human approval gate — execute and verify recovery.

> **Design docs:** `requirements.md`, `architecture.md` (v1.1), `design-review.md`, and the
> ADR set in `docs/adr/`. **Read the ADRs before changing the architecture** — they are binding.

## Status — feature-complete across all 4 phases

| Phase | Scope | State |
|---|---|---|
| 1 — Deterministic spine | Ingest → Kafka → Detect/Correlate → Postgres → Notify + Console, Redis dedup, OTel | Implemented |
| 2 — Knowledge & RAG | Qdrant, embeddings, Knowledge Ingestor, RAG Service, episodic memory | Implemented |
| 3 — Multi-agent diagnosis | LangGraph orchestrator: Triage/Investigation/Recommendation, budgets, gating | Implemented |
| 4 — Governed remediation | PDP/PEP, action catalog, signed approvals, fencing, saga rollback, HITL | Implemented |

The deterministic spine (Phase 1) runs with **zero AI** so detection + paging can never be
made worse by the agent tier (ADR-019). Autonomy is **precedent-gated** and **human-approved**
above the lowest risk tier (ADR-007/016).

## Services (one image, many entrypoints — ADR-013)

| Service | Port | Role |
|---|---|---|
| ingestion_gateway | 8001 | OTLP/webhook intake + Redis dedup (FR-1) |
| detection | — | deterministic correlation → incidents (FR-2, ADR-018) |
| knowledge_ingestor | 8003 | embed runbooks + resolved incidents → Qdrant (FR-4.3) |
| rag_service | 8004 | grounded retrieval + precedent gate (FR-4, ADR-016) |
| orchestrator | — | LangGraph multi-agent workflow (FR-3, ADR-003/006/017) |
| policy_approval (PDP) | 8005 | policy eval + signed approvals (ADR-007/014) |
| action_executor (PEP) | — | verify-sign → mint cred → execute → saga rollback (ADR-009/014) |
| notification | — | lifecycle fan-out / paging (FR-6.3) |
| console_api | 8002 | REST + WebSocket operator console (FR-6.1) |

## Architecture flow

```
ingest ─▶ signals.raw ─▶ detection ─▶ incidents.lifecycle(opened) ─▶ orchestrator
                                                                          │ (RAG: rag_service ⇄ Qdrant)
                                                  plan_proposed ◀─────────┘
   console ⇄ PDP(policy) ──approved──▶ actions.requested ─▶ executor(PEP) ─▶ resolved
                                                                          └▶ knowledge_ingestor (episodic)
```

Every hop is OpenTelemetry-traced (Jaeger at :16686); domain metrics in `aegis_common/metrics.py`.

## Quickstart (full stack, local)

```bash
make install-ai-extra                       # deps incl. langgraph, qdrant, fastembed
make up-all                                 # infra + all 9 services (docker)
make db-init                                # schema + seed catalog/policy
make seed-runbooks                          # grounding for RAG
make demo                                   # drive signals through the pipeline
curl localhost:8002/incidents | jq          # incidents
curl localhost:8002/plans/pending | jq      # plans awaiting approval
# approve a plan:
curl -XPOST localhost:8002/plans/decision -H 'content-type: application/json' \
  -d '{"plan_id":"<id>","decision":"approved","approver":"you"}'
```

Without Ollama/Qdrant running, the platform auto-selects deterministic **offline backends**
for embeddings/LLM and a **dry-run** action runtime (ADR-021) — the whole loop still runs,
end to end, with real control flow; only model quality and real cluster mutation are stubbed.

## Run a single service for dev

```bash
make run-ingestion | run-detection | run-rag | run-knowledge | \
     run-orchestrator | run-policy | run-executor | run-notification | run-console
```

## Testing

```bash
make test               # unit tests: correlation, dedup, audit chain, reliability,
                        # security/signing, policy, retrieval, chunking, agent pipeline
make test-integration   # e2e happy-path against a running stack (AEGIS_RUN_INTEGRATION=1)
make lint               # ruff + mypy
```

## Deployment

```bash
docker build -t aegis:latest .              # hardened, non-root, read-only rootfs
make k8s-apply                              # kubectl apply -k deploy/k8s
```

K8s manifests (`deploy/k8s/`) include non-root securityContext, probes, default-deny
NetworkPolicy, HPA, and a kill switch (`AUTONOMY_MODE`). Backing infra (Postgres/Redis/
Kafka/Qdrant/OTel) is provisioned via operators/Helm and referenced by config (§15).

## Safety model (read this)

- **No LLM output can directly trigger an action** (ADR-015). Actions come only from the
  governed catalog, validated against schemas, behind the PDP/PEP gate.
- **Approvals are HMAC-signed and independently verified** by the executor (ADR-014).
- **Fencing tokens** from a Postgres sequence guard the action path; a superseded owner
  cannot execute (ADR-009).
- **Autonomy is precedent-gated**: no auto-remediation without a validated similar incident
  above threshold; otherwise the agents **abstain and escalate** (ADR-016).
- **Per-incident budgets + circuit breakers** bound cost and stop agent loops (ADR-017).
- **Saga rollback** compensates applied steps on failure (FR-5.4).

## Repository layout

```
src/aegis_common/     config, schemas, events, kafka, db, models(+remediation), audit,
                      ownership, embeddings, vectorstore, chunking, llm, reliability,
                      metrics, security
src/aegis_services/   ingestion_gateway, detection, knowledge_ingestor, rag_service,
                      orchestrator (state/agents/graph/worker), policy_approval (PDP),
                      action_executor (PEP + runtime), notification, console_api
db/                   Alembic migrations (+ fencing sequence)
deploy/local/         compose helpers (topics, otel, topology)
deploy/k8s/           Kubernetes manifests (kustomize)
scripts/              init_db, seed_runbooks, send_demo_signals
tests/                unit + integration (e2e)
docs/adr/             ADR-001 … ADR-021
```

## Open-source stack

FastAPI, PostgreSQL, Redis, Apache Kafka, Qdrant, LangGraph/LangChain, OpenTelemetry,
fastembed / Ollama-compatible models. Cloud-agnostic, Kubernetes-first (ADR-011).
