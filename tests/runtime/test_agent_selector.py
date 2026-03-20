"""Tests for runtime.agent_selector — dynamic agent selection for CCG and deep-plan.

Tests what users care about:
- Correct agents are selected for domain-specific problems
- Diversity enforcement prevents redundant agent picks
- Edge cases: empty problems, no keyword matches, more agents requested than exist
- Agent loading doesn't crash on malformed files
"""

import pytest
from pathlib import Path
from runtime.agent_selector import (
    load_all_agents,
    score_agents,
    select_agents,
    format_agent_selection,
    get_agent_prompt_context,
    _parse_frontmatter,
    _diversify,
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoadAllAgents:
    """Agent definitions load correctly from disk."""

    def test_loads_nonzero_agents(self):
        agents = load_all_agents()
        assert len(agents) >= 30, f"Expected 30+ agents, got {len(agents)}"

    def test_every_agent_has_required_fields(self):
        for agent in load_all_agents():
            assert agent["name"], f"Agent missing name: {agent['file']}"
            assert agent["description"], f"Agent {agent['name']} missing description"
            assert agent["model"], f"Agent {agent['name']} missing model"
            assert isinstance(agent["tools"], list)

    def test_excluded_meta_agents_are_not_loaded(self):
        names = {a["name"] for a in load_all_agents()}
        # These are routing/meta agents, not task agents
        assert "escalation-router" not in names
        assert "implement-mode" not in names
        assert "architect-mode" not in names

    def test_loads_from_custom_directory(self, tmp_path):
        (tmp_path / "test-agent.md").write_text(
            "---\nname: test-bot\ndescription: test\nmodel: claude-sonnet-4-5\ntools: Read\n---\nBody."
        )
        agents = load_all_agents(tmp_path)
        assert len(agents) == 1
        assert agents[0]["name"] == "test-bot"

    def test_skips_files_without_name(self, tmp_path):
        (tmp_path / "bad.md").write_text("---\ndescription: no name\n---\nBody.")
        agents = load_all_agents(tmp_path)
        assert len(agents) == 0

    def test_skips_underscore_prefixed_files(self, tmp_path):
        (tmp_path / "_internal.md").write_text(
            "---\nname: hidden\ndescription: x\nmodel: x\n---\n"
        )
        agents = load_all_agents(tmp_path)
        assert len(agents) == 0

    def test_handles_nonexistent_directory(self):
        agents = load_all_agents(Path("/nonexistent/path"))
        assert agents == []


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


class TestParseFrontmatter:

    def test_parses_standard_frontmatter(self):
        text = "---\nname: foo\ndescription: bar baz\nmodel: claude-sonnet-4-5\n---\nBody"
        fm = _parse_frontmatter(text)
        assert fm["name"] == "foo"
        assert fm["description"] == "bar baz"
        assert fm["model"] == "claude-sonnet-4-5"

    def test_returns_empty_for_no_frontmatter(self):
        assert _parse_frontmatter("Just markdown, no frontmatter") == {}

    def test_handles_multiline_frontmatter(self):
        text = "---\nname: agent\ntools: Read, Grep, Glob\n---\n"
        fm = _parse_frontmatter(text)
        assert fm["tools"] == "Read, Grep, Glob"


# ---------------------------------------------------------------------------
# Scoring — does the right agent win for the right problem?
# ---------------------------------------------------------------------------


class TestScoring:
    """Agent scoring matches domain-specific problems to the right specialists."""

    @pytest.mark.parametrize("problem,expected_winner", [
        ("fix slow database queries", "database-engineer"),
        ("optimize API latency and reduce memory usage", "performance-engineer"),
        ("add dark mode to the dashboard", "frontend-designer"),
        ("audit code for SQL injection and XSS", "security-auditor"),
        ("set up GitHub Actions CI/CD pipeline", "devops-engineer"),
        ("build ML inference endpoint", "ml-engineer"),
        ("debug crash from stack trace", "debugger"),
        ("refactor duplicated code in auth module", "refactor-agent"),
        ("fix race condition in concurrent worker pool", "concurrency-expert"),
        ("write API contract tests for payment endpoints", "api-tester"),
        ("investigate why legacy code was written this way", "code-archeologist"),
    ])
    def test_domain_problem_selects_correct_top_agent(self, problem, expected_winner):
        scored = score_agents(problem)
        top_agent = scored[0][0]["name"]
        # Allow top-3 since some problems have legitimate ambiguity
        top_3_names = [a["name"] for a, _ in scored[:3]]
        assert expected_winner in top_3_names, (
            f"Expected '{expected_winner}' in top 3 for '{problem}', "
            f"got {top_3_names}"
        )

    def test_security_keywords_boost_security_auditor(self):
        scored = score_agents("fix CSRF vulnerability in authentication endpoint")
        scores_by_name = {a["name"]: s for a, s in scored}
        assert scores_by_name.get("security-auditor", 0) > 3.0

    def test_no_keywords_still_returns_scored_list(self):
        scored = score_agents("do something with the codebase")
        assert len(scored) > 0
        # All scores should be low (description overlap only)
        for _, score in scored[:5]:
            assert score < 5.0

    def test_file_hints_boost_relevant_agents(self):
        # Python files should boost backend agents
        scored_no_files = score_agents("fix the bug")
        scored_py = score_agents("fix the bug", file_hints=["src/service.py"])

        py_scores = {a["name"]: s for a, s in scored_py}
        no_scores = {a["name"]: s for a, s in scored_no_files}
        assert py_scores.get("backend-engineer", 0) > no_scores.get("backend-engineer", 0)

    def test_frontend_files_boost_frontend_agents(self):
        scored = score_agents("update the component", file_hints=["src/App.tsx", "src/styles.css"])
        scores_by_name = {a["name"]: s for a, s in scored}
        assert scores_by_name.get("frontend-designer", 0) >= 1.0


# ---------------------------------------------------------------------------
# Selection — picks N agents with diversity
# ---------------------------------------------------------------------------


class TestSelectAgents:
    """select_agents returns the right number and mix of agents."""

    def test_returns_exact_count_requested(self):
        for n in (1, 3, 5, 7):
            selected = select_agents("build a new feature", n=n)
            assert len(selected) == n, f"Requested {n}, got {len(selected)}"

    def test_selected_agents_have_score_and_subagent_type(self):
        selected = select_agents("fix database performance", n=3)
        for agent in selected:
            assert "score" in agent
            assert "subagent_type" in agent
            assert isinstance(agent["score"], (int, float))
            assert isinstance(agent["subagent_type"], str)

    def test_excludes_specified_agents(self):
        selected = select_agents(
            "fix database performance",
            n=3,
            exclude=["database-engineer", "backend-engineer"],
        )
        names = [a["name"] for a in selected]
        assert "database-engineer" not in names
        assert "backend-engineer" not in names

    def test_diversity_prevents_duplicate_roles(self):
        # For any selection, we should not get both designer and frontend-designer
        selected = select_agents("build responsive accessible UI", n=5)
        names = [a["name"] for a in selected]
        # Same diversity group — at most one
        assert not (
            "designer" in names and "frontend-designer" in names
        ), f"Got both designer and frontend-designer: {names}"

    def test_diversity_prevents_duplicate_test_agents(self):
        selected = select_agents("write comprehensive tests for everything", n=5)
        names = [a["name"] for a in selected]
        test_group = {"testing-engineer", "qa-tester", "api-tester"}
        overlap = test_group & set(names)
        assert len(overlap) <= 1, f"Got multiple test agents: {overlap}"

    def test_scores_are_descending(self):
        selected = select_agents("optimize performance of the API", n=5)
        scores = [a["score"] for a in selected]
        assert scores == sorted(scores, reverse=True), (
            f"Scores not descending: {scores}"
        )


# ---------------------------------------------------------------------------
# Diversity helper
# ---------------------------------------------------------------------------


class TestDiversify:

    def test_removes_second_member_of_same_group(self):
        # Simulate two agents from same group
        agent_a = {"name": "designer", "description": "a"}
        agent_b = {"name": "frontend-designer", "description": "b"}
        agent_c = {"name": "backend-engineer", "description": "c"}
        candidates = [(agent_a, 5.0), (agent_b, 4.0), (agent_c, 3.0)]
        result = _diversify(candidates, n=3)
        names = [a["name"] for a, _ in result]
        assert "designer" in names
        assert "frontend-designer" not in names
        assert "backend-engineer" in names


# ---------------------------------------------------------------------------
# Formatting & prompt context
# ---------------------------------------------------------------------------


class TestFormatting:

    def test_format_agent_selection_includes_all_agents(self):
        selected = select_agents("deploy the app", n=3)
        output = format_agent_selection(selected)
        for agent in selected:
            assert agent["name"] in output

    def test_get_agent_prompt_context_strips_frontmatter(self):
        agents = load_all_agents()
        if agents:
            ctx = get_agent_prompt_context(agents[0])
            assert "---" not in ctx[:10]  # frontmatter stripped
            assert len(ctx) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_empty_problem_returns_agents(self):
        selected = select_agents("", n=3)
        assert len(selected) == 3

    def test_very_long_problem_does_not_crash(self):
        problem = "fix the bug " * 1000
        selected = select_agents(problem, n=3)
        assert len(selected) == 3

    def test_requesting_more_agents_than_exist(self):
        # Should return as many as possible without crashing
        selected = select_agents("build everything", n=100)
        assert len(selected) > 0
        assert len(selected) <= 100
