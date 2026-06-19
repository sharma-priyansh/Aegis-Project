"""LLM client abstraction (ADR-010, ADR-021).

`LLMClient` is the single seam through which agents call a model. Two backends:
  * OllamaLLM  — talks to a local Ollama server (OSS models, ADR-010).
  * RuleBasedLLM — a deterministic, offline backend used when no Ollama is reachable.
    It is an *infrastructure adapter*, not mock business logic: it performs lightweight,
    explainable extraction (severity keywords, service mentions, runbook-step echoing) so
    the agent graph, budgets, grounding, and HITL gate all run and are testable offline.
    Production points AEGIS at a real model; the agent logic is identical either way.

Every call returns token usage so the Budget (ADR-017) can charge it. Calls are guarded
by a CircuitBreaker by the caller (ADR-017).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from .config import Settings
from .logging import get_logger

log = get_logger(__name__)


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@runtime_checkable
class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> LLMResponse: ...


def _estimate_tokens(text: str) -> int:
    # ~4 chars/token heuristic; good enough for budget accounting offline.
    return max(1, len(text) // 4)


class OllamaLLM:
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        import httpx

        self._client = httpx.Client(base_url=base_url, timeout=120.0)
        self._model = model

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> LLMResponse:
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        if json_mode:
            payload["format"] = "json"
        resp = self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("message", {}).get("content", "")
        return LLMResponse(
            text=text,
            prompt_tokens=int(data.get("prompt_eval_count", _estimate_tokens(system + user))),
            completion_tokens=int(data.get("eval_count", _estimate_tokens(text))),
        )


class RuleBasedLLM:
    """Deterministic offline backend (infra adapter; see module docstring)."""

    name = "rule-based-offline"
    _SEV = {"sev1": ["outage", "down", "critical", "exhausted", "5xx", "crash"],
            "sev2": ["latency", "slow", "degraded", "error rate", "timeout"],
            "sev3": ["warning", "elevated", "minor"]}

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> LLMResponse:
        text = self._respond(system, user)
        return LLMResponse(text=text, prompt_tokens=_estimate_tokens(system + user),
                           completion_tokens=_estimate_tokens(text))

    def _respond(self, system: str, user: str) -> str:
        role = system.lower()
        if "triage" in role:
            return json.dumps(self._triage(user))
        if "investigat" in role:
            return json.dumps(self._investigate(user))
        if "recommend" in role or "remediat" in role:
            return json.dumps(self._recommend(user))
        return json.dumps({"summary": user[:200]})

    def _triage(self, user: str) -> dict:
        low = user.lower()
        severity = "sev3"
        for sev, kws in self._SEV.items():
            if any(k in low for k in kws):
                severity = sev
                break
        services = sorted(set(re.findall(r"service[=:\s]+([a-z0-9\-_]+)", low)))
        return {"severity": severity, "services": services,
                "summary": f"Triaged as {severity}", "urgent": severity in ("sev1", "sev2")}

    def _investigate(self, user: str) -> dict:
        # Echo the strongest retrieved evidence as the grounded hypothesis (cited).
        cites = re.findall(r"\[[^\]]+\]", user)
        cause = "resource exhaustion" if "exhausted" in user.lower() else "service degradation"
        confidence = 0.82 if cites else 0.4  # ungrounded -> low confidence (ADR-016)
        return {"root_cause": cause, "confidence": confidence,
                "evidence_refs": cites[:5],
                "summary": f"Likely {cause}; grounded in {len(cites)} sources"}

    def _recommend(self, user: str) -> dict:
        low = user.lower()
        if "deployment" in low or "pod" in low or "restart" in low:
            action = {"action": "restart_deployment",
                      "params": {"namespace": "default", "deployment": "api"}}
        elif "scale" in low or "exhausted" in low:
            action = {"action": "scale_replicas",
                      "params": {"namespace": "default", "deployment": "api", "replicas": 5}}
        else:
            action = {"action": "clear_cache",
                      "params": {"namespace": "default", "cache": "default"}}
        return {"plan": [action], "rationale": "Mapped diagnosis to lowest-risk catalog action"}


def get_llm(settings: Settings) -> LLMClient:
    """Return Ollama if reachable, else the deterministic offline backend."""
    try:
        client = OllamaLLM(settings.ollama_url, settings.llm_model)
        client._client.get("/api/tags", timeout=2.0).raise_for_status()  # probe
        log.info("using Ollama LLM", extra={"model": settings.llm_model})
        return client
    except Exception as exc:  # noqa: BLE001
        log.warning("Ollama unavailable; using deterministic offline LLM backend",
                    extra={"error": str(exc)})
        return RuleBasedLLM()
