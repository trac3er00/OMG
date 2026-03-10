# pyright: reportUnknownVariableType=false
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


class TestAxolotlAdapter:
    """Red-state tests for axolotl adapter (not yet implemented)."""

    def test_axolotl_adapter_preflight_returns_adapter_field(self, tmp_path: Path) -> None:
        """Axolotl adapter must return adapter field in preflight mode."""
        # This test will FAIL until lab.axolotl_adapter.run is implemented
        pytest.importorskip("lab.axolotl_adapter")
        from lab.axolotl_adapter import run

        result = run(
            job={"domain": "vision"},
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("adapter") == "axolotl"

    def test_axolotl_adapter_invalid_job_returns_error(self, tmp_path: Path) -> None:
        """Axolotl adapter must handle invalid job gracefully."""
        pytest.importorskip("lab.axolotl_adapter")
        from lab.axolotl_adapter import run

        result = run(
            job={},
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        status = result.get("status")
        assert status in {"error", "blocked"}

    def test_axolotl_adapter_status_values_are_valid(self, tmp_path: Path) -> None:
        """Axolotl adapter status must be one of the canonical values."""
        pytest.importorskip("lab.axolotl_adapter")
        from lab.axolotl_adapter import run

        result = run(
            job={"domain": "vision"},
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        status = result.get("status")
        assert status in {"dry_run_contract", "skipped_unavailable_backend", "invoked", "error"}


class TestPyBulletAdapter:
    """Red-state tests for pybullet adapter (not yet implemented)."""

    def test_pybullet_adapter_preflight_returns_kind_simulator(self, tmp_path: Path) -> None:
        """PyBullet adapter must return kind=simulator in preflight mode."""
        # This test will FAIL until lab.pybullet_adapter.run is implemented
        pytest.importorskip("lab.pybullet_adapter")
        from lab.pybullet_adapter import run

        result = run(
            job={"domain": "robotics"},
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("kind") == "simulator"

    def test_pybullet_adapter_returns_structured_result(self, tmp_path: Path) -> None:
        """PyBullet adapter result must have adapter, kind, and status keys."""
        pytest.importorskip("lab.pybullet_adapter")
        from lab.pybullet_adapter import run

        result = run(
            job={"domain": "robotics"},
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert "adapter" in result
        assert "kind" in result
        assert "status" in result


class TestGazeboAndIsaacAdapters:
    """Red-state tests for gazebo and isaac_gym adapters (not yet implemented)."""

    def test_gazebo_adapter_preflight_returns_adapter_field(self, tmp_path: Path) -> None:
        """Gazebo adapter must return adapter field in preflight mode."""
        # This test will FAIL until lab.gazebo_adapter.run is implemented
        pytest.importorskip("lab.gazebo_adapter")
        from lab.gazebo_adapter import run

        result = run(
            job={"domain": "robotics"},
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("adapter") == "gazebo"

    def test_isaac_adapter_live_mode_never_returns_invoked_when_unavailable(
        self, tmp_path: Path
    ) -> None:
        """Isaac Gym adapter must not return invoked status when backend unavailable."""
        # This test will FAIL until lab.isaac_gym_adapter.run is implemented
        pytest.importorskip("lab.isaac_gym_adapter")
        from lab.isaac_gym_adapter import run

        result = run(
            job={"domain": "robotics"},
            backend_mode="live",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        status = result.get("status")
        # When backend is unavailable, status should NOT be "invoked"
        assert status != "invoked"
