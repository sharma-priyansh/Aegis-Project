# Aegis — Repository Audit

**Date:** 2026-06-19 · **Scope:** entire repository as it exists on disk · **Code added:** none.
**Method:** read every module + manifest, cross-checked against the 21 ADRs and the FR/NFR set.

Severity: **[H]** correctness/safety, fix before trusting · **[M]** important, fix before scale/prod ·
**[L]** polish.

---

## 1. Current Architecture Summary

Aegis is a monorepo (`src` layout) of a shared library `aegis_common` plus nine services that share
one container image (entrypoint selects the service, ADR-013). Flow:

```
ingest(8001) ─▶ signals.raw ─▶ detection ─▶ incidents.lifecycle(opened)
   ─▶ orchestrator (LangGraph: triage→investigate→gate→recommend) ⇄ rag(8004) ⇄ Qdrant
   ─▶ plan_proposed ─▶ console(8002)/PDP policy(8005) ─human approve─▶ actions.requested
   ─▶ executor(PEP) ─▶ resolved ─▶ knowledge_ingestor(8003) ─▶ episodic memory
```

Backbone is Kafka (keyed: signals by service, incidents/actions by incident_id). Postgres is system of
record (incidents, signals, hash-chained audit, plans, approvals, action ledger, workflow snapshots).
Redis does dedup only (advisory, ADR-009). Qdrant holds runbooks + episodic incidents. OpenTelemetry
traces every hop. Safety: governed action catalog, PDP/PEP split, HMAC-signed approvals, Postgres fencing
tokens, precedent-gated autonomy, per-incident budgets + circuit breakers, saga rollback. Offline adapters
(ADR-021) let the whole loop run without Ollama/Qdrant/K8s.

~3,800 LOC of services/lib, ~490 LOC tests, 21 ADRs, full K8s manifests. Largest module 242 lines (within
the 500-line rule).

---

## 2. Fully Implemented

- **Ingestion** (FR-1): signal + Alertmanager intake, token auth, Redis dedup, Kafka publish, health/ready.
- **Deterministic correlation** (FR-2, ADR-018): topology + time-window rules, severity escalation, pure
  and unit-tested. Opens/attaches incidents, fencing token issued, audit written.
- **Console** (FR-6.1): incident list/detail, pending-plans + decision proxy to PDP, live WebSocket timeline.
- **Notification** (FR-6.3): lifecycle fan-out, paging-event filter, optional webhook.
- **RAG retrieval core** (FR-4 partial): embeddings abstraction (FastEmbed/Ollama/hashing), Qdrant
  collections, structure-aware chunking, dense retrieval, **precedent gate** (ADR-016) — all real and tested.
- **Knowledge Ingestor**: runbook ingestion + episodic embedding of resolved incidents (closed loop FR-4.3).
- **Agent graph** (FR-3, ADR-003/006/017): LangGraph state machine, Triage/Investigation/Recommendation,
  confidence floor + precedent gate + budget gate, durable end-state snapshot. Tested via offline LLM.
- **Governed remediation** (ADR-007/014): action catalog, PDP policy modes (observe/suggest/auto_low),
  HMAC-signed approvals, independent signature verification in the PEP, scoped/expiring capabilities,
  catalog param validation (ADR-015), fencing-token currency check (ADR-009), idempotent action ledger,
  **saga rollback**. Policy + security logic unit-tested.
- **Reliability** (ADR-017): circuit breaker + budget, unit-tested.
- **Audit** (ADR-014): hash-chained append + `verify_chain`, tamper-detection tested.
- **Deployment**: hardened non-root Dockerfile, K8s manifests (probes, securityContext, default-deny
  NetworkPolicy, HPA, kill switch), compose infra + app overlay. All YAML validated.

---

## 3. Partially Implemented

- **Verifier / FR-5.5 (recovery verification) — [H].** The executor marks an incident `resolved` as soon as
  actions *apply* (`_resolve`), with **no re-check of the originating signals**. The architecture's Verifier
  agent (§4) and FR-5.5 ("verify recovery by re-checking the originating signals; if not recovered, loop
  back") are not implemented. "Action succeeded" is treated as "incident resolved", which is optimistic.
- **RAG pipeline depth — [M].** Only dense retrieval + metadata filter. Hybrid (sparse) search, cross-encoder
  re-ranking, multi-query expansion, parent-document retrieval, and the post-generation groundedness check
  (RAG §9 steps 3-5) are absent. *Note:* deferring hybrid/re-rank is consistent with design-review O3/I8
  (gate on measured retrieval gain), so this is acknowledged-partial, not a silent cut — except the
  groundedness check, which is a real safety gap (an agent can assert beyond its evidence).
- **Metrics export — [M].** `metrics.py` acquires a meter and defines instruments, but **no MeterProvider /
  OTLP metric exporter is configured**, so metric emissions are no-ops unless external autoinstrumentation
  sets a provider. Tracing is fully wired; metrics are effectively not exported. Observability §14 metrics
  (auto-remediation success, false-action rate, $/incident) are defined but not actually collected.
- **Checkpointing (ADR-006) — [M].** LangGraph uses `MemorySaver` (in-process). A durable end-of-run
  `WorkflowSnapshot` is persisted, but **intra-run checkpoints are not durable**, so a mid-run orchestrator
  crash restarts the workflow from scratch rather than resuming. ADR-006 calls for externalized,
  resumable checkpoints.
- **Postmortem (FR-8) — [L].** No postmortem drafting or follow-up proposals.

---

## 4. Remaining To Implement

- Verifier agent + verification loop (FR-5.5) and the Diagnose↔Verify retry edge.
- Transactional outbox + relay (see §6 ADR-012 deviation).
- DLQ producers (topics exist; nothing writes to them) + poison-message handling.
- Durable LangGraph checkpointer (Postgres/Sqlite saver) for true resumability.
- Metrics exporter wiring (MeterProvider + OTLP) so domain metrics actually flow.
- RAG groundedness check; optionally hybrid + re-rank once evals justify (design-review I8).
- Postmortem agent (FR-8). Historical-replay evaluation harness (ADR-016) — there is no eval suite yet, so
  RCA quality is unmeasured.
- Real Kubernetes runtime exercise (only dry-run has been run); KEDA consumer-lag autoscaling for workers.
- Multi-tenancy, service mesh/mTLS (intentionally deferred per design-review O1).

---

## 5. Technical Debt

- **[H] Kafka commit semantics drop failed messages.** In `kafka.py` consume, on handler exception the offset
  is not committed, but the loop continues; the **next successful `consumer.commit()` commits past the failed
  record**, silently skipping it. The comment "message will be redelivered" is incorrect, and no DLQ catches
  it. This breaks the at-least-once guarantee (ADR-005) for any failing message.
- **[H] Detection idempotency path is partly dead code.** `persist_signal` uses `session.add()` which does
  not flush, so the surrounding `except IntegrityError` cannot catch a duplicate `signal_id`; the error
  instead surfaces at commit, rolls back the whole unit (incident + signal), and — combined with the commit
  bug — the duplicate is dropped or loops. The intended "duplicate signal ignored" branch rarely runs. Redis
  dedup at the gateway masks this today, but genuine Kafka redelivery is not handled idempotently.
- **[M] Synchronous audit append is a serialization point + race.** `append_audit` reads the last row and
  computes `seq = last.seq + 1` with no lock; concurrent appenders pick the same seq → unique/PK conflict →
  one transaction fails (and, via the commit bug, may be skipped). It is also a single global chain (no
  per-incident chains) and is written inline rather than via the Kafka→batched-writer path noted in
  architecture §5. Correct under low concurrency, fragile under load.
- **[M] `notification` worker calls `start_producer()` but never produces** (harmless, but misleading).
- **[L] Per-message `consumer.commit()`** in every worker is simple but throughput-limiting at scale.
- **[L] Secrets defaults** (`AEGIS_SIGNING_SECRET=dev-...`, static ingest token) are fine locally but are an
  easy footgun if shipped unchanged.
- **[L] No CI** workflow; tests run only manually. No `ruff`/`mypy` enforced in a pipeline.

---

## 6. ADR Deviations

- **ADR-012 (transactional outbox) — DEVIATED [H].** The ADR says keep the outbox to make the DB-write +
  Kafka-publish atomic. Implementation does a **dual write**: `detection`, `orchestrator`, `policy`, and
  `executor` publish to Kafka inside/around the DB transaction without an outbox table + relay. A crash or
  commit failure between the two yields a lost or phantom event. This is the single most material deviation.
- **ADR-006 (externalized checkpointing) — PARTIAL [M].** MemorySaver + end-state snapshot only; not
  resumable mid-run (see §3).
- **ADR-018 (correlation as a stateful streaming join) — PARTIAL [M].** Implemented as per-signal Postgres
  queries in the consumer, not a Kafka-Streams/Flink keyed-state join. Works, but: (a) it loads up to 200
  open incidents per signal (O(N) scan + Python loop), and (b) **OPEN_NEW has no guard against concurrent
  duplicate incident creation** — two detection replicas processing topology-adjacent services on different
  partitions can both open separate incidents for what should be one. Single-replica detection avoids this;
  multi-replica races. Deterministic-first (the ADR's core) IS honored.
- **ADR-014 (audit) — PARTIAL [M].** Hash-chaining is real and tamper-evident, but appends are not serialized
  per chain (race, §5) and there is no WORM/object-store anchoring yet. PDP/PEP split and signing are done.
- **ADR-005 (idempotency) — PARTIAL [H].** Action ledger is idempotent; the ingest/detection path is not (see
  §5). 
- **Honored well:** ADR-001/002/003/004/007/008/009 (fencing)/010/011/013/015/016/017/019/020/021. No silent
  architecture simplifications beyond those listed; ADR-021 was raised explicitly rather than hidden.

---

## 7. Code Quality Concerns

- Type hints, docstrings, and structured logging are consistent and good across modules.
- **Error handling is broad in places** (`except Exception` in consume/agents) — acceptable for resilience
  but it currently hides the commit-skip bug; failures should route to a DLQ, not be swallowed.
- **Schema duplication risk:** Pydantic schemas and SQLAlchemy ORM are intentionally separate (good), but
  field drift between them is unguarded (no mapping tests).
- **No flush-then-check pattern** for unique constraints (detection); prefer `INSERT … ON CONFLICT DO
  NOTHING` or an explicit existence check.
- **Tests cannot run in this sandbox** (no PyPI); pure-logic suites are validated, but service/integration
  tests are unexecuted here and there is **no mapping/contract test** for Kafka event schemas.
- A few unused imports / dead branches (e.g. `message_stream` helper unused; detection's redundant
  `SignalKind` import).

---

## 8. Scalability Concerns

- **Detection is the chief bottleneck (ADR-018 deviation).** Per-signal full scan of open incidents + the
  cross-partition duplicate-incident race cap it at effectively one replica for correctness. A real keyed
  stateful processor (or a Redis/DB lock on the correlation group) is needed before horizontal scale.
- **Audit append serialization** (§5) becomes a write hot-spot under incident volume.
- **Per-message commit** limits consumer throughput; batch commits or a faster client (confluent-kafka,
  noted in ADR-002) would help.
- **Hot partitions** (a hub service on `signals.*`, a big namespace on `actions.*`) are not salted/sub-keyed
  (design-review I7 not yet applied).
- **Synchronous LLM/RAG calls** in the orchestrator run on a thread; fine for moderate concurrency, but there
  is no global concurrency cap per blast-radius tier yet (design-review I7).

---

## 9. Security Concerns

- **Strong, real controls present:** no LLM output can trigger an action (catalog + schema validation,
  ADR-015); approvals HMAC-signed and independently verified by the PEP (ADR-014); scoped, expiring,
  tamper-evident capabilities; fencing-token currency check (ADR-009); namespace-scope enforcement in the
  runtime; default-deny NetworkPolicy; non-root, read-only-rootfs containers.
- **[M] Signing secret + ingest token default to dev values** and are read from env, not a secrets manager
  yet (§13 calls for CSI/secrets-manager). Shipping defaults unchanged would be exploitable.
- **[M] No mTLS / service mesh** between services (deferred per design-review O1); intra-namespace traffic is
  plaintext.
- **[L] Audit not yet WORM-anchored**, so a DB admin could in principle rewrite history and re-chain;
  hash-chaining detects in-place edits but not a full chain rewrite without an external anchor.
- **[L] Prompt-injection posture is structurally sound** (catalog/HITL boundary) but the missing groundedness
  check (§3) weakens the "every claim grounded" guarantee.

---

## 10. Areas Requiring Real Infrastructure (not offline adapters)

The offline adapters (ADR-021) validate control flow and safety, **not** quality. The following need real
infra before any production-trust claim:

- **LLM (Ollama or hosted):** the offline `RuleBasedLLM` does keyword extraction, not reasoning. RCA quality,
  confidence calibration, and the precedent-gate thresholds (ADR-016) are meaningless until measured against
  a real model with the historical-replay eval (not yet built).
- **Embeddings (FastEmbed/Ollama):** the `HashingEmbedder` captures only lexical overlap; retrieval relevance
  is not representative. Similar-incident search and precedent scoring need a real embedding model.
- **Kubernetes (real runtime):** only `DryRunRuntime` has been exercised. Restart/scale/rollback against a
  live cluster, RBAC-scoped credentials, and actual rollback behavior are unverified.
- **Kafka/Postgres/Redis/Qdrant at volume:** correctness of correlation under partitioned multi-replica
  consumption, audit under concurrency, and throughput targets (NFR-1/2) can only be validated on the real
  stack under load.
- **OTel metrics backend:** metrics need a real MeterProvider + collector pipeline to be observable at all.

---

## Top fix-first list (recommended order)

1. **[H]** Fix Kafka commit/DLQ semantics so failed messages aren't dropped (ADR-005).
2. **[H]** Implement the transactional outbox (ADR-012) to remove dual-write hazards.
3. **[H]** Make ingest/detection idempotent (flush-then-catch or ON CONFLICT) and guard OPEN_NEW against the
   cross-partition duplicate-incident race.
4. **[H]** Add the Verifier step (FR-5.5) so "resolved" means signals recovered, not just actions applied.
5. **[M]** Wire the metrics exporter; serialize audit appends; durable checkpointer; RAG groundedness check.
