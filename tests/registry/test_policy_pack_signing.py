"""Tests for policy-pack sign and verify round-trip."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest

from registry.approval_artifact import (
    create_approval_artifact,
    verify_approval_artifact,
)
from registry.verify_artifact import _canonical_json
from runtime.policy_pack_loader import load_policy_pack

_DEV_PRIVATE_KEY = "Hx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8fHx8="
_DEV_KEY_ID = "1f5fe64ec2f8c901"
_PACK_ID = "locked-prod"
_PACKS_DIR = Path(__file__).resolve().parent.parent.parent / "registry" / "policy-packs"
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def _compute_pack_digest(pack_id: str) -> str:
    pack = load_policy_pack(pack_id)
    return hashlib.sha256(_canonical_json(dict(pack))).hexdigest()


def _sign_pack(pack_id: str, key_id: str, private_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    pack = load_policy_pack(pack_id)
    digest = _compute_pack_digest(pack_id)

    approval = create_approval_artifact(
        artifact_digest=digest,
        action="policy-pack-sign",
        scope=f"policy-pack/{pack_id}",
        reason=f"Signing policy pack {pack_id}",
        signer_key_id=key_id,
        signer_private_key=private_key,
    )

    signature_artifact = asdict(approval)
    lockfile = {
        "pack_id": pack_id,
        "pack_path": f"registry/policy-packs/{pack_id}.yaml",
        "canonical_digest": digest,
        "signer_key_id": key_id,
        "algorithm": "ed25519",
        "signature_path": f"registry/policy-packs/{pack_id}.signature.json",
        "created_at": approval.issued_at,
    }
    return signature_artifact, lockfile


class TestPolicyPackSignRoundTrip:

    def test_sign_then_verify_passes(self):
        digest = _compute_pack_digest(_PACK_ID)
        sig_artifact, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)

        result = verify_approval_artifact(sig_artifact, expected_artifact_digest=digest)
        assert result["valid"] is True
        assert result["reason"] == "verified"

    def test_lockfile_digest_matches_recomputed(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        recomputed = _compute_pack_digest(_PACK_ID)
        assert lockfile["canonical_digest"] == recomputed


class TestPolicyPackTamperDetection:

    def test_tampered_content_fails_verification(self, tmp_path):
        # given: signed pack
        digest = _compute_pack_digest(_PACK_ID)
        sig_artifact, _ = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)

        # when: content is tampered
        tampered_pack = dict(load_policy_pack(_PACK_ID))
        tampered_pack["description"] = "TAMPERED DESCRIPTION"
        tampered_digest = hashlib.sha256(_canonical_json(tampered_pack)).hexdigest()

        # then: verification fails with digest mismatch
        result = verify_approval_artifact(sig_artifact, expected_artifact_digest=tampered_digest)
        assert result["valid"] is False
        assert "digest mismatch" in result["reason"]


class TestCanonicalDigestDeterminism:

    def test_key_order_does_not_affect_digest(self):
        pack = dict(load_policy_pack(_PACK_ID))

        digest_a = hashlib.sha256(_canonical_json(pack)).hexdigest()

        reversed_pack = dict(reversed(list(pack.items())))
        digest_b = hashlib.sha256(_canonical_json(reversed_pack)).hexdigest()

        assert digest_a == digest_b

    def test_canonical_json_is_deterministic(self):
        pack = dict(load_policy_pack(_PACK_ID))
        assert _canonical_json(pack) == _canonical_json(pack)


class TestLockfileFields:

    def test_lockfile_has_required_fields(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)

        required = {"pack_id", "pack_path", "canonical_digest", "signer_key_id",
                     "algorithm", "signature_path", "created_at"}
        assert required.issubset(set(lockfile.keys()))

    def test_lockfile_signature_path_format(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        assert lockfile["signature_path"] == f"registry/policy-packs/{_PACK_ID}.signature.json"

    def test_lockfile_canonical_digest_is_sha256(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        digest = lockfile["canonical_digest"]
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_lockfile_signer_key_id_matches(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        assert lockfile["signer_key_id"] == _DEV_KEY_ID

    def test_lockfile_algorithm_is_ed25519(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        assert lockfile["algorithm"] == "ed25519"


class TestCLISignVerify:

    def test_cli_sign_exits_zero(self):
        env = os.environ.copy()
        env["OMG_SIGNING_KEY"] = _DEV_PRIVATE_KEY
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "sign", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
        output = json.loads(result.stdout)
        assert output["status"] == "signed"

    def test_cli_verify_exits_zero(self):
        # given: pack is signed
        env = os.environ.copy()
        env["OMG_SIGNING_KEY"] = _DEV_PRIVATE_KEY
        sign_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "sign", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert sign_result.returncode == 0

        # when: verify is called
        verify_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "verify", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )

        # then: exits 0 with verified status
        assert verify_result.returncode == 0, f"stdout={verify_result.stdout}\nstderr={verify_result.stderr}"
        output = json.loads(verify_result.stdout)
        assert output["status"] == "verified"
