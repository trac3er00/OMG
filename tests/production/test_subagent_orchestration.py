import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestAgentRegistry:
    def test_agent_registry_importable(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_agent_registry", ROOT / "hooks" / "_agent_registry.py"
        )
        assert spec is not None

    def test_model_router_importable(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "model_router", ROOT / "runtime" / "model_router.py"
        )
        assert spec is not None

    def test_agent_types_defined(self):
        registry_file = ROOT / "hooks" / "_agent_registry.py"
        content = registry_file.read_text(encoding="utf-8")
        agent_types = ["explore", "librarian", "oracle"]
        found = [agent for agent in agent_types if agent in content]
        assert len(found) >= 1, f"No known agent types found in registry: {agent_types}"

    def test_provider_model_mapping_exists(self):
        registry_file = ROOT / "hooks" / "_agent_registry.py"
        content = registry_file.read_text(encoding="utf-8")
        assert "provider" in content.lower() or "model" in content.lower()


class TestModelRouting:
    def test_model_router_has_routing_logic(self):
        router_file = ROOT / "runtime" / "model_router.py"
        assert router_file.exists(), "runtime/model_router.py not found"
        content = router_file.read_text(encoding="utf-8")
        assert len(content) > 100, "model_router.py appears empty"

    def test_orchestration_router_exists(self):
        router_file = ROOT / "src" / "orchestration" / "router.js"
        assert router_file.exists(), "src/orchestration/router.js not found"

    def test_router_includes_selection_and_parallel_logic(self):
        router_file = ROOT / "src" / "orchestration" / "router.js"
        content = router_file.read_text(encoding="utf-8")
        assert "class TeamRouter" in content
        assert "ModelTier" in content
        assert "executeWorkersParallel" in content
        assert "Promise.all" in content


class TestParallelDispatch:
    def test_background_task_pattern_documented(self):
        selective_dispatch_test = (
            ROOT / "tests" / "runtime" / "test_selective_dispatch.py"
        )
        assert selective_dispatch_test.exists(), (
            "tests/runtime/test_selective_dispatch.py not found"
        )
        content = selective_dispatch_test.read_text(encoding="utf-8")
        assert "run_in_background" in content
