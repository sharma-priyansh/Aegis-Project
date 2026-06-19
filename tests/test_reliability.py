"""Unit tests for circuit breaker + budget (ADR-017). Pure, no infra."""
from aegis_common.reliability import Budget, BreakerState, CircuitBreaker, CircuitOpenError
import pytest


def test_breaker_trips_after_threshold():
    clk = [0.0]
    cb = CircuitBreaker("t", failure_threshold=2, cooldown_seconds=5, clock=lambda: clk[0])
    assert cb.allow()
    cb.record_failure(); cb.record_failure()
    assert not cb.allow() and cb.state == BreakerState.OPEN
    with pytest.raises(CircuitOpenError):
        cb.guard()


def test_breaker_half_opens_then_recovers():
    clk = [0.0]
    cb = CircuitBreaker("t", failure_threshold=1, cooldown_seconds=5, clock=lambda: clk[0])
    cb.record_failure()
    assert cb.state == BreakerState.OPEN
    clk[0] = 6
    assert cb.state == BreakerState.HALF_OPEN
    cb.record_success()
    assert cb.allow() and cb.state == BreakerState.CLOSED


def test_budget_iteration_limit():
    b = Budget(max_iterations=2, wallclock_seconds=100, max_tokens=1000).start()
    b.charge_iteration(); assert b.exhausted() is None
    b.charge_iteration(); assert "iteration" in (b.exhausted() or "")


def test_budget_token_limit():
    b = Budget(max_iterations=10, wallclock_seconds=100, max_tokens=50).start()
    b.charge_tokens(60); assert "token" in (b.exhausted() or "")


def test_budget_wallclock_limit():
    clk = [0.0]
    b = Budget(max_iterations=10, wallclock_seconds=5, max_tokens=1000)
    b.clock = lambda: clk[0]
    b.start(); clk[0] = 6
    assert "wallclock" in (b.exhausted() or "")
