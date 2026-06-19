# Aegis — Operations Guide (Journey, Demo, Commands, API, Interactions)

Companion to `AUDIT.md`. Everything here reflects the code as it exists. Where behavior depends on
offline adapters (no Ollama/Qdrant/K8s), that is called out.

---

## 1. User Journey — incident creation to resolution

Personas: **Maya** (on-call SRE), **the platform** (Aegis services).

1. **Signal arrives.** A monitoring system POSTs an alert to the **Ingestion Gateway** (`/v1/signals` or
   `/v1/alerts/alertmanager`). The gateway authenticates the token, computes a content fingerprint, and
   drops duplicates via Redis. New signals are published to `signals.raw` keyed by service.
2. **Correlation → incident.** **Detection** consumes the signal, normalizes it, and applies deterministic
   topology+time correlation. It either attaches the signal to an open, topology-adjacent incident or opens
   a new one — assigning a monotonic **fencing token**, writing a hash-chained audit record, and emitting
   `incidents.lifecycle: opened`.
3. **Paging.** **Notification** sees `opened` (a paging event) and logs/pages Maya with a deep link to the
   console. This path has no AI dependency (ADR-019) — Maya is informed even if the agent tier is down.
4. **Autonomous investigation.** **Orchestrator** consumes `opened` and runs the LangGraph workflow:
   *Triage* sets severity/services → *Investigation* queries the **RAG Service** for grounding (runbooks +
   similar past incidents from Qdrant) and forms a **cited** root-cause hypothesis → *Gate* applies safety
   checks (confidence floor, precedent gate, budget) → *Recommendation* maps the diagnosis to an ordered
   plan of **governed catalog actions**. A durable plan + workflow snapshot are written; it emits
   `plan_proposed` (or `escalated` if it abstains).
5. **Human approval (HITL).** Maya opens the console, sees the pending plan with per-step risk tiers and
   dispositions, and approves (or rejects). The console forwards the decision to the **Policy/Approval
   PDP**, which records an **HMAC-signed, immutable** approval and emits `actions.requested`.
6. **Governed execution (PEP).** **Action Executor** independently verifies the approval signature, confirms
   the **fencing token is still current**, mints a scoped/expiring capability per namespace, validates each
   step's params against the catalog schema, and executes steps idempotently. On any failure it runs **saga
   rollback** of applied reversible steps and escalates; on success it marks the incident resolved and emits
   `resolved`.
7. **Learning loop.** **Knowledge Ingestor** consumes `resolved` and embeds the incident into episodic
   memory, so the next similar incident retrieves it as precedent.

> Current honest caveat (see AUDIT §3): step 6→7 marks "resolved" on *action success*; it does **not** yet
> re-verify the originating signals recovered (FR-5.5 Verifier is not implemented). With offline adapters,
> the LLM/embeddings are deterministic stand-ins and the runtime is dry-run.

---

## 2. Demo Walkthrough (what you'll see)

Using `scripts/send_demo_signals.py` (4 signals: api alert, a duplicate, an adjacent db alert, an unrelated
payments alert) against the full stack:

- **Ingestion** returns `{"accepted": 3, "deduplicated": 1}` — the repeated api alert is dropped.
- **Detection** logs `incident opened` for the api+db group (collapsed into ONE incident via topology) and a
  separate incident for payments. Two incidents total, not four alerts.
- **Notification** logs paging lines with console deep links for each `opened`.
- **Orchestrator** logs an `orchestration complete` line per incident with a decision: with seeded runbooks
  it produces a `plan_proposed` (e.g. `scale_replicas` for the db-pool incident); without grounding it
  `escalate`s (abstention, ADR-016).
- **Console** `GET /incidents` shows the incidents; `GET /plans/pending` shows the proposed plan(s).
- After you POST an approval, **Executor** logs `incident auto-resolved` (dry-run), the incident's status
  flips to `resolved`, and **Knowledge Ingestor** logs `episodic incident embedded`.
- **Jaeger** (`localhost:16686`) shows a single trace per incident spanning ingestion → detection →
  orchestrator → rag → executor.

---

## 3. Exact commands to run locally

Prereqs: Docker + Docker Compose, Python 3.10+. From the repo root.

### Option A — everything in Docker (recommended)
```bash
make install-ai-extra      # local venv deps (for scripts/tests); optional if only using compose
make up-all                # infra + all 9 services; also runs kafka-init to create topics
make db-init               # create schema + seed action catalog/policy   (run once)
make seed-runbooks         # load demo runbooks into Qdrant via the knowledge service
make demo                  # send the 4 demo signals to the gateway

# inspect
curl -s localhost:8002/incidents | jq
curl -s localhost:8002/plans/pending | jq
# approve a plan (copy a plan_id from the previous output):
curl -s -XPOST localhost:8002/plans/decision \
  -H 'content-type: application/json' \
  -d '{"plan_id":"<PLAN_ID>","decision":"approved","approver":"maya"}' | jq
curl -s localhost:8002/incidents/<INCIDENT_ID> | jq   # status should become "resolved"
```

### Option B — infra in Docker, services on host (for debugging)
```bash
make install-ai-extra
make infra-up && make db-init && make seed-runbooks
# each in its own terminal:
make run-ingestion ; make run-detection ; make run-rag ; make run-knowledge
make run-orchestrator ; make run-policy ; make run-executor ; make run-notification ; make run-console
make demo
```

### Observability & teardown
```bash
open http://localhost:16686      # Jaeger traces
make test                        # unit tests (needs deps installed)
make test-integration            # e2e happy-path (AEGIS_RUN_INTEGRATION=1), stack must be up
make infra-down                  # stop infra
docker compose -f docker-compose.yml -f docker-compose.app.yml down   # stop everything
```

---

## 4. Expected Outputs (concrete)

`make demo`:
```json
{"accepted": 3, "deduplicated": 1}
```

`curl localhost:8002/incidents`:
```json
[
  {"incident_id":"…","status":"plan_proposed","severity":"sev1",
   "title":"SEV1: ConnectionPoolExhausted on db","services":["db","api"],"version":2},
  {"incident_id":"…","status":"investigating","severity":"sev1",
   "title":"SEV1: ChargeFailures on payments","services":["payments"],"version":0}
]
```

`curl localhost:8002/plans/pending`:
```json
[{"plan_id":"…","incident_id":"…","status":"proposed","requires_approval":true,
  "autonomy_allowed":false,
  "steps":[{"action":"scale_replicas","risk_tier":"medium","disposition":"require_approval", … }]}]
```

After approval, `GET /incidents/{id}` shows `"status":"resolved"`; executor log: `incident auto-resolved`.

> With offline adapters, severities/plans are deterministic but reflect the rule-based LLM, not real RCA.
> Exact incident counts depend on the correlation window and demo timing.

---

## 5. API Endpoints

**Ingestion Gateway — :8001**
| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/signals` | ingest canonical signals (header `x-aegis-token`) |
| POST | `/v1/alerts/alertmanager` | Alertmanager webhook → signals |
| GET | `/healthz`, `/readyz` | health/readiness |

**Console API — :8002**
| Method | Path | Purpose |
|---|---|---|
| GET | `/incidents?status=&limit=` | list incidents |
| GET | `/incidents/{incident_id}` | incident detail + signals |
| GET | `/plans/pending` | plans awaiting approval (proxies PDP) |
| POST | `/plans/decision` | approve/reject `{plan_id,decision,approver}` (proxies PDP) |
| WS | `/ws/incidents` | live lifecycle event stream |
| GET | `/healthz` | health |

**Knowledge Ingestor — :8003**
| POST | `/v1/runbooks` | ingest a runbook `{source,service,system,text,tags}` |
| GET | `/healthz` | health |

**RAG Service — :8004**
| POST | `/v1/retrieve` | grounded retrieval `{query,service,k_runbooks,k_episodic}` → hits + `has_precedent` |
| GET | `/healthz`, `/readyz` | health/readiness |

**Policy & Approval (PDP) — :8005**
| GET | `/v1/plans/pending` | pending plans with per-step dispositions |
| GET | `/v1/plans/{plan_id}` | plan detail |
| POST | `/v1/plans/{plan_id}/decision` | record signed approval/rejection; emit `actions.requested` |
| GET | `/healthz` | health |

**Workers (no HTTP):** detection, orchestrator, action_executor, notification.

---

## 6. Service Interactions

**Kafka topics (key):**
- `signals.raw` (service) — gateway → detection.
- `incidents.lifecycle` (incident_id) — detection → {orchestrator, notification, console, knowledge}; also
  orchestrator/executor publish lifecycle transitions here.
- `actions.requested` (incident_id) — PDP → executor.
- `actions.result`, `notifications.outbound`, `knowledge.ingest` — defined; result/notify topics reserved.
- DLQ topics exist but have no producers yet (AUDIT §5).

**Synchronous (HTTP):**
- orchestrator → RAG (`/v1/retrieve`), circuit-breaker guarded.
- console → PDP (`/v1/plans/...`).
- operator/CLI → knowledge (`/v1/runbooks`), → gateway (`/v1/signals`).

**Stores:**
- Postgres: incidents, signals, audit_log, action_catalog, policies, plans, plan_steps, approvals,
  actions_ledger, workflow_snapshots. Fencing tokens from `aegis_fencing_token_seq`.
- Redis: dedup keys only.
- Qdrant: `runbooks`, `incidents_episodic`, `architecture_docs`.
- OTel Collector → Jaeger (traces). Metrics defined but not exported yet (AUDIT §3).

**Ownership / safety on the action path:** detection issues a fencing token per incident; the PDP signs the
approval over that token; the executor re-verifies the signature AND that the token still matches the
incident before minting a scoped capability and acting — so a superseded owner cannot execute (ADR-009/014).

---

## 7. Quick health check

```bash
for p in 8001 8002 8003 8004 8005; do
  printf "%s " $p; curl -s localhost:$p/healthz || echo "(down)"; echo
done
docker compose ps         # infra + app container status
```
