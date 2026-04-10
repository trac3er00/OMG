import os
import pytest
from runtime.autoresearch_engine import (
    DaemonConfig,
    SecurityEnvelope,
    start_daemon,
    stop_daemon,
)


class TestDaemonLifecycle:
    def test_start_writes_pid_and_stop_clears(self, tmp_path):
        pid_file = str(tmp_path / "daemon.pid")
        output_dir = str(tmp_path / "output")
        config = DaemonConfig(pid_file=pid_file, output_dir=output_dir)

        result = start_daemon(config)
        assert result["status"] == "started"
        assert result["pid"] == os.getpid()
        assert os.path.exists(pid_file)
        assert config.read_pid() == os.getpid()

        result = stop_daemon(config)
        assert result["status"] == "stopped"
        assert not os.path.exists(pid_file)

    def test_start_creates_output_dir(self, tmp_path):
        output_dir = str(tmp_path / "nested" / "output")
        config = DaemonConfig(
            pid_file=str(tmp_path / "daemon.pid"),
            output_dir=output_dir,
        )
        start_daemon(config)
        assert os.path.isdir(output_dir)

    def test_is_running_false_when_no_pid_file(self, tmp_path):
        config = DaemonConfig(pid_file=str(tmp_path / "nonexistent.pid"))
        assert config.is_running() is False

    def test_is_running_true_for_current_process(self, tmp_path):
        pid_file = str(tmp_path / "daemon.pid")
        config = DaemonConfig(pid_file=pid_file)
        config.write_pid(os.getpid())
        assert config.is_running() is True

    def test_is_running_false_for_dead_pid(self, tmp_path):
        pid_file = str(tmp_path / "daemon.pid")
        config = DaemonConfig(pid_file=pid_file)
        config.write_pid(99999999)
        assert config.is_running() is False

    def test_read_pid_returns_none_for_invalid(self, tmp_path):
        pid_file = str(tmp_path / "daemon.pid")
        os.makedirs(os.path.dirname(pid_file), exist_ok=True)
        with open(pid_file, "w") as f:
            f.write("not-a-number")
        config = DaemonConfig(pid_file=pid_file)
        assert config.read_pid() is None

    def test_clear_pid_noop_when_missing(self, tmp_path):
        config = DaemonConfig(pid_file=str(tmp_path / "nonexistent.pid"))
        config.clear_pid()


class TestSecurityEnvelope:
    def test_token_budget_enforced(self):
        env = SecurityEnvelope(max_tokens=100)
        assert env.check_token_budget(50) is True
        assert env.check_token_budget(101) is False

    def test_use_tokens_updates_tracking(self):
        env = SecurityEnvelope(max_tokens=100)
        env.use_tokens(30)
        assert env.tokens_used == 30
        env.use_tokens(20)
        assert env.tokens_used == 50
        assert env.check_token_budget(51) is False
        assert env.check_token_budget(50) is True

    def test_blocked_url_localhost(self):
        env = SecurityEnvelope()
        assert env.check_url("http://localhost:8080/api") is False
        assert env.check_url("http://127.0.0.1/data") is False
        assert env.check_url("http://internal.corp/secret") is False

    def test_allowed_url_external(self):
        env = SecurityEnvelope()
        assert env.check_url("https://example.com/api") is True
        assert env.check_url("https://github.com/repo") is True

    def test_no_code_execution(self):
        env = SecurityEnvelope()
        assert env.allow_code_execution is False
        env2 = SecurityEnvelope(allow_code_execution=False)
        assert env2.allow_code_execution is False

    def test_is_within_budget(self):
        env = SecurityEnvelope(max_tokens=100, max_web_requests=5)
        assert env.is_within_budget() is True
        env.tokens_used = 101
        assert env.is_within_budget() is False
        env.tokens_used = 50
        env.web_requests_made = 6
        assert env.is_within_budget() is False

    def test_to_dict(self):
        env = SecurityEnvelope(max_tokens=1000)
        env.use_tokens(250)
        d = env.to_dict()
        assert d["max_tokens"] == 1000
        assert d["tokens_used"] == 250
        assert d["allow_code_execution"] is False
        assert d["budget_remaining_pct"] == pytest.approx(0.75)


class TestDaemonConfigDefaults:
    def test_default_security_envelope(self):
        config = DaemonConfig()
        assert isinstance(config.security, SecurityEnvelope)
        assert config.security.allow_code_execution is False

    def test_default_interval(self):
        config = DaemonConfig()
        assert config.interval_seconds == 300

    def test_not_running_by_default(self):
        config = DaemonConfig()
        assert config.running is False
