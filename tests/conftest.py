"""Pytest config: register the `integration` marker and skip those tests unless the live
stack is available (opt in with AEGIS_RUN_INTEGRATION=1)."""
import os
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: requires the running Aegis stack")


def pytest_collection_modifyitems(config, items):
    if os.getenv("AEGIS_RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set AEGIS_RUN_INTEGRATION=1 to run against a live stack")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
