"""E2E test suite conftest — applies e2e marker to all tests in this directory."""
import pytest


def pytest_collection_modifyitems(items):
    """Auto-mark all tests collected from tests/e2e/ with @pytest.mark.e2e."""
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
