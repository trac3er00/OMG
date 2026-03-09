"""E2E test suite conftest — applies e2e marker, extended timeout, and xdist grouping.

E2E tests spawn shell subprocesses against the real project root and must not
run concurrently.  The ``xdist_group`` marker ensures all e2e tests land on
the same worker, preventing filesystem contention under ``-n auto / -n N``.
"""
import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            item.add_marker(pytest.mark.timeout(120))
            item.add_marker(pytest.mark.xdist_group("e2e"))
