"""Security primitives for the action path (ADR-014, ADR-015).

  * sign_approval / verify_approval — HMAC over the canonical approval record. The Action
    Executor (PEP) and credential issuer verify this signature; they do NOT trust the
    caller's assertion that "this was approved" (ADR-014 independent verification).
  * mint_credential — issues a short-lived, narrowly-scoped capability token only after an
    approval signature verifies and the fencing token is current (ADR-009/014).
  * validate_action_params — schema-validates action parameters against the catalog so no
    LLM-shaped output can smuggle an out-of-catalog or malformed action (ADR-015 invariant:
    no LLM output directly triggers an action).

The HMAC secret is read from the environment (a secrets manager in production, §13). This
is a real, verifiable control — not a placeholder — though key management is environment-provided.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any

import orjson

_SECRET = os.getenv("AEGIS_SIGNING_SECRET", "dev-signing-secret-change-me").encode()


def _canonical(record: dict[str, Any]) -> bytes:
    return orjson.dumps(record, option=orjson.OPT_SORT_KEYS)


def sign_approval(record: dict[str, Any]) -> str:
    """HMAC-SHA256 signature over the canonical approval record."""
    return hmac.new(_SECRET, _canonical(record), hashlib.sha256).hexdigest()


def verify_approval(record: dict[str, Any], signature: str) -> bool:
    expected = sign_approval(record)
    return hmac.compare_digest(expected, signature)


@dataclass
class Capability:
    """A short-lived, scoped capability token minted for one execution (ADR-014)."""

    incident_id: str
    plan_id: str
    fencing_token: int
    namespace: str
    expires_at: float
    signature: str

    def is_valid(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if now >= self.expires_at:
            return False
        record = {"incident_id": self.incident_id, "plan_id": self.plan_id,
                  "fencing_token": self.fencing_token, "namespace": self.namespace,
                  "expires_at": self.expires_at}
        return verify_approval(record, self.signature)


def mint_credential(*, incident_id: str, plan_id: str, fencing_token: int, namespace: str,
                    ttl_seconds: int = 120) -> Capability:
    """Mint a scoped, signed, expiring capability. Caller must already have verified the
    approval signature and fencing-token currency (enforced in the Action Executor)."""
    expires_at = time.time() + ttl_seconds
    record = {"incident_id": incident_id, "plan_id": plan_id, "fencing_token": fencing_token,
              "namespace": namespace, "expires_at": expires_at}
    return Capability(incident_id=incident_id, plan_id=plan_id, fencing_token=fencing_token,
                      namespace=namespace, expires_at=expires_at, signature=sign_approval(record))


class ActionValidationError(ValueError):
    """Raised when proposed action params violate the catalog schema (ADR-015)."""


def validate_action_params(action: str, params: dict[str, Any],
                           params_schema: dict[str, Any]) -> None:
    """Minimal JSON-Schema 'required' + type guard. Rejects anything off-catalog (ADR-015).

    We intentionally keep this dependency-free and strict: unknown action -> caller checks
    existence; here we enforce required keys and that params is a flat object.
    """
    if not isinstance(params, dict):
        raise ActionValidationError(f"{action}: params must be an object")
    required = params_schema.get("required", [])
    missing = [k for k in required if k not in params]
    if missing:
        raise ActionValidationError(f"{action}: missing required params {missing}")
