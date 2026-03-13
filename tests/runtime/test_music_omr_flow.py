from __future__ import annotations

import json
from pathlib import Path

from runtime.music_omr_testbed import MusicOMRTestbed


def test_flagship_omr_flow_passes_under_normal_conditions(tmp_path: Path) -> None:
    """Test: flagship OMR flow passes under normal conditions (deterministic fixtures)."""
    # Setup fixtures
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    score_path = fixtures_dir / "simple_c_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_c_major"}), encoding="utf-8")
    
    expected_path = fixtures_dir / "simple_c_major_expected.json"
    expected_path.write_text(json.dumps({
        "notes": ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"],
        "time_signatures": ["4/4"],
        "key_signatures": ["C"],
        "measures": 2,
        "raw_output": "raw_omr_data_here"
    }), encoding="utf-8")
    
    testbed = MusicOMRTestbed(str(tmp_path))
    
    # Run OMR
    omr_result = testbed.run_omr(score_path)
    
    # Verify
    verification = testbed.verify_result(omr_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0
    assert len(verification.mismatches) == 0


def test_flagship_flow_surfaces_musically_wrong_result(tmp_path: Path) -> None:
    """Test: flagship flow surfaces a musically wrong or incomplete result (corrupted fixture)."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    score_path = fixtures_dir / "corrupted_score.json"
    score_path.write_text(json.dumps({"score_id": "corrupted_score"}), encoding="utf-8")
    
    expected_path = fixtures_dir / "simple_c_major_expected.json"
    expected_path.write_text(json.dumps({
        "notes": ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"],
        "time_signatures": ["4/4"],
        "key_signatures": ["C"],
        "measures": 2,
        "raw_output": "raw_omr_data_here"
    }), encoding="utf-8")
    
    testbed = MusicOMRTestbed(str(tmp_path))
    
    # Run OMR
    omr_result = testbed.run_omr(score_path)
    
    # Verify
    verification = testbed.verify_result(omr_result, expected_path)
    assert verification.passed is False
    assert verification.score == 0.0
    assert len(verification.mismatches) > 0


def test_transposition_produces_correct_output(tmp_path: Path) -> None:
    """Test: transposition produces correct output."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    score_path = fixtures_dir / "simple_c_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_c_major"}), encoding="utf-8")
    
    expected_path = fixtures_dir / "transposed_to_g_major.json"
    expected_path.write_text(json.dumps({
        "original_key": "C",
        "target_key": "G",
        "transposed_notes": ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"]
    }), encoding="utf-8")
    
    testbed = MusicOMRTestbed(str(tmp_path))
    
    # Run OMR
    omr_result = testbed.run_omr(score_path)
    
    # Run Transposition
    transposition_result = testbed.run_transposition(omr_result, "G")
    
    # Verify
    verification = testbed.verify_result(transposition_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0
    assert len(verification.mismatches) == 0


def test_evidence_is_emitted_and_machine_verifiable(tmp_path: Path) -> None:
    """Test: evidence is emitted and machine-verifiable."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    score_path = fixtures_dir / "simple_c_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_c_major"}), encoding="utf-8")
    
    testbed = MusicOMRTestbed(str(tmp_path))
    
    omr_result = testbed.run_omr(score_path)
    transposition_result = testbed.run_transposition(omr_result, "G")
    
    results = {
        "omr": omr_result,
        "transposition": transposition_result
    }
    
    evidence_path = testbed.emit_evidence("test-run-123", results)
    
    assert Path(evidence_path).exists()
    
    payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    assert payload["schema"] == "MusicOMREvidence"
    assert payload["run_id"] == "test-run-123"
    assert "omr" in payload["results"]
    assert "transposition" in payload["results"]
    assert payload["results"]["omr"]["notes"] == ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
    assert payload["results"]["transposition"]["target_key"] == "G"
