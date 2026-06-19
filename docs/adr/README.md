# Architecture Decision Records — Aegis

Canonical ADRs for all major technical decisions. Format: Status · Context · Decision · Alternatives ·
Consequences. Records superseded or amended by the Staff-Engineer design review (`../../design-review.md`)
are marked accordingly.

| ADR | Title | Status |
|---|---|---|
| 001 | Domain = Agentic AIOps (Aegis) | Accepted |
| 002 | Kafka as the event backbone | Accepted |
| 003 | LangGraph supervised state machine over autonomous chat-agents | Accepted |
| 004 | CP (consistency) on the action path | Accepted |
| 005 | At-least-once delivery + idempotency over exactly-once | Accepted |
| 006 | Externalized, checkpointed workflow state | Accepted |
| 007 | Governed action catalog + human-in-the-loop gate | Accepted |
| 008 | Qdrant as the vector database | Accepted |
| 009 | Incident ownership: Kafka partition + Postgres fencing token | Accepted (revises Redis Redlock) |
| 010 | OSS/Ollama-first models + escalation router | Accepted |
| 011 | Cloud-agnostic, Kubernetes-first | Accepted |
| 012 | Transactional outbox; defer event-sourcing/CQRS | Amended |
| 013 | Right-sized v1 service topology (~7 services) | Accepted |
| 014 | PDP/PEP split, independent credential issuer, hash-chained audit | Accepted |
| 015 | Assume-injection-succeeds security model | Accepted |
| 016 | Precedent-gated autonomy + abstention + replay eval | Accepted |
| 017 | Per-incident agent budgets + circuit breakers | Accepted |
| 018 | Correlation as deterministic-first stateful streaming join | Accepted |
| 019 | Aegis reliability isolation + no self-remediation in v1 | Accepted |
| 020 | Signal/trace retention tiering | Accepted |
| 021 | Offline infra adapters (embeddings/LLM/runtime) | Accepted |
