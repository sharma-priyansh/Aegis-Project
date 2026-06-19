"""Unit tests for PDP policy evaluation (ADR-007/016)."""
from aegis_services.policy_approval.policy import (PolicyMode, StepContext, StepDisposition,
                                                   evaluate_step, plan_requires_human)

LOW_AUTO = StepContext(risk_tier="low", catalog_requires_approval=False, autonomy_allowed=True)
HIGH = StepContext(risk_tier="high", catalog_requires_approval=True, autonomy_allowed=True)
LOW_NOPREC = StepContext(risk_tier="low", catalog_requires_approval=False, autonomy_allowed=False)


def test_auto_low_approves_low_risk_with_precedent():
    assert evaluate_step(PolicyMode.AUTO_LOW, LOW_AUTO) == StepDisposition.AUTO_APPROVE


def test_suggest_always_requires_approval():
    assert evaluate_step(PolicyMode.SUGGEST, LOW_AUTO) == StepDisposition.REQUIRE_APPROVAL


def test_observe_never_auto_approves():
    assert evaluate_step(PolicyMode.OBSERVE, LOW_AUTO) == StepDisposition.REQUIRE_APPROVAL


def test_high_risk_requires_approval_even_in_auto():
    assert evaluate_step(PolicyMode.AUTO_LOW, HIGH) == StepDisposition.REQUIRE_APPROVAL


def test_precedent_gate_blocks_autonomy():
    assert evaluate_step(PolicyMode.AUTO_LOW, LOW_NOPREC) == StepDisposition.REQUIRE_APPROVAL


def test_plan_requires_human_if_any_step_does():
    assert plan_requires_human(PolicyMode.AUTO_LOW, [LOW_AUTO, HIGH])
    assert not plan_requires_human(PolicyMode.AUTO_LOW, [LOW_AUTO])
