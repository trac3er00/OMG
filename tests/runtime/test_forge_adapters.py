# pyright: reportUnknownVariableType=false
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class TestAxolotlAdapter:
    @staticmethod
    def _job() -> dict[str, Any]:
        return {
            "domain": "vision",
            "base_model": {
                "name": "distill-base-v1",
                "source": "approved-registry",
                "allow_distill": True,
            },
        }

    def test_axolotl_adapter_preflight_returns_available_status_when_installed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: True)

        result = adapter.run(
            job=self._job(),
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("adapter") == "axolotl"
        assert result.get("status") == "available"
        assert result.get("available") is True

    def test_axolotl_adapter_preflight_returns_unavailable_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: False)

        result = adapter.run(
            job=self._job(),
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("status") == "unavailable"
        assert result.get("reason") == "axolotl_not_installed"
        assert result.get("available") is False

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

    def test_axolotl_adapter_live_mode_defaults_to_sft(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: False)

        result = adapter.run(
            job=self._job(),
            backend_mode="live",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("mode") == "live_sft"

    def test_axolotl_adapter_live_mode_selects_grpo_for_single_reward_head(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: False)

        job = self._job()
        job["reward_heads"] = 1

        result = adapter.run(
            job=job,
            backend_mode="live",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("mode") == "live_grpo"
        assert result.get("sidecar_required") is True

    def test_axolotl_adapter_live_mode_selects_gdpo_for_multiple_reward_heads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: False)

        job = self._job()
        job["reward_heads"] = 2

        result = adapter.run(
            job=job,
            backend_mode="live",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("mode") == "live_gdpo"
        assert result.get("sidecar_required") is True

    def test_axolotl_adapter_live_unavailable_backend_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: False)

        result = adapter.run(
            job=self._job(),
            backend_mode="live_sft",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("status") == "unavailable_backend"
        assert result.get("reason") == "axolotl_not_installed"

    def test_axolotl_adapter_resume_blocks_double_lora_stack(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: True)

        resume_checkpoint = tmp_path / "checkpoint.safetensors"
        resume_checkpoint.write_text("ok", encoding="utf-8")

        job = self._job()
        job["base_model"] = {
            "name": "distill-base-v1",
            "has_lora_adapter": True,
        }
        job["resume"] = {"checkpoint_path": str(resume_checkpoint)}

        result = adapter.run(
            job=job,
            backend_mode="live_sft",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("status") == "error"
        assert "double_lora_adapter" in str(result.get("reason", ""))

    def test_axolotl_adapter_resume_blocks_incompatible_checkpoint_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: True)

        bad_checkpoint = tmp_path / "checkpoint.zip"
        bad_checkpoint.write_text("bad", encoding="utf-8")

        job = self._job()
        job["resume"] = {"checkpoint_path": str(bad_checkpoint)}

        result = adapter.run(
            job=job,
            backend_mode="live_sft",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("status") == "error"
        assert "incompatible_checkpoint_format" in str(result.get("reason", ""))

    def test_axolotl_adapter_live_sft_emits_checkpoint_and_search_evidence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pytest.importorskip("lab.axolotl_adapter")
        import lab.axolotl_adapter as adapter

        monkeypatch.setattr(adapter, "_check_axolotl_available", lambda: True)

        def _fake_runner(spec: Any) -> Any:
            return SimpleNamespace(
                status="success",
                evidence={"budget": {"time_used_seconds": 0.1}, "isolation": {"process_count": 1}},
                checkpoint_paths=[str(tmp_path / "run" / "checkpoint.safetensors")],
            )

        monkeypatch.setattr(adapter, "run_forge_sandboxed", _fake_runner)

        result = adapter.run(
            job=self._job(),
            backend_mode="live_sft",
            run_id="adapter-live-sft",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        assert result.get("status") == "invoked"
        assert result.get("checkpoint_path")
        assert isinstance(result.get("checkpoint_artifacts"), list)
        assert isinstance(result.get("search_scores"), list)
        assert len(result.get("search_scores", [])) == 6
        assert result.get("search_best_trial") is not None

    def test_axolotl_adapter_status_values_are_valid(self, tmp_path: Path) -> None:
        """Axolotl adapter status must be one of the canonical values."""
        pytest.importorskip("lab.axolotl_adapter")
        from lab.axolotl_adapter import run

        result = run(
            job=self._job(),
            backend_mode="preflight",
            sandbox_root=str(tmp_path),
        )

        assert isinstance(result, dict)
        status = result.get("status")
        assert status in {
            "available",
            "unavailable",
            "unavailable_backend",
            "invoked",
            "error",
            "blocked",
        }


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
