"""Tests for knowledge scan index cache (§4.5)."""

def test_knowledge_uses_index_cache():
    """§4.5: Should use .index.json cache instead of full os.walk."""
    with open("hooks/prompt-enhancer.py") as f:
        content = f.read()
    assert ".index.json" in content
    assert "mtime" in content
    assert "file_count > 30" in content  # cap at 30 files
