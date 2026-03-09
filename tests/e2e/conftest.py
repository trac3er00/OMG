"""E2E test suite conftest — applies e2e marker to all tests in this directory."""
import pytest

pytestmark = pytest.mark.e2e
