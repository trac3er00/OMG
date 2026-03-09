"""Integration test suite conftest — applies integration marker to all tests in this directory."""
import pytest

pytestmark = pytest.mark.integration
