# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false
from __future__ import annotations

import json
import importlib.util
import sysconfig
import sys
from pathlib import Path
import re
import warnings
from typing import Protocol, cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

sys.path.insert(0, str(ROOT / "scripts"))
import github_review_helpers as helpers  # noqa: E402


class _YamlLike(Protocol):
    def safe_load(self, stream: str) -> object: ...


def _load_pyyaml_module() -> _YamlLike:
    purelib = Path(sysconfig.get_paths()["purelib"])
    yaml_init = purelib / "yaml" / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "_omg_pyyaml",
        yaml_init,
        submodule_search_locations=[str(yaml_init.parent)],
    )
    assert spec is not None and spec.loader is not None, "PyYAML loader unavailable"
    module = importlib.util.module_from_spec(spec)
    sys.modules["_omg_pyyaml"] = module
    spec.loader.exec_module(module)
    return cast(_YamlLike, cast(object, module))


_PYYAML = _load_pyyaml_module()


def _read_workflow_text(name: str) -> str:
    return (WORKFLOW_DIR / name).read_text(encoding="utf-8")


def _section(text: str, start_marker: str, end_marker: str | None = None) -> str:
    start = text.find(start_marker)
    assert start >= 0, f"Missing marker: {start_marker}"
    if end_marker is None:
        return text[start:]
    end = text.find(end_marker, start)
    assert end >= 0, f"Missing end marker: {end_marker}"
    return text[start:end]


def _contains_secret_ref(text: str, key: str) -> bool:
    return f"secrets.{key}" in text


def _load_workflow(name: str) -> dict[object, object]:
    payload = _PYYAML.safe_load(_read_workflow_text(name))
    assert isinstance(payload, dict), f"{name} must parse to a mapping"
    return payload


def _workflow_on(payload: dict[object, object]) -> object:
    return payload.get("on", payload.get(True))


def _plugin_name(plugin_entry: object) -> str | None:
    if isinstance(plugin_entry, str):
        return plugin_entry
    if isinstance(plugin_entry, list) and plugin_entry and isinstance(plugin_entry[0], str):
        return plugin_entry[0]
    return None


def _has_release_push_branch(push_config: object) -> bool:
    if not isinstance(push_config, dict):
        return False
    branches = push_config.get("branches")
    if isinstance(branches, str):
        branches = [branches]
    if not isinstance(branches, list):
        return False

    for branch in branches:
        if not isinstance(branch, str):
            continue
        normalized = branch.lower()
        if normalized.startswith("release") or normalized in {"main", "master"}:
            return True
    return False


def test_all_target_workflows_define_concurrency() -> None:
    text = _read_workflow_text("publish-npm.yml")
    assert re.search(
        r"^concurrency:\n  group: \$\{\{ github\.workflow \}\}-\$\{\{ github\.ref \}\}\n  cancel-in-progress: true",
        text,
        flags=re.MULTILINE,
    )

    for workflow_name in ("omg-compat-gate.yml", "omg-release-readiness.yml"):
        text = _read_workflow_text(workflow_name)
        assert "github.event.issue.number || github.ref" in text
        assert "cancel-in-progress: true" in text


def test_compat_workflow_has_split_pr_analyze_and_trusted_post_review_jobs() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    assert "  pr-analyze:\n" in text
    assert "  post-review:\n" in text

    pr_analyze = _section(text, "  pr-analyze:\n", "  post-review:\n")
    post_review = _section(text, "  post-review:\n", "  compat-gate:\n")

    assert "permissions:\n      contents: read" in pr_analyze
    assert not _contains_secret_ref(pr_analyze, "GITHUB_APP_ID")
    assert not _contains_secret_ref(pr_analyze, "GITHUB_APP_PRIVATE_KEY")
    assert not _contains_secret_ref(pr_analyze, "GITHUB_INSTALLATION_ID")

    assert "pull-requests: write" in post_review
    assert "checks: write" in post_review
    assert _contains_secret_ref(post_review, "OMG_APP_ID") or _contains_secret_ref(post_review, "GITHUB_APP_ID")
    assert _contains_secret_ref(post_review, "OMG_APP_PRIVATE_KEY") or _contains_secret_ref(post_review, "GITHUB_APP_PRIVATE_KEY")
    assert _contains_secret_ref(post_review, "OMG_APP_INSTALLATION_ID") or _contains_secret_ref(post_review, "GITHUB_INSTALLATION_ID")


def test_trusted_post_review_lane_never_checks_out_pr_head() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    post_review = _section(text, "  post-review:\n", "  compat-gate:\n")
    assert "uses: actions/checkout@v4" in post_review
    assert "ref: ${{ needs.resolve-pr.outputs.base-sha }}" in post_review
    assert "head.sha" not in post_review


def test_fast_pr_blockers_reuse_uploaded_artifacts() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    pr_analyze = _section(text, "  pr-analyze:\n", "  post-review:\n")
    assert "uses: actions/download-artifact@v4" in pr_analyze
    assert "pattern: compat-*" in pr_analyze
    assert "scripts/github_review_helpers.py build-pr-handoff" in pr_analyze
    assert "scripts/github_review_helpers.py assert-pass" in pr_analyze
    assert "scripts/omg.py release readiness" not in pr_analyze


def test_release_readiness_workflow_uploads_reviewer_bot_handoff_artifact() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    assert "scripts/github_review_helpers.py build-release-handoff" in release_job
    assert "reviewer-bot-release-input" in release_job


def test_release_readiness_not_schedule_only_or_has_release_bridge() -> None:
    readiness = _load_workflow("omg-release-readiness.yml")
    readiness_on = _workflow_on(readiness)
    assert isinstance(readiness_on, dict), "omg-release-readiness.yml must define event triggers"

    has_workflow_dispatch = "workflow_dispatch" in readiness_on
    has_release_push = _has_release_push_branch(readiness_on.get("push"))
    if has_workflow_dispatch or has_release_push:
        return

    release_workflow_path = WORKFLOW_DIR / "release.yml"
    assert release_workflow_path.exists(), "release.yml must exist when readiness lacks dispatch/release push triggers"
    release_payload = _PYYAML.safe_load(release_workflow_path.read_text(encoding="utf-8"))
    assert isinstance(release_payload, dict), "release.yml must parse to a mapping"
    release_on = _workflow_on(release_payload)
    assert isinstance(release_on, dict), "release.yml must define event triggers"
    assert "workflow_dispatch" in release_on or _has_release_push_branch(release_on.get("push"))

    release_text = release_workflow_path.read_text(encoding="utf-8")
    bridge_markers = (
        "omg-release-readiness.yml",
        "release-readiness",
        "workflow_call",
        "gh workflow run omg-release-readiness.yml",
    )
    assert any(marker in release_text for marker in bridge_markers), "release.yml must call or gate release readiness"


def test_release_readiness_runs_on_pull_request() -> None:
    readiness = _load_workflow("omg-release-readiness.yml")
    readiness_on = _workflow_on(readiness)
    assert isinstance(readiness_on, dict), "omg-release-readiness.yml must define event triggers"
    assert "issue_comment" in readiness_on, "omg-release-readiness.yml must use issue_comment for manual PR coverage"
    assert "pull_request" not in readiness_on, "omg-release-readiness.yml must not auto-trigger on pull_request"


def test_compat_gate_has_doc_drift_check_before_reviewer_handoff() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    pr_analyze = _section(text, "  pr-analyze:\n", "  post-review:\n")
    drift_pos = pr_analyze.find("Run generated-doc drift check")
    handoff_pos = pr_analyze.find("Build reviewer bot handoff")
    assert drift_pos >= 0, "Missing 'Run generated-doc drift check' step in compat-gate pr-analyze job"
    assert handoff_pos >= 0, "Missing reviewer handoff step"
    assert drift_pos < handoff_pos, "Doc drift check must appear before reviewer handoff"
    assert "python3 scripts/omg.py docs generate --check" in pr_analyze


def test_release_readiness_has_doc_drift_check_before_release_handoff() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    drift_pos = release_job.find("Run generated-doc drift check")
    handoff_pos = release_job.find("Build reviewer bot release handoff artifact")
    assert drift_pos >= 0, "Missing 'Run generated-doc drift check' step in release-readiness"
    assert handoff_pos >= 0, "Missing release handoff step"
    assert drift_pos < handoff_pos, "Doc drift check must appear before release handoff"
    assert "python3 scripts/omg.py docs generate --check" in release_job


def test_post_review_runs_only_on_trusted_lane() -> None:
    workflow = _load_workflow("omg-compat-gate.yml")
    workflow_on = _workflow_on(workflow)
    assert isinstance(workflow_on, dict), "omg-compat-gate.yml must define triggers"

    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "omg-compat-gate.yml must define jobs"
    post_review = jobs.get("post-review")
    assert isinstance(post_review, dict), "post-review job must exist"

    if_condition = str(post_review.get("if", ""))
    trusted_if_markers = (
        "github.event_name != 'pull_request'",
        'github.event_name != "pull_request"',
        "github.event.pull_request.head.repo.full_name == github.repository",
        "github.event.pull_request.base.repo.full_name == github.repository",
    )
    has_trusted_if_guard = any(marker in if_condition for marker in trusted_if_markers)

    steps = post_review.get("steps")
    assert isinstance(steps, list), "post-review job must define steps"
    checkout_steps = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("uses") == "actions/checkout@v4"
    ]
    assert checkout_steps, "post-review must checkout trusted base surface"
    checkout_with_base_sha = any(
        isinstance(step.get("with"), dict)
        and str(step["with"].get("ref", "")) == "${{ needs.resolve-pr.outputs.base-sha }}"
        for step in checkout_steps
    )

    pull_request_enabled = "pull_request" in workflow_on
    if pull_request_enabled:
        assert has_trusted_if_guard or checkout_with_base_sha, (
            "post-review must exclude untrusted PR head (trusted if guard or base.sha checkout required)"
        )


def test_comment_triggered_workflows_resolve_pr_from_at_omg_comment() -> None:
    for workflow_name in ("omg-compat-gate.yml", "omg-release-readiness.yml"):
        workflow = _load_workflow(workflow_name)
        workflow_on = _workflow_on(workflow)
        assert isinstance(workflow_on, dict), f"{workflow_name} must define event triggers"
        assert "issue_comment" in workflow_on, f"{workflow_name} must accept issue_comment events"
        issue_comment = workflow_on["issue_comment"]
        assert isinstance(issue_comment, dict), f"{workflow_name} issue_comment trigger must be configured"
        assert issue_comment.get("types") == ["created"], f"{workflow_name} must only trigger on new comments"
        assert "pull_request" not in workflow_on, f"{workflow_name} must not auto-trigger on pull_request"

        jobs = workflow.get("jobs")
        assert isinstance(jobs, dict), f"{workflow_name} must define jobs"
        resolve_pr = jobs.get("resolve-pr")
        assert isinstance(resolve_pr, dict), f"{workflow_name} must define resolve-pr"
        resolve_if = str(resolve_pr.get("if", ""))
        assert "github.event_name == 'issue_comment'" in resolve_if
        assert "github.event.issue.pull_request" in resolve_if
        assert "contains(github.event.comment.body, '@omg')" in resolve_if
        assert "github.event.comment.author_association" in resolve_if
        for association in ("OWNER", "MEMBER", "COLLABORATOR"):
            assert association in resolve_if

        outputs = resolve_pr.get("outputs")
        assert isinstance(outputs, dict), f"{workflow_name} resolve-pr must export outputs"
        assert outputs.get("pr-number") == "${{ steps.pr.outputs.pr_number }}"
        assert outputs.get("head-sha") == "${{ steps.pr.outputs.head_sha }}"
        assert outputs.get("base-sha") == "${{ steps.pr.outputs.base_sha }}"


def test_comment_triggered_workflows_checkout_resolved_pr_head() -> None:
    for workflow_name in ("omg-compat-gate.yml", "omg-release-readiness.yml"):
        text = _read_workflow_text(workflow_name)
        assert "ref: ${{ needs.resolve-pr.outputs.head-sha || github.ref }}" in text


def test_compat_pr_review_jobs_use_synthesized_pr_event() -> None:
    text = _read_workflow_text("omg-compat-gate.yml")
    pr_analyze = _section(text, "  pr-analyze:\n", "  post-review:\n")
    post_review = _section(text, "  post-review:\n", "  compat-gate:\n")

    assert "needs.resolve-pr.result == 'success'" in pr_analyze
    assert "needs.resolve-pr.outputs.pr-number" in pr_analyze
    assert '--event-path "/tmp/pr-event.json"' in pr_analyze

    assert "needs.resolve-pr.result == 'success'" in post_review
    assert "needs.resolve-pr.outputs.pr-number" in post_review
    assert '--event-path "/tmp/pr-event.json"' in post_review


def test_pr_analyze_and_post_review_are_separate_jobs() -> None:
    workflow = _load_workflow("omg-compat-gate.yml")
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "omg-compat-gate.yml must define jobs"
    assert "pr-analyze" in jobs
    assert "post-review" in jobs
    assert "pr-analyze" != "post-review"


def test_semantic_release_config_if_present_has_required_fields() -> None:
    config_paths = [ROOT / ".releaserc.json", ROOT / ".releaserc.yml"]
    existing_path = next((path for path in config_paths if path.exists()), None)
    if existing_path is None:
        warnings.warn(
            "semantic-release config missing; Task 8 must add .releaserc with plugins ending in @semantic-release/git, CI fetch-depth: 0, and prepare sync-release-identity",
            stacklevel=2,
        )
        pytest.skip("semantic-release config not present yet; required release contract recorded for follow-up task")

    if existing_path.suffix == ".json":
        config: object = cast(object, json.loads(existing_path.read_text(encoding="utf-8")))
    else:
        config = _PYYAML.safe_load(existing_path.read_text(encoding="utf-8"))
    assert isinstance(config, dict), "semantic-release config must be a mapping"

    plugins = config.get("plugins")
    assert isinstance(plugins, list) and plugins, "semantic-release config must define a non-empty plugins list"
    last_plugin = _plugin_name(plugins[-1])
    assert last_plugin == "@semantic-release/git", "semantic-release plugins must end with @semantic-release/git"

    publish_text = _read_workflow_text("publish-npm.yml")
    assert "fetch-depth: 0" in publish_text, "CI workflow must checkout with fetch-depth: 0"

    prepare_sources = [
        json.dumps(config),
        _read_workflow_text("omg-release-readiness.yml"),
        publish_text,
    ]
    assert any("sync-release-identity" in source for source in prepare_sources), (
        "release pipeline must include a prepare step invoking sync-release-identity"
    )


def test_publish_workflow_requires_readiness_gate() -> None:
    workflow = _load_workflow("publish-npm.yml")
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "publish-npm.yml must define jobs"
    assert "release-readiness" in jobs, "publish workflow must define a release-readiness gate job"

    publish_job = jobs.get("publish")
    assert isinstance(publish_job, dict), "publish job must exist"
    needs = publish_job.get("needs")
    if isinstance(needs, str):
        needs = [needs]
    assert isinstance(needs, list), "publish job needs must be a list"
    assert "release-readiness" in needs, "publish job must depend on release-readiness"


def test_evidence_gate_reusable_workflow_exists_and_has_correct_structure() -> None:
    workflow = _load_workflow("evidence-gate.yml")
    on_triggers = _workflow_on(workflow)
    assert isinstance(on_triggers, dict), "evidence-gate.yml must define triggers"
    assert "workflow_call" in on_triggers, "evidence-gate.yml must use workflow_call trigger"

    call_config = on_triggers["workflow_call"]
    assert isinstance(call_config, dict), "workflow_call must have configuration"

    inputs = call_config.get("inputs", {})
    assert "repo-full-name" in inputs
    assert "pr-number" in inputs
    assert "head-sha" in inputs

    secrets = call_config.get("secrets", {})
    assert "GITHUB_APP_ID" in secrets
    assert "GITHUB_APP_PRIVATE_KEY" in secrets
    assert "GITHUB_INSTALLATION_ID" in secrets

    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "evidence-gate.yml must define jobs"
    assert "post-review" in jobs, "evidence-gate.yml must have a post-review job"

    text = _read_workflow_text("evidence-gate.yml")
    assert "pull_request" not in on_triggers, "evidence-gate.yml must not have non-reusable triggers"
    assert "push" not in on_triggers, "evidence-gate.yml must not have non-reusable triggers"
    assert "secrets.GITHUB_APP_ID" in text
    assert "secrets.GITHUB_APP_PRIVATE_KEY" in text
    assert "secrets.GITHUB_INSTALLATION_ID" in text


def test_evidence_gate_post_review_passes_event_path_arg() -> None:
    text = _read_workflow_text("evidence-gate.yml")
    assert "--event-path artifacts/reviewer-bot-pr-event.json" in text, (
        "evidence-gate.yml post-review step must pass --event-path artifacts/reviewer-bot-pr-event.json"
    )


def test_evidence_gate_post_review_passes_input_arg() -> None:
    text = _read_workflow_text("evidence-gate.yml")
    assert "--input artifacts/reviewer-bot-pr-input.json" in text, (
        "evidence-gate.yml post-review step must pass --input artifacts/reviewer-bot-pr-input.json"
    )


def test_github_review_helpers_build_pr_handoff_and_assert_pass(tmp_path: Path) -> None:
    event = {
        "action": "opened",
        "repository": {"full_name": "acme/omg"},
        "pull_request": {"number": 7, "head": {"sha": "abc123"}},
    }
    artifacts = tmp_path / "artifacts"
    (artifacts / "public/.omg/evidence").mkdir(parents=True)
    (artifacts / "public/dist/public").mkdir(parents=True)

    (artifacts / "omg-compat-gap.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "omg-compat-contracts.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "public/.omg/evidence/doctor.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "public/dist/public/manifest.json").write_text("{}\n", encoding="utf-8")
    (artifacts / "public/.omg/evidence/host-parity-run-1.json").write_text(
        json.dumps({"parity_results": {"passed": True}}),
        encoding="utf-8",
    )

    payload = helpers.build_pr_handoff(event, artifacts)
    assert payload["verdict"] == "pass"
    assert any(check["name"] == "identity" and check["status"] == "ok" for check in payload["checks"])
    assert any(check["name"] == "parity" and check["status"] == "ok" for check in payload["checks"])

    helpers.assert_pass(payload)


def test_release_readiness_has_drift_check_before_compile_step() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    drift_pos = release_job.find("Check release and docs drift")
    assert drift_pos >= 0, "Missing 'Check release and docs drift' step in release-readiness job"
    compile_pos = release_job.find("Compile")
    if compile_pos >= 0:
        assert drift_pos < compile_pos, "Drift check must appear before any compile step"


def test_release_readiness_no_self_healing_compile_step() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    assert "Compile release surfaces into output root" not in release_job, (
        "Self-healing 'Compile release surfaces into output root' step must be removed from release-readiness"
    )


def test_github_review_helpers_assert_pass_fails_when_required_artifacts_missing(tmp_path: Path) -> None:
    event = {
        "action": "opened",
        "repository": {"full_name": "acme/omg"},
        "pull_request": {"number": 9, "head": {"sha": "def456"}},
    }
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True)

    payload = helpers.build_pr_handoff(event, artifacts)
    assert payload["verdict"] == "fail"
    with pytest.raises(SystemExit):
        helpers.assert_pass(payload)


# ---------------------------------------------------------------------------
# Release-readiness: policy-pack trust enforcement
# ---------------------------------------------------------------------------


def test_release_readiness_workflow_has_policy_pack_verify_step() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    verify_pos = release_job.find("policy-pack verify --all")
    gate_pos = release_job.find("Run release readiness gate")
    assert verify_pos >= 0, "Missing 'policy-pack verify --all' step in release-readiness"
    assert gate_pos >= 0, "Missing 'Run release readiness gate' step"
    assert verify_pos < gate_pos, "policy-pack verify --all must appear before release readiness gate"


def test_release_readiness_workflow_enforces_trusted_packs() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    gate_pos = release_job.find("Run release readiness gate")
    assert gate_pos >= 0, "Missing 'Run release readiness gate' step"
    gate_section = release_job[gate_pos:]
    assert 'OMG_REQUIRE_TRUSTED_POLICY_PACKS: "1"' in gate_section, (
        "Run release readiness gate must set OMG_REQUIRE_TRUSTED_POLICY_PACKS: '1'"
    )


def test_release_readiness_standalone_verification_remains_blocking() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    standalone_pos = release_job.find("Run standalone verification")
    assert standalone_pos >= 0, "Missing 'Run standalone verification' step"
    standalone_section = release_job[standalone_pos:release_job.find("\n      - name:", standalone_pos + 1)]
    assert "continue-on-error: true" not in standalone_section, "Standalone verification must fail the release workflow"
    assert '::warning::Standalone verification failed' not in standalone_section, (
        "Standalone verification must remain a blocker, not a warning"
    )


def test_pytest_uses_loadgroup_when_repo_has_xdist_group_markers() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '--dist",\n    "loadgroup"' in pyproject or "--dist',\n    'loadgroup'" in pyproject or '"loadgroup"' in pyproject


def test_release_workflow_stages_release_surface_manifest_before_gate() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    compile_job = _section(text, "  compile-public-and-parity:\n", "  compile-enterprise:\n")
    assert "release-surface.json" in compile_job
    assert "compile_release_surfaces" in compile_job


def test_release_readiness_normalizes_release_surface_manifest_after_download() -> None:
    text = _read_workflow_text("omg-release-readiness.yml")
    release_job = _section(text, "  release-readiness:\n")
    assert "Normalize release-surface manifests after artifact download" in release_job
    assert "release-surface.json" in release_job
