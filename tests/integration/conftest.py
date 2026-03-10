"""Integration test suite conftest — applies integration marker to all tests in this directory."""
import pytest


def pytest_collection_modifyitems(items):
    """Auto-mark all tests collected from tests/integration/ with @pytest.mark.integration."""
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
