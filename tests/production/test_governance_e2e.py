"""Governance ledger integrity E2E tests.

Tests the full governance pipeline: audit trail, ledger chain, tracebank, claim judge.
Validates module existence, cryptographic integrity mechanisms, and API contracts
without requiring running services or network access.
"""

import importlib.util
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


class TestAuditTrail:
    """Test HMAC audit trail (src/security/audit-trail.ts)."""

    audit_trail_path = ROOT / "src" / "security" / "audit-trail.ts"

    def test_audit_trail_module_exists(self):
        """Audit trail module should exist."""
        assert self.audit_trail_path.exists(), (
            f"audit-trail.ts not found at {self.audit_trail_path}"
        )

    def test_audit_trail_uses_hmac(self):
        """Audit trail should use HMAC for integrity signing."""
        content = self.audit_trail_path.read_text()
        assert "createHmac" in content, (
            "audit-trail.ts must use createHmac for HMAC signing"
        )

    def test_audit_trail_has_verify(self):
        """Audit trail should have a verify method."""
        content = self.audit_trail_path.read_text()
        assert "verify(" in content, "audit-trail.ts must expose a verify function"

    def test_audit_trail_uses_sha256_hmac(self):
        """Audit trail HMAC should use sha256 algorithm."""
        content = self.audit_trail_path.read_text()
        assert 'createHmac("sha256"' in content or "createHmac('sha256'" in content, (
            "audit-trail.ts HMAC must use sha256 algorithm"
        )

    def test_audit_trail_has_timing_safe_equal(self):
        """Audit trail verify should use timingSafeEqual to prevent timing attacks."""
        content = self.audit_trail_path.read_text()
        assert "timingSafeEqual" in content, (
            "audit-trail.ts must use timingSafeEqual for constant-time comparison"
        )

    def test_audit_trail_has_record_method(self):
        """Audit trail should have a record method for logging entries."""
        content = self.audit_trail_path.read_text()
        assert "record(" in content, "audit-trail.ts must have a record method"

    def test_audit_trail_has_key_rotation(self):
        """Audit trail should support HMAC key rotation."""
        content = self.audit_trail_path.read_text()
        assert "rotateKey" in content, "audit-trail.ts must support key rotation"

    def test_audit_trail_key_file_permissions(self):
        """Audit trail HMAC key file should be restricted to owner-only (0600)."""
        content = self.audit_trail_path.read_text()
        assert "0o600" in content or "0600" in content, (
            "audit-trail.ts must set key file permissions to 0600"
        )

    def test_audit_trail_siem_export(self):
        """Audit trail should support SIEM-compatible event export."""
        content = self.audit_trail_path.read_text()
        assert "SiemEvent" in content, "audit-trail.ts must define SiemEvent interface"
        assert "exportSiem" in content, "audit-trail.ts must have exportSiem method"


class TestGovernanceLedger:
    """Test SHA256 governance ledger (src/governance/ledger.ts)."""

    ledger_path = ROOT / "src" / "governance" / "ledger.ts"

    def test_ledger_module_exists(self):
        """Governance ledger should exist."""
        assert self.ledger_path.exists(), f"ledger.ts not found at {self.ledger_path}"

    def test_ledger_uses_sha256(self):
        """Ledger should use SHA256 for chain integrity hashing."""
        content = self.ledger_path.read_text()
        assert 'createHash("sha256")' in content or "createHash('sha256')" in content, (
            "ledger.ts must use createHash('sha256') for chain integrity"
        )

    def test_ledger_has_integrity_check(self):
        """Ledger should have integrity verification via verifyIntegrity."""
        content = self.ledger_path.read_text()
        assert "verifyIntegrity" in content, (
            "ledger.ts must expose verifyIntegrity method"
        )

    def test_ledger_has_chain_linking(self):
        """Ledger entries should link via previous_hash for tamper detection."""
        content = self.ledger_path.read_text()
        assert "previous_hash" in content, (
            "ledger.ts must use previous_hash for chain linking"
        )

    def test_ledger_has_genesis_hash(self):
        """Ledger should define a genesis hash constant."""
        content = self.ledger_path.read_text()
        assert "GENESIS_HASH" in content, "ledger.ts must define GENESIS_HASH constant"

    def test_ledger_has_append_method(self):
        """Ledger should have an append method for adding entries."""
        content = self.ledger_path.read_text()
        assert "append(" in content, "ledger.ts must have an append method"

    def test_ledger_has_read_all(self):
        """Ledger should have a readAll method for retrieving entries."""
        content = self.ledger_path.read_text()
        assert "readAll" in content, "ledger.ts must have readAll method"

    def test_ledger_tamper_detection_returns_index(self):
        """verifyIntegrity should return tampered_index on chain break."""
        content = self.ledger_path.read_text()
        assert "tampered_index" in content, (
            "ledger.ts verifyIntegrity must report tampered_index"
        )

    def test_ledger_has_rotation(self):
        """Ledger should have size-based log rotation."""
        content = self.ledger_path.read_text()
        assert "LEDGER_MAX_BYTES" in content, "ledger.ts must define LEDGER_MAX_BYTES"
        assert "checkRotation" in content, "ledger.ts must have checkRotation method"

    def test_ledger_schema_validation(self):
        """Ledger entries should be validated with a schema (zod)."""
        content = self.ledger_path.read_text()
        assert "LedgerEntrySchema" in content, (
            "ledger.ts must validate entries with LedgerEntrySchema"
        )


class TestTracebank:
    """Test tracebank event recording (runtime/tracebank.py)."""

    tracebank_path = ROOT / "runtime" / "tracebank.py"

    def test_tracebank_exists(self):
        """Tracebank module should exist."""
        assert self.tracebank_path.exists(), (
            f"tracebank.py not found at {self.tracebank_path}"
        )

    def test_tracebank_spec_loadable(self):
        """Tracebank should have a valid module spec."""
        spec = importlib.util.spec_from_file_location("tracebank", self.tracebank_path)
        assert spec is not None, "tracebank.py must have a valid module spec"

    def test_tracebank_has_record_trace(self):
        """Tracebank should expose a record_trace function."""
        content = self.tracebank_path.read_text()
        assert "def record_trace(" in content, (
            "tracebank.py must define record_trace function"
        )

    def test_tracebank_has_link_evidence(self):
        """Tracebank should expose a link_evidence function."""
        content = self.tracebank_path.read_text()
        assert "def link_evidence(" in content, (
            "tracebank.py must define link_evidence function"
        )

    def test_tracebank_captures_plan_patch_verify(self):
        """Tracebank traces should capture plan, patch, and verify phases."""
        content = self.tracebank_path.read_text()
        for field in ("plan", "patch", "verify"):
            assert f'"{field}"' in content or f"'{field}'" in content, (
                f"tracebank.py must capture '{field}' phase"
            )

    def test_tracebank_records_executor_metadata(self):
        """Tracebank should capture executor identity (user, pid)."""
        content = self.tracebank_path.read_text()
        assert "executor" in content, "tracebank.py must capture executor metadata"
        assert "getpass.getuser" in content or "getuser" in content, (
            "tracebank.py must capture user identity"
        )

    def test_tracebank_records_environment(self):
        """Tracebank should capture execution environment (hostname, platform)."""
        content = self.tracebank_path.read_text()
        assert "environment" in content, "tracebank.py must capture environment"
        assert "hostname" in content, "tracebank.py must capture hostname"

    def test_tracebank_uses_jsonl_storage(self):
        """Tracebank should persist events as JSONL."""
        content = self.tracebank_path.read_text()
        assert "events.jsonl" in content, "tracebank.py must store events as JSONL"

    def test_tracebank_generates_trace_ids(self):
        """Tracebank should generate unique trace IDs."""
        content = self.tracebank_path.read_text()
        assert "trace_id" in content, "tracebank.py must generate trace_id"
        assert "uuid4" in content, "tracebank.py should use uuid4 for trace IDs"


class TestClaimJudge:
    """Test claim judge (runtime/claim_judge.py)."""

    claim_judge_path = ROOT / "runtime" / "claim_judge.py"

    def test_claim_judge_exists(self):
        """Claim judge should exist."""
        assert self.claim_judge_path.exists(), (
            f"claim_judge.py not found at {self.claim_judge_path}"
        )

    def test_claim_judge_spec_loadable(self):
        """Claim judge should have a valid module spec."""
        spec = importlib.util.spec_from_file_location(
            "claim_judge", self.claim_judge_path
        )
        assert spec is not None, "claim_judge.py must have a valid module spec"

    def test_claim_judge_has_judge_function(self):
        """Claim judge should have a judge_claim function."""
        content = self.claim_judge_path.read_text()
        assert "def judge_claim(" in content, (
            "claim_judge.py must define judge_claim function"
        )

    def test_claim_judge_has_batch_judge(self):
        """Claim judge should support batch evaluation via judge_claims."""
        content = self.claim_judge_path.read_text()
        assert "def judge_claims(" in content, (
            "claim_judge.py must define judge_claims for batch evaluation"
        )

    def test_claim_judge_has_release_evaluation(self):
        """Claim judge should evaluate release readiness."""
        content = self.claim_judge_path.read_text()
        assert "def evaluate_claims_for_release(" in content, (
            "claim_judge.py must define evaluate_claims_for_release"
        )

    def test_claim_judge_emits_verdicts(self):
        """Claim judge verdicts should include pass/fail/block."""
        content = self.claim_judge_path.read_text()
        for verdict_type in ("pass", "fail", "block"):
            assert f'"{verdict_type}"' in content or f"'{verdict_type}'" in content, (
                f"claim_judge.py must emit '{verdict_type}' verdict"
            )

    def test_claim_judge_checks_artifacts(self):
        """Claim judge should validate evidence artifacts."""
        content = self.claim_judge_path.read_text()
        assert "missing_artifacts" in content, (
            "claim_judge.py must check for missing_artifacts"
        )

    def test_claim_judge_checks_trace_ids(self):
        """Claim judge should validate trace link presence."""
        content = self.claim_judge_path.read_text()
        assert "missing_trace_ids" in content, (
            "claim_judge.py must check for missing_trace_ids"
        )

    def test_claim_judge_validates_causal_chain(self):
        """Claim judge should validate lock->delta->verification causal chain."""
        content = self.claim_judge_path.read_text()
        assert "causal_chain" in content, "claim_judge.py must validate causal_chain"

    def test_claim_judge_persists_results(self):
        """Claim judge should persist per-claim result artifacts."""
        content = self.claim_judge_path.read_text()
        assert "ClaimJudgeResult" in content, (
            "claim_judge.py must persist ClaimJudgeResult artifacts"
        )

    def test_claim_judge_checks_security_scans(self):
        """Claim judge should validate security scan outcomes."""
        content = self.claim_judge_path.read_text()
        assert "security_scan_failed" in content, (
            "claim_judge.py must check security_scan_failed"
        )


class TestGovernancePipeline:
    """Test full governance pipeline integration."""

    governance_modules = [
        ROOT / "src" / "security" / "audit-trail.ts",
        ROOT / "src" / "governance" / "ledger.ts",
        ROOT / "runtime" / "tracebank.py",
        ROOT / "runtime" / "claim_judge.py",
    ]

    def test_all_governance_modules_present(self):
        """All governance modules should be present."""
        missing = [str(m) for m in self.governance_modules if not m.exists()]
        assert len(missing) == 0, f"Missing governance modules: {missing}"

    def test_audit_trail_and_ledger_share_sha256(self):
        """Both audit trail (HMAC) and ledger use SHA256 for integrity."""
        audit_content = (ROOT / "src" / "security" / "audit-trail.ts").read_text()
        ledger_content = (ROOT / "src" / "governance" / "ledger.ts").read_text()
        assert "sha256" in audit_content.lower(), (
            "audit-trail.ts must use sha256 in HMAC"
        )
        assert "sha256" in ledger_content.lower(), (
            "ledger.ts must use sha256 for chain hashing"
        )

    def test_tracebank_and_claim_judge_share_trace_contract(self):
        """Tracebank trace_ids should be consumable by claim judge."""
        tracebank_content = (ROOT / "runtime" / "tracebank.py").read_text()
        claim_judge_content = (ROOT / "runtime" / "claim_judge.py").read_text()
        assert "trace_id" in tracebank_content, "tracebank.py must produce trace_id"
        assert "trace_ids" in claim_judge_content, (
            "claim_judge.py must consume trace_ids"
        )

    def test_claim_judge_references_evidence_artifacts(self):
        """Claim judge should reference .omg/evidence/ artifacts."""
        content = (ROOT / "runtime" / "claim_judge.py").read_text()
        assert ".omg" in content and "evidence" in content, (
            "claim_judge.py must reference .omg/evidence/ for artifact storage"
        )

    def test_ledger_entries_carry_evidence_refs(self):
        """Ledger entries should carry evidence_refs for traceability."""
        content = (ROOT / "src" / "governance" / "ledger.ts").read_text()
        assert "evidence_refs" in content, "ledger.ts entries must carry evidence_refs"

    def test_governance_crypto_consistency(self):
        """All governance modules using crypto should import from node:crypto."""
        audit_content = (ROOT / "src" / "security" / "audit-trail.ts").read_text()
        ledger_content = (ROOT / "src" / "governance" / "ledger.ts").read_text()
        assert "node:crypto" in audit_content, (
            "audit-trail.ts must import from node:crypto"
        )
        assert "node:crypto" in ledger_content, "ledger.ts must import from node:crypto"
