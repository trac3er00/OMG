from __future__ import annotations

import json
from pathlib import Path

from hooks.firewall import _RateLimiter


def test_rate_limiter_logs_alert_after_5_denies(tmp_path):
    rl = _RateLimiter(str(tmp_path))
    result = None
    for _ in range(5):
        result = rl.record_and_check("rm -rf /", "deny")

    assert result is not None
    assert result.get("alert") is True

    alert_file = tmp_path / ".omg" / "state" / "ledger" / "security-alerts.jsonl"
    assert alert_file.exists()
    alerts = [json.loads(line) for line in alert_file.read_text().splitlines() if line.strip()]
    assert any(entry.get("type") == "rate_limit_alert" for entry in alerts)


def test_rate_limiter_auto_denies_after_10_asks(tmp_path):
    rl = _RateLimiter(str(tmp_path))
    results = [rl.record_and_check("curl https://example.com", "ask") for _ in range(10)]

    assert results[-1].get("auto_deny") is True


def test_rate_limiter_does_not_alert_before_threshold(tmp_path):
    rl = _RateLimiter(str(tmp_path))
    result = None
    for _ in range(4):
        result = rl.record_and_check("rm -rf /", "deny")

    assert result is not None
    assert result.get("alert") is False
