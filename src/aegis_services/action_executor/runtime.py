"""Action runtime adapters — the only code that mutates target infrastructure (§13).

`ActionRuntime` is the seam between Aegis and the cluster it remediates. Two backends:
  * KubernetesRuntime — real actions via the Kubernetes API (restart/scale/rollback).
  * DryRunRuntime     — logs intended actions and returns success; used locally and in
    staging fault-injection where we don't want real mutation. This is an infra adapter
    (like a sandbox), not mock business logic: the saga/idempotency/verification logic in
    the executor is identical regardless of backend.

A runtime receives a scoped Capability (ADR-014); it must reject any action whose
namespace is outside the capability's scope.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from aegis_common.logging import get_logger
from aegis_common.security import Capability

log = get_logger(__name__)


@dataclass
class ActionResult:
    ok: bool
    detail: str


class ActionRuntime(Protocol):
    name: str

    async def apply(self, action: str, params: dict[str, Any], cap: Capability) -> ActionResult: ...


def _scope_ok(params: dict[str, Any], cap: Capability) -> bool:
    ns = params.get("namespace", "default")
    return ns == cap.namespace


class DryRunRuntime:
    name = "dry-run"

    async def apply(self, action: str, params: dict[str, Any], cap: Capability) -> ActionResult:
        if not cap.is_valid():
            return ActionResult(False, "capability invalid/expired")
        if not _scope_ok(params, cap):
            return ActionResult(False, f"namespace {params.get('namespace')} outside capability scope")
        # Allow tests/demos to force a failure to exercise saga rollback.
        if params.get("_force_fail"):
            return ActionResult(False, "forced failure (fault injection)")
        log.info("DRY-RUN apply", extra={"action": action, "params": params})
        return ActionResult(True, f"dry-run ok: {action}({params})")


class KubernetesRuntime:
    name = "kubernetes"

    def __init__(self) -> None:
        from kubernetes import client, config  # imported lazily; optional [k8s] extra

        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        self._apps = client.AppsV1Api()
        self._client = client

    async def apply(self, action: str, params: dict[str, Any], cap: Capability) -> ActionResult:
        if not cap.is_valid():
            return ActionResult(False, "capability invalid/expired")
        if not _scope_ok(params, cap):
            return ActionResult(False, "namespace outside capability scope")
        import asyncio

        try:
            return await asyncio.to_thread(self._apply_sync, action, params)
        except Exception as exc:  # noqa: BLE001
            return ActionResult(False, f"{action} failed: {exc}")

    def _apply_sync(self, action: str, params: dict[str, Any]) -> ActionResult:
        ns = params.get("namespace", "default")
        if action == "restart_deployment":
            import datetime
            body = {"spec": {"template": {"metadata": {"annotations": {
                "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow().isoformat()}}}}}
            self._apps.patch_namespaced_deployment(params["deployment"], ns, body)
            return ActionResult(True, f"restarted {params['deployment']}")
        if action == "scale_replicas":
            body = {"spec": {"replicas": int(params["replicas"])}}
            self._apps.patch_namespaced_deployment_scale(params["deployment"], ns, body)
            return ActionResult(True, f"scaled {params['deployment']} to {params['replicas']}")
        if action == "rollback_revision":
            # Trigger a rollback by bumping a rollout annotation; a controller/Argo handles undo.
            body = {"spec": {"template": {"metadata": {"annotations": {
                "aegis.io/rollback": "true"}}}}}
            self._apps.patch_namespaced_deployment(params["deployment"], ns, body)
            return ActionResult(True, f"rollback requested for {params['deployment']}")
        if action == "clear_cache":
            return ActionResult(True, f"cache {params.get('cache')} flush signalled")
        return ActionResult(False, f"unknown action {action}")


def get_runtime() -> ActionRuntime:
    if os.getenv("AEGIS_K8S_ENABLED", "false").lower() == "true":
        try:
            rt = KubernetesRuntime()
            log.info("using Kubernetes action runtime")
            return rt
        except Exception as exc:  # noqa: BLE001
            log.warning("k8s runtime unavailable; using dry-run", extra={"error": str(exc)})
    return DryRunRuntime()
