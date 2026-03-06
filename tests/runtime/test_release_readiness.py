from __future__ import annotations


def test_collect_release_readiness_reports_git_provider_and_blockers(tmp_path, monkeypatch):
    import runtime.release_readiness as release_readiness

    monkeypatch.setattr(release_readiness, "_git_branch", lambda project_dir: "codex/phase1-runtime-truth")
    monkeypatch.setattr(release_readiness, "_git_status_lines", lambda project_dir: [" M README.md", "?? runtime/provider_bootstrap.py"])
    monkeypatch.setattr(
        release_readiness,
        "collect_provider_status_with_options",
        lambda project_dir, providers=None, include_smoke=False, smoke_host_mode="claude_dispatch": {
            "schema": "ProviderStatusMatrix",
            "status": "ok",
            "providers": [
                {
                    "provider": "codex",
                    "parity_state": "blocked",
                    "native_ready": False,
                    "dispatch_ready": False,
                    "fallback_provider": "claude",
                    "fallback_reason": "provider_login_required",
                    "fallback_mode": "provider_failover",
                    "local_steps": ["remove_incompatible_feature_flags"],
                    "provider_steps": ["login_to_provider"],
                },
                {
                    "provider": "kimi",
                    "parity_state": "native_ready",
                    "native_ready": True,
                    "dispatch_ready": True,
                    "local_steps": [],
                    "provider_steps": [],
                },
            ],
        },
    )

    result = release_readiness.collect_release_readiness(str(tmp_path))

    assert result["schema"] == "OmgReleaseReadiness"
    assert result["git"]["branch"] == "codex/phase1-runtime-truth"
    assert result["git"]["dirty"] is True
    assert result["providers"]["blocked"] == ["codex"]
    assert "codex: remove_incompatible_feature_flags" in result["blockers"]
    assert "codex: login_to_provider" in result["blockers"]
