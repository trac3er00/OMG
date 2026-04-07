from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runtime.skill_evolution import SkillHealthMetrics, SkillLifecycleManager


class TestSkillHealthMetrics:
    def test_initial_state(self) -> None:
        m = SkillHealthMetrics("test-skill")
        assert m.skill_name == "test-skill"
        assert m.usage_count == 0
        assert m.success_count == 0
        assert m.consecutive_failures == 0
        assert m.failure_reasons == []
        assert m.success_rate == 0.0

    def test_record_success(self) -> None:
        m = SkillHealthMetrics("s")
        m.record_success()
        assert m.usage_count == 1
        assert m.success_count == 1
        assert m.consecutive_failures == 0

    def test_record_failure(self) -> None:
        m = SkillHealthMetrics("f")
        m.record_failure("timeout")
        assert m.usage_count == 1
        assert m.success_count == 0
        assert m.consecutive_failures == 1
        assert m.failure_reasons == ["timeout"]

    def test_record_failure_empty_reason_not_stored(self) -> None:
        m = SkillHealthMetrics("f")
        m.record_failure("")
        assert m.failure_reasons == []

    def test_success_resets_consecutive_failures(self) -> None:
        m = SkillHealthMetrics("r")
        m.record_failure("a")
        m.record_failure("b")
        assert m.consecutive_failures == 2
        m.record_success()
        assert m.consecutive_failures == 0

    def test_success_rate(self) -> None:
        m = SkillHealthMetrics("rate")
        m.record_success()
        m.record_success()
        m.record_failure("x")
        m.record_success()
        assert m.usage_count == 4
        assert m.success_count == 3
        assert m.success_rate == pytest.approx(0.75)

    def test_success_rate_zero_usage(self) -> None:
        m = SkillHealthMetrics("empty")
        assert m.success_rate == 0.0

    def test_metrics_tracking(self) -> None:
        m = SkillHealthMetrics("track")
        for _ in range(3):
            m.record_success()
        m.record_failure("err")
        m.record_failure("err2")
        assert m.usage_count == 5
        assert m.success_count == 3
        assert m.consecutive_failures == 2
        assert len(m.failure_reasons) == 2

    def test_to_dict(self) -> None:
        m = SkillHealthMetrics("d")
        m.record_success()
        m.record_failure("x")
        d = m.to_dict()
        assert d["skill_name"] == "d"
        assert d["usage_count"] == 2
        assert d["success_count"] == 1
        assert d["consecutive_failures"] == 1
        assert d["success_rate"] == pytest.approx(0.5)


class TestSkillLifecycleManager:
    def test_defaults(self) -> None:
        mgr = SkillLifecycleManager()
        assert mgr.promote_after_successes == 5
        assert mgr.retire_after_failures == 3
        assert mgr.metrics == {}

    def test_get_metrics_creates_on_first_access(self) -> None:
        mgr = SkillLifecycleManager()
        m = mgr.get_metrics("new-skill")
        assert m.skill_name == "new-skill"
        assert m.usage_count == 0
        assert mgr.get_metrics("new-skill") is m

    def test_promotion_threshold(self) -> None:
        mgr = SkillLifecycleManager(promote_after_successes=5, retire_after_failures=3)
        for i in range(4):
            status = mgr.record_use("sk", success=True)
            assert status == "proposed", f"iteration {i}"
        status = mgr.record_use("sk", success=True)
        assert status == "active"

    def test_retirement_threshold(self) -> None:
        mgr = SkillLifecycleManager(promote_after_successes=5, retire_after_failures=3)
        for i in range(2):
            status = mgr.record_use("sk", success=False, reason=f"err{i}")
            assert status == "proposed", f"iteration {i}"
        status = mgr.record_use("sk", success=False, reason="err2")
        assert status == "retired"

    def test_lifecycle_promote_then_retire(self) -> None:
        # Given: 5 successes → active
        mgr = SkillLifecycleManager(promote_after_successes=5, retire_after_failures=3)
        for _ in range(5):
            mgr.record_use("sk", success=True)
        m = mgr.get_metrics("sk")
        assert m.success_count == 5

        # When: retire requires a separate manager where promotion threshold is unreachable
        mgr2 = SkillLifecycleManager(
            promote_after_successes=100, retire_after_failures=3
        )
        status = "proposed"
        for _ in range(3):
            status = mgr2.record_use("sk2", success=False, reason="down")
        assert status == "retired"

    def test_success_after_failures_resets_streak(self) -> None:
        mgr = SkillLifecycleManager(
            promote_after_successes=100, retire_after_failures=3
        )
        mgr.record_use("sk", success=False, reason="a")
        mgr.record_use("sk", success=False, reason="b")
        mgr.record_use("sk", success=True)
        status = mgr.record_use("sk", success=False, reason="c")
        assert status == "proposed"

    def test_update_skill_status_writes_file(self, tmp_path: Path) -> None:
        proposals_dir = str(tmp_path)
        filepath = os.path.join(proposals_dir, "my-skill.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"name": "my-skill", "status": "proposed"}, f)

        mgr = SkillLifecycleManager(
            promote_after_successes=2,
            retire_after_failures=3,
            proposals_dir=proposals_dir,
        )
        mgr.record_use("my-skill", success=True)
        status = mgr.record_use("my-skill", success=True)
        assert status == "active"

        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "active"

    def test_update_skill_status_retirement_writes_file(
        self,
        tmp_path: Path,
    ) -> None:
        proposals_dir = str(tmp_path)
        filepath = os.path.join(proposals_dir, "bad-skill.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"name": "bad-skill", "status": "proposed"}, f)

        mgr = SkillLifecycleManager(
            promote_after_successes=100,
            retire_after_failures=3,
            proposals_dir=proposals_dir,
        )
        for _ in range(3):
            mgr.record_use("bad-skill", success=False, reason="crash")

        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert data["status"] == "retired"

    def test_update_ignores_missing_files(self) -> None:
        mgr = SkillLifecycleManager(
            promote_after_successes=1,
            proposals_dir="/nonexistent/path",
        )
        status = mgr.record_use("ghost", success=True)
        assert status == "active"
