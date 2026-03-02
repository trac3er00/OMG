import io
import json
import sys
from datetime import datetime, timedelta, timezone
from importlib import util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ROOT / "hooks"
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def _load_agent_registry_module():
    module_path = ROOT / "hooks" / "_agent_registry.py"
    spec = util.spec_from_file_location("agent_registry_test_module", str(module_path))
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_agent_registry = _load_agent_registry_module()
resolve_agent = _agent_registry.resolve_agent
detect_available_models = _agent_registry.detect_available_models


def _load_circuit_breaker_module(tmp_path, monkeypatch):
    hook_path = ROOT / "hooks" / "circuit-breaker.py"
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo ok"},
        "tool_response": {"exitCode": 0},
    }
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "exit", lambda _code=0: None)

    spec = util.spec_from_file_location("circuit_breaker_test_module", str(hook_path))
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_agent_returns_none_for_empty_keywords():
    assert resolve_agent(set()) is None


def test_resolve_agent_matches_frontend_designer():
    result = resolve_agent({"css", "layout", "responsive"})
    assert result is not None
    assert result["name"] == "frontend-designer"


def test_resolve_agent_matches_security_auditor():
    result = resolve_agent({"auth", "jwt", "security"})
    assert result is not None
    assert result["name"] == "security-auditor"


def test_resolve_agent_returns_highest_scoring_match():
    result = resolve_agent({"api", "server", "endpoint", "auth"})
    assert result is not None
    assert result["name"] == "backend-engineer"


def test_detect_available_models_always_has_claude_enabled():
    models = detect_available_models()
    assert models.get("claude") is True


def test_effective_count_applies_half_weight_for_old_failures(tmp_path, monkeypatch):
    module = _load_circuit_breaker_module(tmp_path, monkeypatch)
    now = datetime.now(timezone.utc)
    entry = {
        "count": 6,
        "last_failure": (now - timedelta(minutes=31)).isoformat(),
    }
    assert module._effective_count(entry, now) == 3.0


def test_get_domain_hint_matches_known_prefix(tmp_path, monkeypatch):
    module = _load_circuit_breaker_module(tmp_path, monkeypatch)
    assert module._get_domain_hint("Bash:pytest tests/test_agent_routing.py -v") == "codex"
    assert module._get_domain_hint("Read:README.md") == ""
