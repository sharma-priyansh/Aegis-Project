# ADR-003 — LangGraph supervised state machine over autonomous chat-agents

**Status:** Accepted · **Date:** 2026-06-19

## Context
Multi-agent diagnosis must be deterministic, inspectable, durable, and cost-bounded for a safety-critical
workflow.

## Decision
Implement the agent team as a LangGraph supervised state graph with an explicit typed `IncidentState`
checkpointed after every node; agents coordinate via shared state (blackboard), not free-form chat.

## Alternatives considered
Autonomous conversational multi-agent (AutoGen-style free chat) — non-deterministic, hard to test, token-heavy;
a single monolithic prompt — no separation of concerns, no durability.

## Consequences
(+) Deterministic routing, resumable HITL interrupts, testable nodes, lower token cost. (−) Less "emergent"
flexibility; graph must be explicitly designed and maintained.
