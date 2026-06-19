"""Reliability primitives shared by every service (ADR-017).

  * CircuitBreaker — trips after N consecutive failures, half-opens after a cooldown.
    Wraps the LLM provider and the target-infra client so a failing dependency degrades
    gracefully instead of cascading (NFR-3).
  * Budget — a per-incident ceiling on iterations / wall-clock / tokens. The agent loop
    consults it and escalates to a human on exhaustion (ADR-017), bounding cost and the
    Diagnose->Verify oscillation risk (AG1).

Both are pure, dependency-free, and unit-tested.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class BreakerState(str, Enum):
    CLOSED = "closed"      # healthy, calls pass through
    OPEN = "open"          # tripped, calls rejected fast
    HALF_OPEN = "half_open"  # probing recovery


class CircuitOpenError(RuntimeError):
    """Raised when a call is attempted while the breaker is OPEN."""


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, cooldown_seconds: float = 30.0,
                 clock=time.monotonic) -> None:
        self.name = name
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._state = BreakerState.CLOSED
        self._opened_at = 0.0

    @property
    def state(self) -> BreakerState:
        if self._state == BreakerState.OPEN and (self._clock() - self._opened_at) >= self._cooldown:
            self._state = BreakerState.HALF_OPEN
        return self._state

    def allow(self) -> bool:
        return self.state != BreakerState.OPEN

    def record_success(self) -> None:
        self._failures = 0
        self._state = BreakerState.CLOSED

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._state = BreakerState.OPEN
            self._opened_at = self._clock()

    def guard(self) -> None:
        """Raise CircuitOpenError if calls are currently not permitted."""
        if not self.allow():
            raise CircuitOpenError(f"circuit '{self.name}' is open")


@dataclass
class Budget:
    """Per-incident resource budget (ADR-017)."""

    max_iterations: int
    wallclock_seconds: float
    max_tokens: int
    clock: Callable[[], float] = field(default=time.monotonic)
    _start: float = field(default=0.0, init=False)
    _iterations: int = field(default=0, init=False)
    _tokens: int = field(default=0, init=False)

    def start(self) -> "Budget":
        self._start = self.clock()
        return self

    def charge_iteration(self) -> None:
        self._iterations += 1

    def charge_tokens(self, n: int) -> None:
        self._tokens += max(0, n)

    @property
    def tokens_used(self) -> int:
        return self._tokens

    @property
    def iterations_used(self) -> int:
        return self._iterations

    def elapsed(self) -> float:
        return self.clock() - self._start

    def exhausted(self) -> Optional[str]:
        """Return a reason string if any limit is exceeded, else None."""
        if self._iterations >= self.max_iterations:
            return f"iteration budget exhausted ({self._iterations}/{self.max_iterations})"
        if self._tokens >= self.max_tokens:
            return f"token budget exhausted ({self._tokens}/{self.max_tokens})"
        if self._start and self.elapsed() >= self.wallclock_seconds:
            return f"wallclock budget exhausted ({self.elapsed():.0f}s/{self.wallclock_seconds:.0f}s)"
        return None
