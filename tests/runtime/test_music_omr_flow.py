from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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


def test_g_major_omr_flow(tmp_path: Path) -> None:
    """Test: G major scale fixture produces correct OMR output."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "simple_g_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_g_major"}), encoding="utf-8")

    expected_path = fixtures_dir / "simple_g_major_expected.json"
    expected_path.write_text(json.dumps({
        "notes": ["G4", "A4", "B4", "C5", "D5", "E5", "F#5", "G5"],
        "time_signatures": ["4/4"],
        "key_signatures": ["G"],
        "measures": 2,
    }), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    verification = testbed.verify_result(omr_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0


def test_chromatic_fragment_omr_flow(tmp_path: Path) -> None:
    """Test: chromatic fragment fixture produces correct OMR output."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "chromatic_fragment.json"
    score_path.write_text(json.dumps({"score_id": "chromatic_fragment"}), encoding="utf-8")

    expected_path = fixtures_dir / "chromatic_fragment_expected.json"
    expected_path.write_text(json.dumps({
        "notes": ["C4", "C#4", "D4", "D#4", "E4", "F4", "F#4", "G4"],
        "time_signatures": ["4/4"],
        "key_signatures": ["C"],
        "measures": 2,
    }), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    verification = testbed.verify_result(omr_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0


def test_waltz_three_four_omr_flow(tmp_path: Path) -> None:
    """Test: waltz 3/4 fixture produces correct OMR output."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "waltz_three_four.json"
    score_path.write_text(json.dumps({"score_id": "waltz_three_four"}), encoding="utf-8")

    expected_path = fixtures_dir / "waltz_three_four_expected.json"
    expected_path.write_text(json.dumps({
        "notes": ["C4", "E4", "G4", "C5", "E5", "G5"],
        "time_signatures": ["3/4"],
        "key_signatures": ["C"],
        "measures": 2,
    }), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    verification = testbed.verify_result(omr_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0


def test_g_major_transposition_to_d(tmp_path: Path) -> None:
    """Test: G major transposed to D major via deterministic interval."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "simple_g_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_g_major"}), encoding="utf-8")

    expected_path = fixtures_dir / "transposed_g_to_d_major.json"
    expected_path.write_text(json.dumps({
        "original_key": "G",
        "target_key": "D",
        "transposed_notes": ["D5", "E5", "F#5", "G5", "A5", "B5", "C#6", "D6"],
    }), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    transposition_result = testbed.run_transposition(omr_result, "D")
    verification = testbed.verify_result(transposition_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0


def test_chromatic_transposition_to_g(tmp_path: Path) -> None:
    """Test: chromatic fragment transposed to G via deterministic interval."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "chromatic_fragment.json"
    score_path.write_text(json.dumps({"score_id": "chromatic_fragment"}), encoding="utf-8")

    expected_path = fixtures_dir / "transposed_chromatic_to_g.json"
    expected_path.write_text(json.dumps({
        "original_key": "C",
        "target_key": "G",
        "transposed_notes": ["G4", "G#4", "A4", "A#4", "B4", "C5", "C#5", "D5"],
    }), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    transposition_result = testbed.run_transposition(omr_result, "G")
    verification = testbed.verify_result(transposition_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0


def test_waltz_transposition_to_g(tmp_path: Path) -> None:
    """Test: waltz transposed to G via deterministic interval."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "waltz_three_four.json"
    score_path.write_text(json.dumps({"score_id": "waltz_three_four"}), encoding="utf-8")

    expected_path = fixtures_dir / "transposed_waltz_to_g.json"
    expected_path.write_text(json.dumps({
        "original_key": "C",
        "target_key": "G",
        "transposed_notes": ["G4", "B4", "D5", "G5", "B5", "D6"],
    }), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    transposition_result = testbed.run_transposition(omr_result, "G")
    verification = testbed.verify_result(transposition_result, expected_path)
    assert verification.passed is True
    assert verification.score == 1.0


def test_stale_evidence_detected(tmp_path: Path) -> None:
    """Test: stale evidence (past freshness window) is flagged as not fresh."""
    testbed = MusicOMRTestbed(str(tmp_path))

    # Timestamp 25 hours ago exceeds the default 24h window
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    assert testbed._is_fresh(old_ts, 86400) is False

    # Fresh timestamp within window
    fresh_ts = datetime.now(timezone.utc).isoformat()
    assert testbed._is_fresh(fresh_ts, 86400) is True

    # Zero max_age always stale
    assert testbed._is_fresh(fresh_ts, 0) is False

    # Invalid timestamp always stale
    assert testbed._is_fresh("not-a-date", 86400) is False


def test_incomplete_fixture_inventory_flagged(tmp_path: Path) -> None:
    """Test: evidence with fewer fixtures than minimum is flagged invalid."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "simple_c_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_c_major"}), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)

    evidence_path = testbed.emit_evidence(
        "test-incomplete-inv",
        {"omr": omr_result},
        fixture_inventory=["only_one.json"],
    )

    payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    assert payload["fixture_inventory_valid"] is False
    assert payload["fixture_count"] == 1
    assert payload["trace_metadata"]["fixture_inventory_valid"] is False


def test_evidence_includes_expanded_metadata(tmp_path: Path) -> None:
    """Test: emitted evidence includes fixture_inventory, freshness_threshold_secs, trace_metadata, and run_id linkage."""
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    score_path = fixtures_dir / "simple_c_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_c_major"}), encoding="utf-8")

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)

    evidence_path = testbed.emit_evidence(
        "test-metadata-run-001",
        {"omr": omr_result},
        trace_id="trace-meta-001",
    )

    payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))

    # fixture_inventory (default has >= 5)
    inv = payload["fixture_inventory"]
    assert isinstance(inv, list)
    assert len(inv) >= 5
    assert "simple_c_major.json" in inv

    # freshness_threshold_secs
    assert payload["freshness_threshold_secs"] == 86400
    assert payload["freshness"]["freshness_threshold_secs"] == 86400

    # run_id linkage
    assert payload["run_id"] == "test-metadata-run-001"
    assert payload["trace_metadata"]["run_id_linkage"] == "test-metadata-run-001"

    # trace_metadata
    tm = payload["trace_metadata"]
    assert tm["testbed"] == "MusicOMRTestbed"
    assert tm["deterministic"] is True
    assert tm["gate"] == "music-omr-daily"
    assert tm["fixture_count"] >= 5
    assert tm["fixture_inventory_valid"] is True

    # schema version bump
    assert payload["schema_version"] == "2.1.0"


def test_emit_evidence_includes_coordinator_run_id_when_active(tmp_path: Path, monkeypatch) -> None:
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    score_path = fixtures_dir / "simple_c_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_c_major"}), encoding="utf-8")

    monkeypatch.setattr(
        "runtime.music_omr_testbed.get_active_coordinator_run_id",
        lambda _project_dir: "coordinator-run-123",
    )

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    evidence_path = testbed.emit_evidence("test-run-123", {"omr": omr_result})
    payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))

    assert payload["coordinator_run_id"] == "coordinator-run-123"


def test_emit_evidence_omits_coordinator_run_id_when_not_active(tmp_path: Path, monkeypatch) -> None:
    fixtures_dir = tmp_path / "fixtures" / "music_omr"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    score_path = fixtures_dir / "simple_c_major.json"
    score_path.write_text(json.dumps({"score_id": "simple_c_major"}), encoding="utf-8")

    monkeypatch.setattr(
        "runtime.music_omr_testbed.get_active_coordinator_run_id",
        lambda _project_dir: "",
    )

    testbed = MusicOMRTestbed(str(tmp_path))
    omr_result = testbed.run_omr(score_path)
    evidence_path = testbed.emit_evidence("test-run-123", {"omr": omr_result})
    payload = json.loads(Path(evidence_path).read_text(encoding="utf-8"))

    assert "coordinator_run_id" not in payload
