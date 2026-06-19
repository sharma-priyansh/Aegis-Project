"""Service dependency topology used for topology-aware correlation (ADR-018).

Loaded from a JSON file (AEGIS_TOPOLOGY_PATH) mapping service -> list of dependencies.
Adjacency is treated as bidirectional for correlation: a fault in a dependency and a
fault in its dependent are likely the same incident.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


class Topology:
    def __init__(self, edges: dict[str, list[str]] | None = None):
        self._adj: dict[str, set[str]] = {}
        for svc, deps in (edges or {}).items():
            for dep in deps:
                self._adj.setdefault(svc, set()).add(dep)
                self._adj.setdefault(dep, set()).add(svc)  # bidirectional

    def adjacent(self, a: str, b: str) -> bool:
        """True if a == b or a and b are directly connected in the topology."""
        return a == b or b in self._adj.get(a, set())

    def related(self, service: str, others: set[str]) -> bool:
        """True if `service` is adjacent to any service in `others`."""
        return any(self.adjacent(service, o) for o in others)

    @classmethod
    def load(cls) -> "Topology":
        path = os.getenv("AEGIS_TOPOLOGY_PATH")
        if path and Path(path).exists():
            return cls(json.loads(Path(path).read_text()))
        return cls({})
