# Aegis — Requirements Specification

**Project:** Aegis — Autonomous Incident Response & Remediation Platform (Agentic AIOps)
**Phase:** Architecture & Planning (no implementation)
**Status:** Draft v1.0
**Owner:** Platform / AI Engineering
**Date:** 2026-06-19

---

## 1. Project Selection Summary

Aegis was selected over nine alternatives (see `roadmap.md` §1 for the full ranking). It is the
single project that exercises *every* required competency authentically rather than decoratively:

- It is **observability-native**, so OpenTelemetry is the product domain, not a bolt-on.
- It **ingests high-volume telemetry**, so Kafka and event-driven design are load-bearing.
- It **reasons over operational knowledge**, so RAG + a vector database have a real grounding job.
- It is a **multi-agent control loop with a human approval gate**, so LangGraph / LangChain are core.
- It **operates on a Kubernetes cluster it also runs in**, so cloud-native and distributed-systems
  concerns (idempotency, retries, consensus on "who owns this incident", blast-radius control) are
  unavoidable and interview-rich.

It is deliberately *not* a chatbot, document-Q&A app, resume analyzer, or SaaS clone. The agents take
**consequential actions on production infrastructure**, which is what makes the system design hard and
the resume line credible.

---

## 2. Problem Statement

Modern software organizations run hundreds to thousands of services emitting metrics, logs, and traces.
When something breaks, the bottleneck is rarely *detection* — alerting is mature — it is **diagnosis and
remediation**. On-call engineers spend the critical first minutes of an incident manually correlating
signals across dashboards, searching runbooks, recalling how a similar incident was resolved months ago,
and cautiously applying fixes. This work is:

- **Slow** — Mean Time To Resolution (MTTR) for non-trivial incidents is commonly measured in tens of
  minutes to hours; most of that is human investigation, not the fix itself.
- **Tribal** — the engineer who knows *why* the cache stampedes at 3am may be asleep or have left the company.
- **Inconsistent** — two on-call engineers handle the same alert differently.
- **Expensive and corrosive** — downtime has direct revenue cost, and 3am pages drive burnout and attrition.

**Aegis** is an autonomous, multi-agent platform that ingests live observability data, detects and
correlates anomalies into a single incident, performs root-cause analysis grounded in the
organization's own runbooks and past postmortems, proposes a remediation plan with an explicit
confidence and blast-radius assessment, and — subject to policy-driven human approval — executes that
remediation and verifies recovery. It is an **autonomous SRE teammate that compresses the investigate →
diagnose → fix → verify loop**, while keeping a human in command of high-risk actions.

---

## 3. Business Value

| Lever | Mechanism | Quantifiable outcome |
|---|---|---|
| **Reduced MTTR** | Agents parallelize correlation, RCA, and runbook retrieval that a human does serially | Target 40–70% reduction in MTTR for incidents matching known patterns |
| **Reduced downtime cost** | Faster resolution shortens revenue-impacting outages | Downtime is frequently costed at thousands–tens-of-thousands of dollars per minute for large services |
| **Knowledge retention** | Every resolved incident enriches the RAG corpus; tribal knowledge becomes a queryable asset | Onboarding time for new on-call engineers drops; bus-factor risk falls |
| **Consistency & auditability** | Every action is policy-gated, logged, and traced end-to-end | Clean audit trail for SOC2 / regulated environments |
| **On-call quality of life** | Agents handle triage and routine remediation; humans handle judgment calls | Fewer 3am pages, lower burnout, better retention |
| **Continuous improvement** | Post-incident, agents draft the postmortem and propose guardrail/alert changes | Compounding reliability gains over time |

The economic argument is simple: even a modest MTTR reduction on revenue-critical services pays for the
platform many times over, and the knowledge-retention effect compounds.

---

## 4. User Personas

**P1 — On-Call SRE / Software Engineer ("Maya").** Primary operator. Gets paged, needs to trust Aegis'
diagnosis quickly, wants a clear plan with blast-radius and a one-click approve/reject. Cares about *not*
being woken up for things Aegis can safely handle, and about never having a rogue agent make an outage worse.

**P2 — Engineering Manager / Incident Commander ("Devraj").** Oversees major incidents. Wants a live
incident timeline, who/what is doing what, confidence levels, and the ability to set autonomy policy
("auto-remediate sev-3 in staging; require approval for anything touching prod data stores").

**P3 — Platform / Reliability Engineer ("Lena").** Owns Aegis itself and the runbook corpus. Curates
knowledge sources, tunes detection sensitivity, reviews agent decision quality, and manages the
remediation action catalog (what agents are *allowed* to do).

**P4 — Security / Compliance Officer ("Sam").** Needs assurance that every autonomous action is
authorized, scoped, logged, and reversible, and that the system cannot exfiltrate data or exceed its
blast radius.

**P5 — Service Owner ("Tomas").** Owns a specific microservice. Wants Aegis to respect service-specific
guardrails, notify them when their service is touched, and feed them quality postmortems.

---

## 5. Functional Requirements

### FR-1 — Telemetry & Signal Ingestion
- FR-1.1 Ingest metrics, logs, traces, and alert events via OpenTelemetry (OTLP) and from alerting
  systems (e.g. Alertmanager-style webhooks) onto an event backbone.
- FR-1.2 Normalize heterogeneous signals into a canonical internal `Signal` schema.
- FR-1.3 Deduplicate and rate-limit signal floods (a single failure emits thousands of correlated alerts).

### FR-2 — Anomaly Detection & Incident Correlation
- FR-2.1 Detect anomalies via configurable rules and statistical/ML detectors.
- FR-2.2 **Correlate** related signals across services and time into a single logical `Incident`
  (topology- and time-aware) rather than N separate alerts.
- FR-2.3 Deterministically assign incident ownership so exactly one agent workflow drives each incident
  (no duplicate concurrent remediation of the same incident).

### FR-3 — Multi-Agent Diagnosis (RCA)
- FR-3.1 Orchestrate a team of specialized agents (Triage, Diagnostician, Knowledge/Retriever,
  Remediation Planner, Verifier, Communicator, Postmortem) via a LangGraph state machine.
- FR-3.2 Agents may call **tools** (query metrics, fetch recent deploys, inspect K8s objects, read logs,
  search the vector store) — read-only during diagnosis.
- FR-3.3 Produce a ranked set of root-cause hypotheses, each with supporting evidence and a confidence score.

### FR-4 — Knowledge-Grounded Reasoning (RAG)
- FR-4.1 Retrieve relevant runbooks, past incidents/postmortems, architecture docs, and recent change
  events from a vector database, scoped to the affected services.
- FR-4.2 Ground every hypothesis and remediation step in cited sources; **no ungrounded action proposals**.
- FR-4.3 Continuously ingest new docs and resolved incidents into the corpus (closed-loop learning).

### FR-5 — Remediation Planning & Execution
- FR-5.1 Generate a remediation plan as an ordered list of actions drawn from a **governed action catalog**
  (e.g. restart deployment, scale replicas, roll back to previous revision, drain node, clear cache,
  flip feature flag).
- FR-5.2 Annotate each action with estimated **blast radius**, reversibility, and required approval tier.
- FR-5.3 Enforce a **human-in-the-loop approval gate** per policy; execute only approved (or auto-approved
  low-risk) actions.
- FR-5.4 Execute actions **idempotently** with retries, timeouts, and automatic rollback on failure.
- FR-5.5 **Verify** recovery by re-checking the originating signals; if not recovered, loop back to diagnosis.

### FR-6 — Human Interaction & Control
- FR-6.1 Real-time incident console: live timeline, agent reasoning trace, current hypothesis, proposed plan.
- FR-6.2 Approve / reject / modify proposed actions; interrupt or pause the workflow at any time ("big red button").
- FR-6.3 Notifications via chat/paging integrations with deep links into the console.

### FR-7 — Policy & Governance
- FR-7.1 Configurable autonomy policy per environment/service/severity (observe-only → suggest → auto-remediate).
- FR-7.2 Action catalog with RBAC: which agent/tier may invoke which action against which target.
- FR-7.3 Full, immutable audit log of every decision and action.

### FR-8 — Post-Incident
- FR-8.1 Auto-draft a postmortem (timeline, root cause, actions taken, impact) for human edit.
- FR-8.2 Propose follow-ups (new alerts, guardrails, runbook updates) and feed them back into the corpus.

---

## 6. Non-Functional Requirements

### NFR-1 — Performance & Latency
- Signal ingest path sustains high throughput (target design point: ≥100k signals/min) with p99
  enqueue latency < 250 ms.
- Time from incident-open to first agent hypothesis: target < 30 s (p95) for known patterns.
- Console live-update latency < 1 s.

### NFR-2 — Scalability
- Horizontally scalable across every tier; no single-writer bottleneck on the hot path.
- Stateless services where possible; agent workflow state externalized (durable, resumable).
- Handle bursty "thundering herd" signal storms via backpressure and partitioned consumption.

### NFR-3 — Reliability & Availability
- Control plane target availability 99.9%. Aegis must degrade gracefully: if the LLM/agent tier is
  unavailable, deterministic detection + paging still works (Aegis never makes incidents *worse* by failing).
- No data loss on the ingest path (at-least-once delivery + idempotent processing).
- Exactly-one-owner guarantee per incident even under partition/failover.

### NFR-4 — Consistency & Correctness
- Incident ownership and action execution are **idempotent** and safe under retries and duplicate delivery.
- Action execution is transactional at the plan-step level with compensating rollback.
- Strong consistency for incident state and audit log; eventual consistency acceptable for derived analytics.

### NFR-5 — Security
- Least-privilege: agents act only through the governed action catalog with scoped, short-lived credentials.
- Tenant isolation (multi-tenant capable); no cross-tenant data or action leakage.
- Prompt-injection resistance: retrieved content and telemetry are untrusted input and cannot escalate
  agent privileges or trigger unapproved actions.
- All data encrypted in transit and at rest; secrets via a secrets manager, never in prompts or logs.

### NFR-6 — Observability (the platform observes itself)
- Full distributed tracing (OpenTelemetry) across services *and* across agent/LLM steps.
- Metrics on agent decision quality, RCA accuracy, auto-remediation success rate, false-action rate,
  token/cost per incident.
- Every agent action emits a span; the audit log is queryable and exportable.

### NFR-7 — Maintainability & Extensibility
- New detectors, tools, agents, and remediation actions are pluggable without core changes.
- No source file exceeds 500 lines without justification (per repo standard); modular service boundaries.

### NFR-8 — Cost
- LLM spend is bounded per incident with budgets, caching, model-tiering (small models for routine
  steps, large models for hard RCA), and circuit breakers.

### NFR-9 — Compliance & Auditability
- Immutable, exportable audit trail suitable for SOC2-style review; data-retention policies configurable.

### NFR-10 — Portability
- Cloud-agnostic, Kubernetes-first. All infra dependencies (Kafka, Postgres, Redis, vector DB) run as
  portable workloads or are swappable behind interfaces.

---

## 7. Scope

**In scope (design):** ingestion, detection, correlation, multi-agent RCA, RAG, governed remediation with
HITL, verification, postmortem generation, policy/RBAC, observability, cloud-native deployment design.

**Out of scope (v1):** building a full APM/dashboards product (Aegis consumes existing telemetry); fully
autonomous remediation of *novel* incidents without human approval; non-Kubernetes runtime targets.

---

## 8. Key Assumptions & Constraints

- The organization already emits OpenTelemetry-compatible signals (or can via collectors).
- Remediation targets are Kubernetes-based workloads in v1.
- A curated runbook/postmortem corpus exists or can be bootstrapped.
- Human approval is *required* for any action above the configured low-risk tier in production.
- Open-source / Ollama-compatible models are preferred where they meet the quality bar; hard RCA may use
  a larger hosted model behind an abstraction (see `architecture.md` §11).
