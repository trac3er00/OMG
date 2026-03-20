from importlib import util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_agent_registry_module():
    module_path = ROOT / "hooks" / "_agent_registry.py"
    spec = util.spec_from_file_location("agent_registry_for_tests", str(module_path))
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_agent_registry = _load_agent_registry_module()
resolve_agent = _agent_registry.resolve_agent
get_dispatch_params = _agent_registry.get_dispatch_params
detect_available_models = _agent_registry.detect_available_models
discover_mcp_tools = _agent_registry.discover_mcp_tools
AGENT_REGISTRY = _agent_registry.AGENT_REGISTRY
CORE_AGENT_MODELS = _agent_registry.CORE_AGENT_MODELS


def _load_setup_wizard_module():
    module_path = ROOT / "hooks" / "setup_wizard.py"
    spec = util.spec_from_file_location("setup_wizard_for_tests", str(module_path))
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resolve_agent_security_keywords():
    result = resolve_agent({'auth', 'jwt', 'vulnerability'})
    assert result is not None
    assert result['preferred_model'] == 'codex-cli'
    assert result['name'] == 'security-auditor'


def test_resolve_agent_ui_keywords():
    result = resolve_agent({'css', 'layout', 'responsive'})
    assert result is not None
    assert result['preferred_model'] == 'gemini-cli'
    assert result['name'] == 'frontend-designer'


def test_resolve_agent_no_match():
    result = resolve_agent({'completely', 'unrelated', 'words'})
    assert result is None


def test_detect_available_models_always_has_claude():
    models = detect_available_models()
    assert 'claude' in models
    assert models['claude'] is True


def test_get_dispatch_params_returns_category():
    params = get_dispatch_params('backend-engineer')
    assert 'category' in params
    assert params['category'] == 'deep'


def test_get_dispatch_params_fallback_when_model_unavailable():
    # Even if codex not available, should not crash
    params = get_dispatch_params('backend-engineer')
    assert 'preferred_model' in params
    assert params['preferred_model'] in ('codex-cli', 'claude')


def test_registry_has_17_agents():
    assert len(AGENT_REGISTRY) == 17  # 10 original + 6 bundled + release-engineer


def test_registry_includes_api_builder_agent():
    api_builder = AGENT_REGISTRY.get('api-builder')
    assert api_builder is not None
    assert api_builder['preferred_model'] == 'codex-cli'
    assert api_builder['task_category'] == 'deep'


def test_all_agents_have_required_fields():
    required = {'preferred_model', 'task_category', 'skills', 'trigger_keywords', 'description'}
    for name, config in AGENT_REGISTRY.items():
        for field in required:
            assert field in config, f"Agent {name} missing field {field}"


def test_discover_mcp_tools_returns_list():
    tools = discover_mcp_tools()
    assert isinstance(tools, list)


def test_discover_mcp_tools_reads_user_claude_mcp_json(monkeypatch, tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    home_dir = tmp_path / "home"
    claude_dir = home_dir / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"context7": {}, "websearch": {}}}),
        encoding="utf-8",
    )

    monkeypatch.chdir(project_dir)
    monkeypatch.setenv("HOME", str(home_dir))

    tools = discover_mcp_tools()
    assert set(tools) == {"context7", "websearch"}


def test_all_agents_have_model_version():
    for name, config in AGENT_REGISTRY.items():
        assert 'model_version' in config, f"Agent {name} missing model_version"
        assert config['model_version'], f"Agent {name} has empty model_version"


def test_all_agent_skills_are_from_supported_catalog():
    supported_skills = {
        "api-design",
        "backend-patterns",
        "docker-patterns",
        "e2e-testing",
        "frontend-design",
        "frontend-patterns",
        "python-testing",
        "security-review",
    }
    for name, config in AGENT_REGISTRY.items():
        for skill in config.get("skills", []):
            assert skill in supported_skills, f"Agent {name} references unknown skill {skill}"


def test_all_agent_mcp_tools_exist_in_supported_mcp_catalog():
    setup_wizard = _load_setup_wizard_module()
    available = {entry["id"] for entry in setup_wizard.get_mcp_catalog()}
    for name, config in AGENT_REGISTRY.items():
        for tool in config.get("mcp_tools", []):
            assert tool in available, f"Agent {name} references unknown MCP tool {tool}"


def test_core_agent_models_has_5_entries():
    assert len(CORE_AGENT_MODELS) == 5


def test_core_agents_have_model_version():
    for name, config in CORE_AGENT_MODELS.items():
        assert 'model_version' in config, f"Core agent {name} missing model_version"
        assert 'preferred_model' in config, f"Core agent {name} missing preferred_model"


def test_model_versions_are_specific():
    GENERIC = {'opus', 'sonnet', 'haiku', 'claude', 'codex', 'gemini', 'codex-cli', 'gemini-cli'}
    all_agents = {**AGENT_REGISTRY, **CORE_AGENT_MODELS}
    for name, config in all_agents.items():
        v = config.get('model_version', '')
        assert v not in GENERIC, f"{name} has generic model_version: {v}"
        assert v, f"{name} has empty model_version"
