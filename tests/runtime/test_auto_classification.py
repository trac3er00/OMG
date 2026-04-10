from __future__ import annotations

from runtime.tool_plan_gate import (
    TaskClassification,
    classify_task,
    log_classification,
)


class TestClassifyTask:
    def test_security_sensitive_task_elevated(self):
        result = classify_task("Update the auth token rotation logic")
        assert result.risk_level in ("high", "critical")
        assert result.governance_pipeline in ("elevated", "maximum")

    def test_simple_task_minimal(self):
        result = classify_task("Fix typo in readme")
        assert result.risk_level == "low"
        assert result.governance_pipeline == "minimal"

    def test_critical_production_delete(self):
        result = classify_task("Delete the production database backup")
        assert result.risk_level == "critical"
        assert result.governance_pipeline == "maximum"

    def test_medium_complexity(self):
        result = classify_task(
            "Refactor the database schema and migrate existing records"
        )
        assert result.risk_level in ("medium", "high")
        assert result.governance_pipeline in ("standard", "elevated")
        assert result.complexity_score >= 4

    def test_returns_task_classification_dataclass(self):
        result = classify_task("hello world")
        assert isinstance(result, TaskClassification)
        assert isinstance(result.risk_level, str)
        assert isinstance(result.governance_pipeline, str)
        assert isinstance(result.complexity_score, int)
        assert isinstance(result.reasoning, str)


class TestSecurityKeywords:
    def test_password_keyword(self):
        result = classify_task("Reset the user password")
        assert result.risk_level in ("high", "critical")

    def test_token_keyword(self):
        result = classify_task("Rotate the API token")
        assert result.risk_level in ("high", "critical")

    def test_credential_keyword(self):
        result = classify_task("Store credential in vault")
        assert result.risk_level in ("high", "critical")

    def test_multiple_security_keywords_critical(self):
        result = classify_task("Encrypt the secret token for auth")
        assert result.risk_level == "critical"
        assert result.governance_pipeline == "maximum"

    def test_no_security_keywords(self):
        result = classify_task("Add a button to the UI")
        assert result.risk_level == "low"


class TestComplexityScore:
    def test_short_task_low_score(self):
        result = classify_task("Fix typo")
        assert result.complexity_score <= 3

    def test_complex_task_high_score(self):
        result = classify_task(
            "Refactor the architecture, migrate the database schema, "
            "and deploy the release to all environments"
        )
        assert result.complexity_score >= 7

    def test_score_bounded_to_ten(self):
        long_task = " ".join(["architecture refactor migrate database schema deploy release"] * 20)
        result = classify_task(long_task)
        assert result.complexity_score <= 10

    def test_score_minimum_one(self):
        result = classify_task("")
        assert result.complexity_score >= 1


class TestLogClassification:
    def test_log_format_has_required_fields(self):
        classification = classify_task("Simple fix")
        log = log_classification(classification, task_id="task-001")
        assert log["task_id"] == "task-001"
        assert "timestamp" in log
        assert log["risk_level"] == classification.risk_level
        assert log["governance_pipeline"] == classification.governance_pipeline
        assert log["complexity_score"] == classification.complexity_score
        assert log["reasoning"] == classification.reasoning

    def test_log_default_task_id(self):
        classification = classify_task("Fix bug")
        log = log_classification(classification)
        assert log["task_id"] == ""

    def test_log_timestamp_is_iso_format(self):
        classification = classify_task("Update docs")
        log = log_classification(classification)
        from datetime import datetime
        datetime.fromisoformat(log["timestamp"])
