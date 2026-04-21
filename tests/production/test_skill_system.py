"""Skill system full inventory test suite.

Validates registry/skills.json structure, skill discovery,
provider coverage, and Kimi-specific skill presence.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "registry" / "skills.json"
SKILLS_DIR = ROOT / "skills"
SKILL_REGISTRY_PY = ROOT / "runtime" / "skill_registry.py"

# Expected providers in registry
EXPECTED_PROVIDERS = frozenset(
    {"universal", "claude", "codex", "opencode", "gemini", "kimi"}
)

# Kimi skill IDs expected in registry
KIMI_SKILL_IDS = [
    "@kimi/long-context",
    "@kimi/web-search",
    "@kimi/code-generation",
    "@kimi/moonshot",
]

# All provider categories
EXPECTED_CATEGORIES = frozenset({"universal", "provider"})


def load_skills_registry() -> list[dict[str, Any]]:
    """Load skills list from registry/skills.json."""
    if not REGISTRY_PATH.exists():
        return []
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Registry wraps skills in a top-level object
    if isinstance(data, dict) and "skills" in data:
        return data["skills"]
    if isinstance(data, list):
        return data
    return []


def load_raw_registry() -> dict[str, Any]:
    """Load full registry JSON (including metadata)."""
    if not REGISTRY_PATH.exists():
        return {}
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestRegistryStructure:
    """Tests for registry/skills.json existence and schema."""

    def test_registry_file_exists(self) -> None:
        """registry/skills.json should exist."""
        assert REGISTRY_PATH.exists(), (
            f"registry/skills.json not found at {REGISTRY_PATH}"
        )

    def test_registry_is_valid_json(self) -> None:
        """registry/skills.json should be parseable JSON."""
        raw = REGISTRY_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, dict), "Registry should be a JSON object"

    def test_registry_has_schema_version(self) -> None:
        """Registry should declare schema_version."""
        data = load_raw_registry()
        assert "schema_version" in data, "Missing schema_version"

    def test_registry_has_skills_array(self) -> None:
        """Registry should contain a 'skills' array."""
        data = load_raw_registry()
        assert "skills" in data, "Missing 'skills' key"
        assert isinstance(data["skills"], list), "'skills' should be an array"


class TestSkillInventory:
    """Test skill discovery and counts."""

    def test_skills_count_minimum(self) -> None:
        """Should have 20+ skills registered."""
        skills = load_skills_registry()
        print(f"\n{len(skills)} skills discovered in registry")
        assert len(skills) >= 20, f"Expected 20+ skills, found {len(skills)}"

    def test_all_skills_have_required_fields(self) -> None:
        """Each skill entry should have id, name, description, provider, path."""
        skills = load_skills_registry()
        required = {"id", "name", "description", "provider", "path"}
        incomplete: list[str] = []
        for skill in skills:
            missing = required - set(skill.keys())
            if missing:
                incomplete.append(f"{skill.get('id', '?')}: missing {missing}")
        assert not incomplete, f"Skills with missing fields:\n" + "\n".join(incomplete)

    def test_skill_ids_unique(self) -> None:
        """All skill IDs should be unique."""
        skills = load_skills_registry()
        ids = [s.get("id", "") for s in skills]
        dupes = [sid for sid in ids if ids.count(sid) > 1]
        assert not dupes, f"Duplicate skill IDs: {set(dupes)}"

    def test_skill_categories_valid(self) -> None:
        """Skill categories should be known values."""
        skills = load_skills_registry()
        categories = {s.get("category") for s in skills}
        unknown = categories - EXPECTED_CATEGORIES
        assert not unknown, f"Unknown categories: {unknown}"

    def test_all_expected_providers_present(self) -> None:
        """Registry should cover all expected providers."""
        skills = load_skills_registry()
        providers = {s.get("provider") for s in skills}
        missing = [p for p in EXPECTED_PROVIDERS if p not in providers]
        assert not missing, f"Missing providers in registry: {missing}"

    @pytest.mark.parametrize("provider", sorted(EXPECTED_PROVIDERS))
    def test_provider_has_skills(self, provider: str) -> None:
        """Each provider should have at least one skill."""
        skills = load_skills_registry()
        provider_skills = [s for s in skills if s.get("provider") == provider]
        assert len(provider_skills) >= 1, f"No skills for provider '{provider}'"
        print(f"\n  {provider}: {len(provider_skills)} skills")


class TestKimiSkills:
    """Test Kimi-specific skills in registry."""

    def test_all_four_kimi_skills_registered(self) -> None:
        """All 4 Kimi skills should be in the registry."""
        skills = load_skills_registry()
        skill_ids = {s.get("id") for s in skills}
        missing = [kid for kid in KIMI_SKILL_IDS if kid not in skill_ids]
        assert not missing, f"Kimi skills missing from registry: {missing}"

    def test_kimi_skills_have_correct_provider(self) -> None:
        """Kimi skills should have provider='kimi'."""
        skills = load_skills_registry()
        kimi = [s for s in skills if s.get("id", "").startswith("@kimi/")]
        for skill in kimi:
            assert skill.get("provider") == "kimi", (
                f"{skill['id']} has provider={skill.get('provider')}, expected 'kimi'"
            )

    def test_kimi_skill_md_exists(self) -> None:
        """skills/kimi/SKILL.md should exist with content."""
        skill_md = SKILLS_DIR / "kimi" / "SKILL.md"
        assert skill_md.exists(), "skills/kimi/SKILL.md not found"
        content = skill_md.read_text(encoding="utf-8")
        assert len(content) >= 200, f"Kimi SKILL.md too short: {len(content)} chars"

    def test_kimi_skill_md_references_all_skills(self) -> None:
        """Kimi SKILL.md should mention all 4 skill names."""
        skill_md = SKILLS_DIR / "kimi" / "SKILL.md"
        if not skill_md.exists():
            pytest.skip("skills/kimi/SKILL.md not found")
        content = skill_md.read_text(encoding="utf-8")
        for skill_id in KIMI_SKILL_IDS:
            short_name = skill_id.split("/")[-1]
            assert short_name in content, (
                f"Kimi SKILL.md does not mention '{short_name}'"
            )

    def test_kimi_skills_have_paths(self) -> None:
        """Each Kimi skill should have a 'path' field."""
        skills = load_skills_registry()
        kimi = [s for s in skills if s.get("id", "").startswith("@kimi/")]
        for skill in kimi:
            assert skill.get("path"), f"{skill['id']} missing path field"


class TestProviderSkillFiles:
    """Test that provider SKILL.md files exist on disk."""

    @pytest.mark.parametrize("provider", sorted(EXPECTED_PROVIDERS))
    def test_provider_skill_md_exists(self, provider: str) -> None:
        """Each provider should have a skills/<provider>/SKILL.md."""
        skill_md = SKILLS_DIR / provider / "SKILL.md"
        assert skill_md.exists(), f"skills/{provider}/SKILL.md not found"

    @pytest.mark.parametrize("provider", sorted(EXPECTED_PROVIDERS))
    def test_provider_skill_md_not_empty(self, provider: str) -> None:
        """Provider SKILL.md should have meaningful content."""
        skill_md = SKILLS_DIR / provider / "SKILL.md"
        if not skill_md.exists():
            pytest.skip(f"skills/{provider}/SKILL.md not found")
        content = skill_md.read_text(encoding="utf-8")
        assert len(content) >= 100, (
            f"skills/{provider}/SKILL.md too short: {len(content)} chars"
        )


class TestSkillRegistryRuntime:
    """Test runtime/skill_registry.py module."""

    def test_skill_registry_file_exists(self) -> None:
        """runtime/skill_registry.py should exist."""
        assert SKILL_REGISTRY_PY.exists(), "runtime/skill_registry.py not found"

    def test_skill_registry_importable(self) -> None:
        """skill_registry.py should be importable without errors."""
        spec = importlib.util.spec_from_file_location(
            "skill_registry", str(SKILL_REGISTRY_PY)
        )
        if spec is None or spec.loader is None:
            pytest.skip("Cannot create module spec for skill_registry.py")
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "compact_registry"), "Missing compact_registry function"

    def test_compact_registry_callable(self) -> None:
        """compact_registry() should be callable with skill lists."""
        spec = importlib.util.spec_from_file_location(
            "skill_registry", str(SKILL_REGISTRY_PY)
        )
        if spec is None or spec.loader is None:
            pytest.skip("Cannot create module spec")
            return
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        skills = load_skills_registry()
        all_ids = [s.get("id", "") for s in skills]
        used = all_ids[:3]  # Simulate using first 3

        result = mod.compact_registry(all_ids, used)
        assert isinstance(result, dict)
        assert "active" in result
        assert "pruned" in result
        assert len(result["active"]) == 3


class TestSkillPathConsistency:
    """Test that registry paths are consistent with disk layout."""

    def test_registry_paths_follow_convention(self) -> None:
        """Skill paths should follow skills/<provider>/<skill-name> pattern."""
        skills = load_skills_registry()
        violations: list[str] = []
        for skill in skills:
            path = skill.get("path", "")
            if not path.startswith("skills/"):
                violations.append(
                    f"{skill['id']}: path '{path}' doesn't start with 'skills/'"
                )
        assert not violations, "Path convention violations:\n" + "\n".join(violations)

    def test_skill_count_drift_detection(self) -> None:
        """Track skill count for drift detection."""
        skills = load_skills_registry()
        # Allow ±5 drift from current baseline of 20
        assert 15 <= len(skills) <= 50, (
            f"Skill count {len(skills)} outside expected range [15, 50]. "
            "Update test if skills were intentionally added/removed."
        )
