import json
from pathlib import Path
from datetime import datetime
import pytest
from runtime.doc_generator import generate_docs
from runtime.adoption import CANONICAL_VERSION
from runtime.canonical_surface import get_canonical_hosts

def test_generate_docs_emits_all_files(tmp_path):
    output_root = tmp_path / "docs"
    result = generate_docs(output_root)
    
    expected_files = [
        "support-matrix.json",
        "preset-matrix.json",
        "host-tiers.json",
        "install-verification.json",
        "SUPPORT-MATRIX.md",
        "PRESET-REFERENCE.md",
    ]
    
    for filename in expected_files:
        assert (output_root / filename).exists()
    
    assert result["status"] == "ok"
    assert result["output_root"] == str(output_root)

def test_support_matrix_content(tmp_path):
    output_root = tmp_path / "docs"
    generate_docs(output_root)
    
    with open(output_root / "support-matrix.json", "r") as f:
        data = json.load(f)
    
    assert data["generated_by"] == "omg docs generate"
    assert data["version"] == CANONICAL_VERSION
    assert "generated_at" in data
    assert data["canonical_hosts"] == list(get_canonical_hosts())
    assert "compatibility_hosts" in data
    assert "channels" in data
    assert "presets" in data

def test_preset_matrix_content(tmp_path):
    output_root = tmp_path / "docs"
    generate_docs(output_root)
    
    with open(output_root / "preset-matrix.json", "r") as f:
        data = json.load(f)
    
    assert data["generated_by"] == "omg docs generate"
    assert data["version"] == CANONICAL_VERSION
    assert "presets" in data
    assert len(data["presets"]) >= 6
    for preset, features in data["presets"].items():
        assert isinstance(features, dict)

def test_deterministic_output(tmp_path):
    output_root1 = tmp_path / "docs1"
    output_root2 = tmp_path / "docs2"
    
    generate_docs(output_root1)
    generate_docs(output_root2)
    
    files_to_check = [
        "support-matrix.json",
        "preset-matrix.json",
        "host-tiers.json",
        "install-verification.json",
        "SUPPORT-MATRIX.md",
        "PRESET-REFERENCE.md",
    ]
    
    for filename in files_to_check:
        content1 = (output_root1 / filename).read_text()
        content2 = (output_root2 / filename).read_text()
        
        if filename.endswith(".json"):
            # Ignore generated_at for determinism check
            d1 = json.loads(content1)
            d2 = json.loads(content2)
            d1.pop("generated_at")
            d2.pop("generated_at")
            assert d1 == d2
        else:
            assert content1 == content2

def test_markdown_headers(tmp_path):
    output_root = tmp_path / "docs"
    generate_docs(output_root)
    
    for filename in ["SUPPORT-MATRIX.md", "PRESET-REFERENCE.md"]:
        content = (output_root / filename).read_text()
        assert content.startswith("<!-- GENERATED: DO NOT EDIT MANUALLY -->")
