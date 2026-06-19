"""The agent team (FR-3). Each agent is a pure-ish function over IncidentState that calls
the LLM through a guarded, budget-charged helper. Responsibilities mirror architecture §4.

Agents during diagnosis are READ-ONLY: they never execute infra actions. The
Recommendation agent only *proposes* catalog actions; execution happens later behind the
PDP/PEP gate (ADR-007/014).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from aegis_common.llm import LLMClient
from aegis_common.logging import get_logger
from aegis_common.reliability import Budget, CircuitBreaker, CircuitOpenError
from aegis_common.telemetry import tracer

from .state import IncidentState

log = get_logger(__name__)

# A retriever callable injected by the orchestrator: (query, service) -> dict with
# keys: citations, has_precedent, best_precedent_score, evidence_text.
RetrieverFn = Callable[[str, str | None], dict[str, Any]]


@dataclass
class AgentDeps:
    llm: LLMClient
    breaker: CircuitBreaker
    budget: Budget
    retrieve: RetrieverFn


def _ask(deps: AgentDeps, system: str, user: str) -> dict:
    """Guarded, budget-charged JSON LLM call (ADR-017)."""
    deps.breaker.guard()
    try:
        resp = deps.llm.complete(system, user, json_mode=True)
    except Exception:
        deps.breaker.record_failure()
        raise
    deps.breaker.record_success()
    deps.budget.charge_tokens(resp.total_tokens)
    try:
        return json.loads(resp.text)
    except json.JSONDecodeError:
        return {"summary": resp.text[:500]}


def triage_agent(state: IncidentState, deps: AgentDeps) -> IncidentState:
    """Set severity, affected services, urgency (architecture §4 Triage)."""
    with tracer(__name__).start_as_current_span("agent.triage"):
        deps.budget.charge_iteration()
        signals_txt = "\n".join(
            f"- service={s.get('service')} {s.get('title')} [{s.get('severity')}]"
            for s in state.get("signals", []))
        out = _ask(deps,
                   "You are the Triage agent for an SRE incident.",
                   f"Incident: {state.get('title')}\nSignals:\n{signals_txt}")
        state["triage_summary"] = out.get("summary", "")
        state["urgent"] = bool(out.get("urgent", state.get("severity") in ("sev1", "sev2")))
        if out.get("severity"):
            state["severity"] = out["severity"]
        merged = set(state.get("services", [])) | set(out.get("services", []))
        state["services"] = sorted(merged)
        state.setdefault("notes", []).append(f"triage: {state['triage_summary']}")
    return state


def investigation_agent(state: IncidentState, deps: AgentDeps) -> IncidentState:
    """Retrieve grounding (RAG), form a cited root-cause hypothesis (architecture §4)."""
    with tracer(__name__).start_as_current_span("agent.investigation"):
        deps.budget.charge_iteration()
        service = (state.get("services") or [None])[0]
        query = f"{state.get('title','')} {state.get('triage_summary','')}".strip()
        state["query"] = query
        ev = deps.retrieve(query, service)
        state["citations"] = ev.get("citations", [])
        state["has_precedent"] = bool(ev.get("has_precedent", False))
        state["best_precedent_score"] = float(ev.get("best_precedent_score", 0.0))
        user = (f"Symptoms: {query}\nRetrieved evidence:\n{ev.get('evidence_text','')}\n"
                f"Citations: {' '.join(state['citations'])}")
        out = _ask(deps, "You are the Investigation agent. Ground every claim in evidence.", user)
        state["root_cause"] = out.get("root_cause", "undetermined")
        state["confidence"] = float(out.get("confidence", 0.0))
        state["evidence_refs"] = out.get("evidence_refs", state["citations"])
        state.setdefault("notes", []).append(
            f"investigation: {state['root_cause']} (conf={state['confidence']:.2f}, "
            f"precedent={state['has_precedent']})")
    return state


def recommendation_agent(state: IncidentState, deps: AgentDeps) -> IncidentState:
    """Map the diagnosis to an ordered plan of governed catalog actions (FR-5.1)."""
    with tracer(__name__).start_as_current_span("agent.recommendation"):
        deps.budget.charge_iteration()
        user = (f"Root cause: {state.get('root_cause')}\n"
                f"Services: {', '.join(state.get('services', []))}\n"
                f"Evidence: {' '.join(state.get('evidence_refs', []))}")
        out = _ask(deps, "You are the Recommendation agent. Propose catalog actions only.", user)
        state["plan"] = out.get("plan", [])
        state["rationale"] = out.get("rationale", "")
        state.setdefault("notes", []).append(
            f"recommendation: {len(state['plan'])} action(s)")
    return state
