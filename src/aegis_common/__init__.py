"""Aegis shared library: config, schemas, event contracts, and infra clients.

Every service depends on this package so that schemas, topic names, and client
construction are defined exactly once (DRY). See ADR-013 (right-sized topology).
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
