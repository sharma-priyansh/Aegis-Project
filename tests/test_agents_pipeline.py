"""Agent-pipeline test using the deterministic offline LLM (no LangGraph, no infra).

Exercises triage -> investigate -> gate -> recommend directly so the agent + safety-gate
logic (ADR-016/017) is covered without external services.
"""
import pytest
from aegis_common.llm import RuleBasedLLM
from aegis_common.reliability import Budget, CircuitBreaker
from aegis_services.orchestrator.agents import (AgentDeps, investigation_agent,
                                                recommendation_agent, triage_agent)
from aegis_services.orchestrator.graph import gate_node


def _deps(retrieve):
    return AgentDeps(llm=RuleBasedLLM(),
                     breaker=CircuitBreaker("llm"),
                     budget=Budget(max_iterations=10, wallclock_seconds=60, max_tokens=100000).start(),
                     retrieve=retrieve)


def _grounded_retriever(query, service):
    return {"citations": ["[runbook#abcd]"], "has_precedent": True,
            "best_precedent_score": 0.9, "evidence_text": "[runbook#abcd] pool exhausted -> scale"}


def _ungrounded_retriever(query, service):
    return {"citations": [], "has_precedent": False, "best_precedent_score": 0.0,
            "evidence_text": ""}


def test_grounded_incident_produces_plan_with_autonomy():
    deps = _deps(_grounded_retriever)
    state = {"title": "DB ConnectionPoolExhausted", "services": ["db"],
             "severity": "sev1", "signals": [{"service": "db", "title": "exhausted", "severity": "sev1"}]}
    state = triage_agent(state, deps)
    state = investigation_agent(state, deps)
    state = gate_node(state, deps)
    assert state["decision"] == "recommend"
    assert state["autonomy_allowed"] is True   # precedent + high confidence (ADR-016)
    state = recommendation_agent(state, deps)
    assert state["plan"] and state["plan"][0]["action"]


def test_ungrounded_incident_escalates():
    deps = _deps(_ungrounded_retriever)
    state = {"title": "weird thing", "services": ["api"], "severity": "sev3",
             "signals": [{"service": "api", "title": "weird", "severity": "sev3"}]}
    state = triage_agent(state, deps)
    state = investigation_agent(state, deps)
    state = gate_node(state, deps)
    # No grounding -> low confidence -> abstain/escalate (ADR-016)
    assert state["decision"] == "escalate"
    assert state["escalated"] is True


def test_budget_exhaustion_escalates():
    deps = AgentDeps(llm=RuleBasedLLM(), breaker=CircuitBreaker("llm"),
                     budget=Budget(max_iterations=1, wallclock_seconds=60, max_tokens=100000).start(),
                     retrieve=_grounded_retriever)
    state = {"title": "x", "services": ["db"], "severity": "sev1", "signals": []}
    state = triage_agent(state, deps)       # consumes the only iteration
    state = investigation_agent(state, deps)
    state = gate_node(state, deps)
    assert state["decision"] == "escalate" and "budget" in state["escalation_reason"]
