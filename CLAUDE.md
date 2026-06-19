# CLAUDE.md

## Core Principles

* Think before coding.
* Understand the problem before proposing solutions.
* Prefer simplicity over cleverness.
* Avoid unnecessary abstractions.
* Avoid premature optimization.
* Make the smallest correct change possible.
* Verify assumptions before acting.
* Never claim something works unless it has been validated.

## Planning First

Before implementation:

1. Understand requirements.
2. Identify edge cases.
3. Explain tradeoffs.
4. Propose architecture.
5. Get alignment.
6. Implement incrementally.

Do not immediately generate large amounts of code.

## Coding Standards

* Write production-grade code.
* Use clear naming.
* Keep functions focused.
* Prefer readability over brevity.
* Add type hints.
* Add meaningful error handling.
* Avoid duplicated logic.

## Project Stack

* FastAPI
* PostgreSQL
* Redis
* Qdrant
* Kafka
* LangGraph
* LangChain
* Docker
* Kubernetes
* OpenTelemetry

## AI System Standards

* Prefer open-source models.
* Prefer Ollama-compatible models.
* Use RAG when grounding is required.
* Explain retrieval strategy.
* Explain memory strategy.
* Explain agent communication strategy.

## System Design Standards

* Design for horizontal scaling.
* Design for failure recovery.
* Consider observability from day one.
* Use async processing where appropriate.
* Use event-driven architecture when beneficial.

## Agent Workflow

When implementing agents:

* Define responsibilities.
* Define tools.
* Define memory.
* Define inputs.
* Define outputs.
* Define failure modes.

Avoid creating agents without a clear purpose.

## Distributed Systems

When proposing architecture:

* Identify bottlenecks.
* Identify scaling limits.
* Discuss CAP tradeoffs.
* Discuss caching.
* Discuss queues.
* Discuss retries.
* Discuss idempotency.
* Discuss monitoring.

## Testing

Before marking a task complete:

* Verify implementation.
* Check edge cases.
* Check error paths.
* Run tests when available.
* Explain limitations honestly.

Never assume code works without validation.

## Documentation

For major decisions:

* Create ADRs.
* Explain alternatives considered.
* Explain why the chosen solution was selected.

## Repository Rules

* No file should exceed 500 lines without strong justification.
* Prefer modular design.
* Keep architecture diagrams updated.
* Keep README updated.
* Keep setup instructions reproducible.

## If Unsure

Stop and ask clarifying questions rather than making assumptions.
