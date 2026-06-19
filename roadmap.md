# Aegis — Roadmap, Idea Ranking & Decision Log

**Phase:** Architecture & Planning (no implementation)
**Status:** Draft v1.0
**Date:** 2026-06-19

---

## 1. Idea Generation & Ranking

Ten candidate projects were generated, then scored 1–10 on seven weighted criteria:

- **TD** Technical depth · **IR** Industry relevance · **FD** Future demand (2026–2030) ·
  **RV** Resume value · **AI** AI-engineering depth · **DS** Distributed-systems depth · **LV** Learning value.

| # | Idea | TD | IR | FD | RV | AI | DS | LV | **Total /70** |
|---|---|----|----|----|----|----|----|----|------|
| **1** | **Aegis — Autonomous Incident Response & Remediation (Agentic AIOps)** | 10 | 9 | 10 | 10 | 9 | 10 | 10 | **68** |
| 2 | Real-time Financial-Crime / Fraud Investigation Co-pilot | 9 | 10 | 9 | 9 | 8 | 9 | 8 | 62 |
| 3 | Autonomous Cloud Cost & Reliability Optimizer (FinOps + SRE) | 8 | 9 | 9 | 8 | 7 | 9 | 8 | 58 |
| 4 | Autonomous Supply-Chain Control Tower | 8 | 8 | 8 | 8 | 8 | 9 | 8 | 57 |
| 5 | Multi-Agent Due-Diligence / M&A Research Platform | 8 | 8 | 8 | 8 | 9 | 7 | 7 | 55 |
| 6 | Autonomous Data-Pipeline Healing / Data-Quality Agent | 8 | 8 | 8 | 7 | 7 | 8 | 8 | 54 |
| 7 | Clinical Prior-Auth & Claims Automation (regulated) | 7 | 9 | 8 | 7 | 7 | 7 | 7 | 52 |
| 8 | Grid / Energy Demand-Response Orchestration | 8 | 7 | 8 | 7 | 6 | 9 | 7 | 52 |
| 9 | Autonomous Legal Contract-Lifecycle / Negotiation | 7 | 7 | 7 | 7 | 8 | 6 | 7 | 49 |
| 10 | Trust & Safety / Content-Moderation Platform | 7 | 7 | 7 | 6 | 7 | 8 | 6 | 48 |

### Why Aegis wins

- **It uses every required technology load-bearingly, not decoratively.** OpenTelemetry is the *domain*;
  Kafka carries real signal volume; RAG has a genuine grounding job over runbooks/postmortems; LangGraph
  runs a real multi-agent control loop with a human gate; Kubernetes is both the runtime *and* the thing
  being remediated. Most alternatives have to *shoehorn* one or two of these.
- **Highest distributed-systems depth.** The "exactly one owner per incident, idempotent dangerous
  actions, CP-on-the-action-path, saga rollback" problem set is exactly what distributed-systems
  interviews probe — and here it's intrinsic, not contrived.
- **Highest future demand.** Agentic AIOps / autonomous SRE is one of the clearest 2026–2030 growth areas;
  "AI that operates infrastructure" is where the puck is going.
- **Maximum interview surface area.** It tells a complete story in SWE, AI-engineer, system-design, and
  distributed-systems interviews from one project, because it has a hard backend, a hard AI core, and a
  hard reliability story simultaneously.
- **Not a clichéd build.** It is explicitly none of: chatbot, doc-Q&A, resume analyzer, SaaS clone. The
  agents take consequential production actions, which is the differentiator.

Runner-up (Idea 2, Fraud Co-pilot) is excellent and shares much of the architecture; it is the natural
"second domain" if a finance-flavored variant is ever wanted.

---

## 2. Delivery Roadmap (phased, design-led)

> Each phase ends with a working vertical slice and an honest validation step. We build the **safe
> deterministic spine first**, then layer intelligence, then autonomy — so Aegis is useful and *never
> dangerous* at every stage.

### Phase 0 — Foundations & Architecture (current)
- Finalize `requirements.md`, `architecture.md`, ADRs. Define canonical schemas, topics, action-catalog
  shape, and the autonomy-policy model. Stand up local K8s (kind/k3d) + Terraform/Helm skeletons.
- **Exit:** design reviewed; schemas + interfaces agreed; no app code yet.

### Phase 1 — Deterministic Spine (no AI yet)
- Ingestion Gateway → Kafka → Normalizer → Detection & Correlation → Incident store (Postgres) →
  Console (read-only timeline) → Notification. Redis dedup + locks. OTel wired end-to-end.
- **Exit:** real signals produce correlated incidents and pages, fully traced. Aegis is already useful
  as a correlation/paging engine. Load-test the ingest path.

### Phase 2 — Knowledge & RAG
- Knowledge Ingestor + Qdrant; runbook/postmortem corpus bootstrapped; RAG Service with hybrid search +
  re-rank. Console shows "relevant runbooks / similar past incidents" per incident (still no autonomy).
- **Exit:** retrieval relevance validated on a labeled eval set; episodic memory loop closed.

### Phase 3 — Multi-Agent Diagnosis (read-only)
- LangGraph Orchestrator + agent team (Triage, Diagnostician, Retriever, Verifier, Communicator).
  Durable checkpointing. Agents produce **cited RCA hypotheses** — *suggest only, never act*.
- **Exit:** RCA quality measured against historical incidents; time-to-first-hypothesis within target.

### Phase 4 — Governed Remediation with HITL
- Action catalog + Policy/Approval service + Action Executor (idempotent, fencing tokens, saga rollback).
  LangGraph interrupt/approval gate. Start in **suggest** mode, then **auto-remediate low-risk in
  staging** against fault-injected workloads.
- **Exit:** auto-remediation success rate + rollback correctness validated in staging chaos tests; kill
  switch verified.

### Phase 5 — Hardening, Postmortems, Multi-Tenancy
- Postmortem agent + follow-up proposals; multi-tenant isolation; security review (prompt-injection,
  egress, RBAC); cost controls + model router; SLOs, DR, runbooks for Aegis itself.
- **Exit:** security + chaos + cost reviews pass; production-readiness checklist complete.

### Phase 6 — Limited Production Autonomy
- Graduated autonomy in prod: low-risk auto-remediation for proven incident classes; everything else
  suggest-with-approval. Continuous decision-quality review.
- **Exit:** measured MTTR reduction on target services; sustained false-action rate near zero.

---

## 3. Milestones & Success Metrics

| Milestone | Metric | Target |
|---|---|---|
| M1 Spine live | Ingest throughput / p99 enqueue | ≥100k signals/min · <250 ms |
| M2 Correlation quality | Alerts-per-incident compression; duplicate-incident rate | high compression; ~0 dupes |
| M3 Retrieval quality | Retrieval relevance@k on eval set | meets agreed threshold |
| M4 RCA quality | Top-1 root-cause accuracy vs. historical | beats human-baseline on known patterns |
| M5 Time-to-hypothesis | p95 incident-open → first hypothesis | <30 s (known patterns) |
| M6 Remediation safety | Auto-remediation success; rollback correctness; false-action rate | high · 100% · ~0 |
| M7 Business impact | MTTR reduction on target services | 40–70% |
| M8 Cost | $ / incident | within budget envelope |

---

## 4. Architecture Decision Records (log)

> Full ADRs created per decision in `/docs/adr/`. Summaries:

- **ADR-001 — Domain = Agentic AIOps (Aegis).** *Alternatives:* fraud, supply chain, etc. *Why:* maximal,
  authentic coverage of all target competencies + highest future demand (see §1).
- **ADR-002 — Kafka as event backbone.** *Alt:* RabbitMQ, NATS, cloud queues. *Why:* partitioned ordering
  by `incident_id`, replayability, ecosystem, high throughput; ordering+locality without global coordination.
- **ADR-003 — LangGraph supervised state machine over autonomous chat-agents.** *Alt:* free-form
  multi-agent conversation. *Why:* determinism, inspectability, durable checkpointing, lower token cost,
  testability.
- **ADR-004 — CP on the action path.** *Alt:* AP / optimistic action. *Why:* never double-remediate;
  refuse-and-page is safer than act-and-hope. Reads stay AP.
- **ADR-005 — At-least-once + idempotency over exactly-once.** *Alt:* exactly-once semantics. *Why:*
  simpler, robust, achievable; idempotency keys + execution ledger give effective once-only *effects*.
- **ADR-006 — Externalized, checkpointed workflow state.** *Alt:* in-memory agent state. *Why:*
  crash-tolerance, horizontal scale, resumable HITL interrupts.
- **ADR-007 — Governed action catalog + HITL gate.** *Alt:* open-ended agent tool use on infra. *Why:*
  bounded blast radius, RBAC, auditability; structurally prevents out-of-catalog actions.
- **ADR-008 — Qdrant for vectors.** *Alt:* pgvector, Pinecone, Weaviate, Milvus. *Why:* OSS, K8s-native,
  payload filtering + hybrid search + sharding; avoids overloading Postgres; portable/on-prem.
- **ADR-009 — Redis fenced locks for incident ownership.** *Alt:* DB advisory locks, ZooKeeper/etcd.
  *Why:* low-latency single-owner with fencing token consumed by the executor to defeat split-brain on
  the dangerous path; lighter than a full consensus service for this scope.
- **ADR-010 — OSS/Ollama-first models + escalation router.** *Alt:* single frontier model everywhere.
  *Why:* cost, portability, on-prem for regulated tenants; escalate only hard RCA.
- **ADR-011 — Cloud-agnostic, Kubernetes-first.** *Alt:* one managed cloud. *Why:* portability + interview
  generality; infra via operators/Terraform, swappable behind interfaces.
- **ADR-012 — Transactional outbox + event sourcing for incident state.** *Alt:* dual-write. *Why:*
  atomic DB-write + publish; replayable, auditable lifecycle; CQRS read projections.

---

## 5. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Agent makes a harmful remediation | Low | Critical | HITL gate, catalog-only actions, blast-radius caps, saga rollback, staging-first, kill switch, CP refuse-if-unsure |
| Hallucinated / ungrounded RCA | Med | High | Mandatory citations, groundedness check, confidence-gated planning, episodic-memory grounding |
| Prompt injection via telemetry/docs | Med | High | Untrusted-data boundary, no tool-privilege escalation from content, egress controls, secret scanning |
| Signal-storm overload | Med | Med | Kafka backpressure, dedup, partitioned consumers, severity-based load-shedding |
| LLM cost/latency blowup | Med | Med | Model tiering, semantic cache, per-incident budgets, circuit breakers |
| Split-brain on incident ownership | Low | High | Fenced Redis locks + executor token check + Postgres optimistic concurrency |
| Corpus staleness/poor coverage | Med | Med | Continuous ingest of resolved incidents, retrieval evals, Reliability-Eng curation |
| Over-trust / automation complacency | Med | Med | Graduated autonomy, decision-quality dashboards, human-override metrics, periodic review |
| Self-referential monitoring loop (Aegis watching Aegis) | Low | Med | Sandboxed self-monitoring, separate control domain, explicit loop-breakers |

---

## 6. Definition of Done (planning phase)

- `requirements.md`, `architecture.md`, `roadmap.md` complete and internally consistent.
- Every required design area addressed (problem, value, personas, FR/NFR, high-level / agent /
  distributed / event-driven / DB / vector / RAG / agent-comms / scaling / security / observability /
  deployment architecture).
- Trade-offs and alternatives captured as ADRs.
- **No implementation code, no source files** — design only, per the project mandate.
