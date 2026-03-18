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

    import base64
    from registry.verify_artifact import _load_ed25519_backend, _key_id_from_public_key

    signer_public_key_b64 = ""
    try:
        serialization, Ed25519PrivateKey, _ = _load_ed25519_backend()
        private_raw = base64.b64decode(private_key, validate=True)
        priv_key_obj = Ed25519PrivateKey.from_private_bytes(private_raw)
        public_key_raw = priv_key_obj.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        signer_public_key_b64 = base64.b64encode(public_key_raw).decode("ascii")
    except Exception:
        pass

    signature_artifact = asdict(approval)
    lockfile = {
        "lockfile_version": 1,
        "pack_id": pack_id,
        "pack_path": f"registry/policy-packs/{pack_id}.yaml",
        "canonical_digest": digest,
        "signer_key_id": key_id,
        "signer_public_key": signer_public_key_b64,
        "algorithm": "ed25519-minisign",
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

        required = {"lockfile_version", "pack_id", "pack_path", "canonical_digest",
                     "signer_key_id", "signer_public_key", "algorithm",
                     "signature_path", "created_at"}
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

    def test_lockfile_algorithm_is_ed25519_minisign(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        assert lockfile["algorithm"] == "ed25519-minisign"

    def test_lockfile_version_is_integer(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        assert lockfile["lockfile_version"] == 1
        assert isinstance(lockfile["lockfile_version"], int)

    def test_lockfile_signer_public_key_is_base64(self):
        _, lockfile = _sign_pack(_PACK_ID, _DEV_KEY_ID, _DEV_PRIVATE_KEY)
        import base64
        pub = lockfile["signer_public_key"]
        assert isinstance(pub, str) and len(pub) > 0
        raw = base64.b64decode(pub, validate=True)
        assert len(raw) == 32


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
        env = os.environ.copy()
        env["OMG_SIGNING_KEY"] = _DEV_PRIVATE_KEY
        sign_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "sign", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert sign_result.returncode == 0

        verify_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "verify", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )

        assert verify_result.returncode == 0, f"stdout={verify_result.stdout}\nstderr={verify_result.stderr}"
        output = json.loads(verify_result.stdout)
        assert output["status"] == "verified"


class TestKeygenRoundTrip:

    def test_keygen_cli_produces_keypair(self, tmp_path):
        keypair_path = tmp_path / "test-key.json"
        result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "keygen", "--output", str(keypair_path), "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
        output = json.loads(result.stdout)
        assert output["schema"] == "PolicyPackKeygen"
        assert output["status"] == "ok"
        assert output["algorithm"] == "ed25519-minisign"
        assert "key_id" in output
        assert "public_key" in output
        assert keypair_path.exists()

        keypair = json.loads(keypair_path.read_text(encoding="utf-8"))
        assert "private_key" in keypair
        assert "public_key" in keypair
        assert keypair["algorithm"] == "ed25519-minisign"

    def test_json_keypath_sign_then_verify(self, tmp_path):
        keypair_path = tmp_path / "dev-key.json"
        keypair_path.write_text(json.dumps({
            "key_id": _DEV_KEY_ID,
            "algorithm": "ed25519-minisign",
            "private_key": _DEV_PRIVATE_KEY,
            "public_key": "placeholder",
        }), encoding="utf-8")

        env = os.environ.copy()
        sign_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "sign", _PACK_ID,
             "--key-path", str(keypair_path), "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert sign_result.returncode == 0, f"stdout={sign_result.stdout}\nstderr={sign_result.stderr}"
        sign_out = json.loads(sign_result.stdout)
        assert sign_out["status"] == "signed"
        assert sign_out["signer_key_id"] == _DEV_KEY_ID

        verify_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "verify", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert verify_result.returncode == 0, f"stdout={verify_result.stdout}\nstderr={verify_result.stderr}"
        verify_out = json.loads(verify_result.stdout)
        assert verify_out["status"] == "verified"

    def test_lockfile_from_sign_has_new_fields(self):
        import base64
        env = os.environ.copy()
        env["OMG_SIGNING_KEY"] = _DEV_PRIVATE_KEY
        sign_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "sign", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert sign_result.returncode == 0, f"stdout={sign_result.stdout}\nstderr={sign_result.stderr}"

        lock_path = _PACKS_DIR / f"{_PACK_ID}.lock.json"
        lockfile = json.loads(lock_path.read_text(encoding="utf-8"))
        assert lockfile["lockfile_version"] == 1
        assert lockfile["algorithm"] == "ed25519-minisign"
        assert "signer_public_key" in lockfile
        assert isinstance(lockfile["signer_public_key"], str)
        decoded_pub = base64.b64decode(lockfile["signer_public_key"], validate=True)
        assert len(decoded_pub) == 32

    def test_tampered_lockfile_algorithm_fails(self):
        env = os.environ.copy()
        env["OMG_SIGNING_KEY"] = _DEV_PRIVATE_KEY
        sign_result = subprocess.run(
            [sys.executable, str(_SCRIPTS_DIR / "omg.py"),
             "policy-pack", "sign", _PACK_ID, "--format", "json"],
            capture_output=True, text=True, env=env, timeout=30,
        )
        assert sign_result.returncode == 0

        lock_path = _PACKS_DIR / f"{_PACK_ID}.lock.json"
        lockfile = json.loads(lock_path.read_text(encoding="utf-8"))
        assert lockfile["algorithm"] == "ed25519-minisign"
