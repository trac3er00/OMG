from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from registry.verify_artifact import sign_artifact_statement
from runtime.release_surfaces import AuthoredSurface

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

import importlib.util

_SCRIPT_PATH = _REPO_ROOT / "scripts" / "validate-release-identity.py"
_spec = importlib.util.spec_from_file_location("validate_release_identity", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

validate_authored = _mod.validate_authored
validate_derived = _mod.validate_derived
scan_scoped_residue = _mod.scan_scoped_residue
build_report = _mod.build_report
validate_release_surface = getattr(_mod, "validate_release_surface", None)
find_explain_command_blockers = getattr(_mod, "_find_explain_command_blockers", None)
find_install_launcher_blockers = getattr(_mod, "_find_install_launcher_blockers", None)
find_npx_front_door_blockers = getattr(_mod, "_find_npx_front_door_blockers", None)

_OLD_VERSION = "0.0.1-test"


class TestHappyPath:
    def test_exits_zero_on_clean_tree(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "all", "--forbid-version", _OLD_VERSION],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["overall_status"] == "ok"
        assert result.returncode == 0
        assert "release_surface" in output
        assert output["release_surface"]["status"] == "ok"

    def test_json_output_structure(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "all"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert "canonical_version" in output
        assert "scope" in output
        assert "authored" in output
        assert "derived" in output
        assert "overall_status" in output
        assert output["scope"] == "all"

    def test_forbid_version_equal_to_canonical_is_not_residue(self):
        canonical = _mod.extract_canonical_version(_REPO_ROOT / "runtime" / "adoption.py")
        assert canonical is not None

        result = subprocess.run(
            [
                sys.executable,
                str(_SCRIPT_PATH),
                "--scope",
                "all",
                "--forbid-version",
                canonical,
            ],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )

        output = json.loads(result.stdout)
        assert output["scoped_residue"]["status"] == "ok"
        assert output["scoped_residue"]["blockers"] == []
        assert result.returncode == 0


class TestAuthoredDrift:
    def test_authored_blockers_on_drift(self):
        with patch.object(_mod, "check_surface") as mock_check:
            mock_check.return_value = [("package.json version", "1.0.0")]
            result = validate_authored(_REPO_ROOT, _OLD_VERSION)
        assert result["status"] == "fail"
        assert len(result["blockers"]) > 0
        blocker = result["blockers"][0]
        assert blocker["surface"] == "package.json version"
        assert blocker["found"] == "1.0.0"
        assert blocker["expected"] == _OLD_VERSION

    def test_authored_ok_when_no_drift(self):
        with patch.object(_mod, "check_surface") as mock_check:
            mock_check.return_value = []
            result = validate_authored(_REPO_ROOT, _OLD_VERSION)
        assert result["status"] == "ok"
        assert result["blockers"] == []

    def test_authored_blockers_on_stale_gemini_surface(self, tmp_path):
        gemini_path = tmp_path / ".gemini" / "settings.json"
        gemini_path.parent.mkdir(parents=True)
        gemini_path.write_text(
            json.dumps(
                {
                    "_omg": {
                        "_version": "2.2.2",
                        "generated": {"contract_version": "2.2.2"},
                    }
                }
            ),
            encoding="utf-8",
        )

        surfaces = [
            AuthoredSurface(
                ".gemini/settings.json",
                "json_key_path",
                ["_omg", "_version"],
                "Gemini settings OMG version",
                source_only=False,
            ),
            AuthoredSurface(
                ".gemini/settings.json",
                "json_key_path",
                ["_omg", "generated", "contract_version"],
                "Gemini settings contract version",
                source_only=False,
            ),
        ]

        with patch.object(_mod, "AUTHORED_SURFACES", surfaces):
            result = validate_authored(tmp_path, "2.2.3")

        assert result["status"] == "fail"
        assert len(result["blockers"]) == 2
        assert result["blockers"][0]["surface"] == ".gemini/settings.json _omg._version"
        assert result["blockers"][1]["surface"] == ".gemini/settings.json _omg.generated.contract_version"


class TestReleaseSurfaceValidation:
    def test_validate_release_surface_available(self):
        assert callable(validate_release_surface), "validate_release_surface must exist"

    def test_explain_command_blocker_helper_available(self):
        assert callable(find_explain_command_blockers), "_find_explain_command_blockers must exist"

    def test_install_launcher_blocker_helper_available(self):
        assert callable(find_install_launcher_blockers), "_find_install_launcher_blockers must exist"

    def test_npx_front_door_blocker_helper_available(self):
        assert callable(find_npx_front_door_blockers), "_find_npx_front_door_blockers must exist"

    def test_build_report_includes_release_surface_section(self):
        report = build_report(
            canonical="2.2.12",
            scope="all",
            forbid_version=None,
            authored={"status": "ok", "blockers": []},
            derived={"status": "ok", "blockers": []},
            scoped_residue=None,
            release_surface={"status": "ok", "blockers": [], "checks": {}},
        )
        assert "release_surface" in report
        assert report["release_surface"]["status"] == "ok"

    def test_release_surface_failure_flips_overall_status(self):
        report = build_report(
            canonical="2.2.12",
            scope="all",
            forbid_version=None,
            authored={"status": "ok", "blockers": []},
            derived={"status": "ok", "blockers": []},
            scoped_residue=None,
            release_surface={"status": "fail", "blockers": ["front_door"], "checks": {}},
        )
        assert report["overall_status"] == "fail"

    def test_explain_command_blocker_flags_positional_readme_syntax(self, tmp_path):
        proof = tmp_path / "docs" / "proof.md"
        proof.parent.mkdir(parents=True, exist_ok=True)
        proof.write_text("```bash\nnpx omg explain run <id>\n```\n", encoding="utf-8")

        blockers = find_explain_command_blockers(tmp_path)

        assert any("docs/proof.md" in blocker for blocker in blockers)

    def test_install_launcher_blocker_flags_plain_local_npm_install(self, tmp_path):
        guide = tmp_path / "docs" / "install" / "codex.md"
        guide.parent.mkdir(parents=True, exist_ok=True)
        guide.write_text(
            "```bash\nnpm install @trac3r/oh-my-god\n```\n\n```bash\nomg env doctor\n```\n",
            encoding="utf-8",
        )

        blockers = find_install_launcher_blockers(tmp_path)

        assert any("docs/install/codex.md" in blocker for blocker in blockers)

    def test_npx_front_door_blocker_flags_bare_omg_flow(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(
            "```bash\nomg env doctor\nomg install --plan\nomg install --apply\nomg ship\n```\n",
            encoding="utf-8",
        )

        blockers = find_npx_front_door_blockers(tmp_path)

        assert any("README.md" in blocker for blocker in blockers)


class TestDerivedDrift:
    def test_derived_blockers_on_mismatch(self, tmp_path):
        manifest_dir = tmp_path / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text(json.dumps({"contract_version": "1.0.0"}))

        result = validate_derived(tmp_path, _OLD_VERSION)
        assert result["status"] == "fail"
        assert any(b["surface"].endswith("manifest.json") for b in result["blockers"])

    def test_derived_ok_when_version_matches(self, tmp_path):
        manifest_dir = tmp_path / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text(json.dumps({"contract_version": _OLD_VERSION}))

        result = validate_derived(tmp_path, _OLD_VERSION)
        matching = [b for b in result["blockers"] if "dist/public/manifest.json" in b["surface"]]
        assert matching == []

    def test_release_manifest_missing_attestation_fails(self, tmp_path):
        manifest_dir = tmp_path / "artifacts" / "release" / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema": "OmgCompiledArtifactManifest",
                    "contract_version": "2.1.1",
                    "artifacts": [
                        {
                            "path": "bundle/settings.json",
                            "sha256": "abc123",
                        }
                    ],
                }
            )
        )

        result = validate_derived(tmp_path, "2.1.1")
        assert result["status"] == "fail"
        assert any("missing_attestation" in blocker["surface"] for blocker in result["blockers"])

    def test_release_manifest_with_detached_attestation_passes(self, tmp_path):
        manifest_dir = tmp_path / "artifacts" / "release" / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        digest = "a" * 64
        manifest = {
            "schema": "OmgCompiledArtifactManifest",
            "contract_version": "2.1.1",
            "artifacts": [
                {"path": "bundle/settings.json", "sha256": digest}
            ],
            "attestations": [
                {
                    "artifact_path": "bundle/settings.json",
                    "statement_path": "attestations/bundle/settings.json.statement.json",
                    "signature_path": "attestations/bundle/settings.json.minisig",
                    "signer_key_id": "1f5fe64ec2f8c901",
                    "algorithm": "ed25519-minisign",
                }
            ],
        }
        (manifest_dir / "manifest.json").write_text(json.dumps(manifest))

        result = validate_derived(tmp_path, "2.1.1")
        assert result["status"] == "ok"

    def test_release_manifest_missing_statement_path_fails(self, tmp_path):
        manifest_dir = tmp_path / "artifacts" / "release" / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        digest = "a" * 64
        manifest = {
            "schema": "OmgCompiledArtifactManifest",
            "contract_version": "2.1.1",
            "artifacts": [
                {"path": "bundle/settings.json", "sha256": digest}
            ],
            "attestations": [
                {
                    "artifact_path": "bundle/settings.json",
                    "statement_path": "",
                    "signature_path": "attestations/bundle/settings.json.minisig",
                    "signer_key_id": "1f5fe64ec2f8c901",
                    "algorithm": "ed25519-minisign",
                }
            ],
        }
        (manifest_dir / "manifest.json").write_text(json.dumps(manifest))

        result = validate_derived(tmp_path, "2.1.1")
        assert result["status"] == "fail"
        assert any("missing_statement_path" in b["surface"] for b in result["blockers"])

    def test_release_manifest_missing_signature_path_fails(self, tmp_path):
        manifest_dir = tmp_path / "artifacts" / "release" / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        digest = "a" * 64
        manifest = {
            "schema": "OmgCompiledArtifactManifest",
            "contract_version": "2.1.1",
            "artifacts": [
                {"path": "bundle/settings.json", "sha256": digest}
            ],
            "attestations": [
                {
                    "artifact_path": "bundle/settings.json",
                    "statement_path": "attestations/bundle/settings.json.statement.json",
                    "signature_path": "",
                    "signer_key_id": "1f5fe64ec2f8c901",
                    "algorithm": "ed25519-minisign",
                }
            ],
        }
        (manifest_dir / "manifest.json").write_text(json.dumps(manifest))

        result = validate_derived(tmp_path, "2.1.1")
        assert result["status"] == "fail"
        assert any("missing_signature_path" in b["surface"] for b in result["blockers"])

    def test_release_manifest_unknown_algorithm_fails(self, tmp_path):
        manifest_dir = tmp_path / "artifacts" / "release" / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        digest = "a" * 64
        manifest = {
            "schema": "OmgCompiledArtifactManifest",
            "contract_version": "2.1.1",
            "artifacts": [
                {"path": "bundle/settings.json", "sha256": digest}
            ],
            "attestations": [
                {
                    "artifact_path": "bundle/settings.json",
                    "statement_path": "attestations/bundle/settings.json.statement.json",
                    "signature_path": "attestations/bundle/settings.json.minisig",
                    "signer_key_id": "1f5fe64ec2f8c901",
                    "algorithm": "rsa-pss-256",
                }
            ],
        }
        (manifest_dir / "manifest.json").write_text(json.dumps(manifest))

        result = validate_derived(tmp_path, "2.1.1")
        assert result["status"] == "fail"
        assert any("unknown_algorithm" in b["surface"] for b in result["blockers"])

    def test_release_manifest_legacy_hmac_bridge_is_rejected(self, tmp_path):
        manifest_dir = tmp_path / "artifacts" / "release" / "dist" / "public"
        manifest_dir.mkdir(parents=True)
        digest = "a" * 64
        statement = {
            "_type": "https://in-toto.io/Statement/v1",
            "predicateType": "https://slsa.dev/provenance/v1",
            "subject": [
                {"name": "bundle/settings.json", "digest": {"sha256": digest}}
            ],
            "predicate": {},
            "signer": {"keyid": "test", "algorithm": "hmac-sha256"},
            "issued_at": "2025-01-01T00:00:00Z",
            "signature": {
                "alg": "hmac-sha256",
                "keyid": "test",
                "value": "dGVzdA==",
            },
        }
        manifest = {
            "schema": "OmgCompiledArtifactManifest",
            "contract_version": "2.1.1",
            "artifacts": [
                {"path": "bundle/settings.json", "sha256": digest}
            ],
            "attestations": [
                {
                    "artifact_path": "bundle/settings.json",
                    "signer_pubkey": "test-hmac-key",
                    "statement": statement,
                }
            ],
        }
        (manifest_dir / "manifest.json").write_text(json.dumps(manifest))

        result = validate_derived(tmp_path, "2.1.1")
        assert result["status"] == "fail"
        assert any("invalid_signature" in b["surface"] for b in result["blockers"])


class TestScopedResidue:
    def test_residue_detected_in_file(self, tmp_path):
        target = tmp_path / "dist" / "public" / "manifest.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"contract_version": _OLD_VERSION, "name": "test"}))

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        assert result["status"] == "fail"
        assert len(result["blockers"]) > 0

    def test_residue_detected_in_directory(self, tmp_path):
        bundle_dir = tmp_path / "dist" / "public" / "bundle"
        bundle_dir.mkdir(parents=True)
        (bundle_dir / "index.js").write_text(f'const VERSION = "{_OLD_VERSION}";')

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        assert result["status"] == "fail"
        assert any("index.js" in b["file"] for b in result["blockers"])

    def test_residue_detected_in_double_nested_dist_directory(self, tmp_path):
        nested_dir = tmp_path / "dist" / "dist" / "public" / "bundle"
        nested_dir.mkdir(parents=True)
        (nested_dir / "index.js").write_text(f'const VERSION = "{_OLD_VERSION}";')

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        assert result["status"] == "fail"
        assert any("dist/dist/public/bundle/index.js" in b["file"] for b in result["blockers"])

    def test_residue_clean_when_no_forbidden(self, tmp_path):
        target = tmp_path / "dist" / "public" / "manifest.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"contract_version": "3.0.0", "name": "test"}')

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        matching = [b for b in result["blockers"] if "dist/public/manifest.json" in b["file"]]
        assert matching == []

    def test_changelog_historical_excluded(self, tmp_path):
        release_dir = tmp_path / "artifacts" / "release"
        release_dir.mkdir(parents=True)
        (release_dir / "CHANGELOG.md").write_text(f"## [{_OLD_VERSION}] - 2025-01-01\n- old entry\n")

        result = scan_scoped_residue(tmp_path, _OLD_VERSION)
        changelog_blockers = [
            b for b in result["blockers"]
            if b["file"].endswith("CHANGELOG.md") and f"## [{_OLD_VERSION}]" in b["content"]
        ]
        assert changelog_blockers == []


class TestMissingDerived:
    def test_missing_files_not_error(self, tmp_path):
        result = validate_derived(tmp_path, _OLD_VERSION)
        assert result["status"] == "ok"
        assert result["blockers"] == []


class TestOutputFormat:
    def test_build_report_structure(self):
        report = build_report(
            canonical=_OLD_VERSION,
            scope="all",
            forbid_version=_OLD_VERSION,
            authored={"status": "ok", "blockers": []},
            derived={"status": "ok", "blockers": []},
            scoped_residue={"status": "ok", "forbid_version": _OLD_VERSION, "blockers": []},
        )
        assert report["canonical_version"] == _OLD_VERSION
        assert report["scope"] == "all"
        assert report["forbid_version"] == _OLD_VERSION
        assert report["overall_status"] == "ok"

    def test_build_report_fail_on_any_blocker(self):
        report = build_report(
            canonical=_OLD_VERSION,
            scope="all",
            forbid_version=None,
            authored={"status": "fail", "blockers": [{"surface": "x", "found": "1.0", "expected": _OLD_VERSION}]},
            derived={"status": "ok", "blockers": []},
            scoped_residue=None,
        )
        assert report["overall_status"] == "fail"


class TestScopeAuthored:
    def test_scope_authored_subprocess(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "authored"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["scope"] == "authored"
        assert "authored" in output
        assert output.get("derived") is None or output["derived"]["status"] == "skipped"


class TestScopeDerived:
    def test_scope_derived_subprocess(self):
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--scope", "derived"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        output = json.loads(result.stdout)
        assert output["scope"] == "derived"
        assert output.get("authored") is None or output["authored"]["status"] == "skipped"
        assert "derived" in output


class TestReleaseSurfaceDriftGate:
    def test_drift_gate_blocks_when_package_json_has_no_bin(self):
        from runtime.contract_compiler import _check_release_surface_drift
        from runtime.release_surface_registry import get_public_surfaces

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            output = Path(td) / "output"
            root.mkdir()
            output.mkdir()

            pkg = {"name": "@trac3r/oh-my-god", "version": "2.2.7"}
            (root / "package.json").write_text(json.dumps(pkg))
            (root / "action.yml").write_text("name: OMG\n")

            manifest_dir = output / "dist" / "public"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "generated_by": "omg release compile-surfaces",
                "version": "2.2.7",
                "generated_at": "2025-01-01T00:00:00+00:00",
                "surfaces": get_public_surfaces(),
            }
            (manifest_dir / "release-surface.json").write_text(json.dumps(manifest))

            result = _check_release_surface_drift(root, output)

        assert result["status"] == "error"
        assert any("package.json missing npm bin.omg" in b for b in result["blockers"])

    def test_drift_gate_ok_when_all_surfaces_agree(self):
        from runtime.contract_compiler import _check_release_surface_drift
        from runtime.release_surface_registry import get_public_surfaces
        from unittest.mock import patch

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "root"
            output = Path(td) / "output"
            root.mkdir()
            output.mkdir()

            pkg = {"name": "@trac3r/oh-my-god", "version": "2.2.7", "bin": {"omg": "./OMG-setup.sh"}}
            (root / "package.json").write_text(json.dumps(pkg))
            (root / "action.yml").write_text("name: OMG\n")

            manifest_dir = output / "dist" / "public"
            manifest_dir.mkdir(parents=True)
            manifest = {
                "generated_by": "omg release compile-surfaces",
                "version": "2.2.7",
                "generated_at": "2025-01-01T00:00:00+00:00",
                "surfaces": get_public_surfaces(),
            }
            (manifest_dir / "release-surface.json").write_text(json.dumps(manifest))

            with patch(
                "runtime.contract_compiler.compile_release_surfaces",
                return_value={"status": "ok", "drift": []},
            ), patch(
                "runtime.contract_compiler.check_docs",
                return_value={"status": "ok", "drift": []},
            ):
                result = _check_release_surface_drift(root, output)

        assert result["status"] == "ok"
        assert result["blockers"] == []
