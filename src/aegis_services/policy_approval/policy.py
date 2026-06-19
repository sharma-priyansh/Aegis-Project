"""Policy evaluation logic — pure and unit-testable (PDP core, ADR-007).

Decides, for a given plan in a given environment, whether each step may auto-execute or
requires human approval. The decision combines:
  * autonomy policy mode (observe | suggest | auto_low),
  * the step's risk tier and the catalog's requires_approval flag,
  * the plan's precedent-gated autonomy flag (ADR-016).

`observe` never executes; `suggest` always requires approval; `auto_low` may auto-execute
low-risk steps only when autonomy is allowed by precedent.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PolicyMode(str, Enum):
    OBSERVE = "observe"
    SUGGEST = "suggest"
    AUTO_LOW = "auto_low"


class StepDisposition(str, Enum):
    AUTO_APPROVE = "auto_approve"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True)
class StepContext:
    risk_tier: str            # low | medium | high
    catalog_requires_approval: bool
    autonomy_allowed: bool    # precedent-gated (ADR-016)


def evaluate_step(mode: PolicyMode, ctx: StepContext) -> StepDisposition:
    """Return the disposition for a single plan step (ADR-007/016)."""
    if mode == PolicyMode.OBSERVE:
        # Observe-only mode never executes; humans act, Aegis only suggests.
        return StepDisposition.REQUIRE_APPROVAL
    if mode == PolicyMode.SUGGEST:
        return StepDisposition.REQUIRE_APPROVAL
    # AUTO_LOW: auto-execute only low-risk, catalog-auto, precedent-backed steps.
    if (ctx.risk_tier == "low"
            and not ctx.catalog_requires_approval
            and ctx.autonomy_allowed):
        return StepDisposition.AUTO_APPROVE
    return StepDisposition.REQUIRE_APPROVAL


def plan_requires_human(mode: PolicyMode, steps: list[StepContext]) -> bool:
    """True if ANY step in the plan needs human approval (the plan is held)."""
    return any(evaluate_step(mode, s) != StepDisposition.AUTO_APPROVE for s in steps)
