"""LangGraph workflow assembly (ADR-003, ADR-006, ADR-016, ADR-017).

Graph:  triage -> investigate -> gate -> {recommend -> finalize | escalate} -> END

Safety gates implemented in `gate_node`:
  * Confidence floor: confidence < CONFIDENCE_FLOOR -> escalate (abstain, ADR-016/AI2).
  * Precedent gate:   autonomy_allowed only if has_precedent AND confidence high (ADR-016).
  * Budget:           exhausted budget -> escalate to a human (ADR-017/AG1).
Otherwise a plan is produced and marked requires_approval unless autonomy is allowed AND
the policy/risk tier permits auto-execution (final approval decision is the PDP's, §Phase4).

Checkpointing uses LangGraph's MemorySaver within the run; the durable record is the
WorkflowSnapshot + Plan persisted by the worker (ADR-006). Execution is intentionally NOT
a graph node — it lives behind the PDP/PEP services (ADR-013), so the graph stops at
"plan proposed", which IS the human-in-the-loop interrupt point.
"""
from __future__ import annotations

from functools import partial

from aegis_common.logging import get_logger

from .agents import AgentDeps, investigation_agent, recommendation_agent, triage_agent
from .state import IncidentState

log = get_logger(__name__)

CONFIDENCE_FLOOR = 0.4   # below this we abstain and escalate (ADR-016)
AUTONOMY_CONFIDENCE = 0.7  # min confidence to even consider autonomy


def gate_node(state: IncidentState, deps: AgentDeps) -> IncidentState:
    """Apply confidence / precedent / budget safety gates (ADR-016/017)."""
    state["iterations"] = deps.budget.iterations_used
    state["tokens_used"] = deps.budget.tokens_used

    reason = deps.budget.exhausted()
    if reason:
        state["escalated"] = True
        state["escalation_reason"] = reason
        state["decision"] = "escalate"
        return state

    confidence = float(state.get("confidence", 0.0))
    if confidence < CONFIDENCE_FLOOR:
        state["escalated"] = True
        state["escalation_reason"] = f"low confidence {confidence:.2f} < {CONFIDENCE_FLOOR}"
        state["decision"] = "escalate"
        return state

    autonomy = bool(state.get("has_precedent")) and confidence >= AUTONOMY_CONFIDENCE
    state["autonomy_allowed"] = autonomy
    state["requires_approval"] = not autonomy  # risk-tier may still force approval (Phase 4)
    state["escalated"] = False
    state["decision"] = "recommend"
    return state


def finalize_node(state: IncidentState) -> IncidentState:
    state["decision"] = "plan_ready"
    return state


def _route_after_gate(state: IncidentState) -> str:
    return "escalate" if state.get("decision") == "escalate" else "recommend"


def build_graph(deps: AgentDeps):
    """Construct and compile the LangGraph state machine with a checkpointer."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    g = StateGraph(IncidentState)
    g.add_node("triage", partial(triage_agent, deps=deps))
    g.add_node("investigate", partial(investigation_agent, deps=deps))
    g.add_node("gate", partial(gate_node, deps=deps))
    g.add_node("recommend", partial(recommendation_agent, deps=deps))
    g.add_node("finalize", finalize_node)

    g.set_entry_point("triage")
    g.add_edge("triage", "investigate")
    g.add_edge("investigate", "gate")
    g.add_conditional_edges("gate", _route_after_gate,
                            {"recommend": "recommend", "escalate": END})
    g.add_edge("recommend", "finalize")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=MemorySaver())
