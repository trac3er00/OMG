"""Tests for plugins/viz/diagram_generator.py — Mermaid/D2 diagram generation."""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Callable, cast
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_diagram_gen = importlib.import_module("plugins.viz.diagram_generator")
generate_mermaid = cast(
    Callable[..., str], _diagram_gen.generate_mermaid
)
generate_d2 = cast(
    Callable[..., str], _diagram_gen.generate_d2
)
render_to_png = cast(
    Callable[..., bool], _diagram_gen.render_to_png
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_graph() -> dict[str, list[str]]:
    """Simple adjacency list with two modules and one edge."""
    return {
        "module_a": ["module_b"],
        "module_b": [],
    }


@pytest.fixture
def multi_lang_graph() -> dict[str, list[str]]:
    """Graph with Python, JS, and Go modules (extension metadata via naming)."""
    return {
        "app": ["utils", "config"],
        "utils": [],
        "config": [],
    }


@pytest.fixture
def complex_graph() -> dict[str, list[str]]:
    """Larger graph for zoom/subgraph testing."""
    return {
        "core": ["db", "cache"],
        "api": ["core", "auth"],
        "auth": ["db"],
        "db": [],
        "cache": [],
        "cli": ["core"],
    }


# ---------------------------------------------------------------------------
# Test 1: generate_mermaid produces graph TD header
# ---------------------------------------------------------------------------

def test_mermaid_produces_graph_td_header(simple_graph: dict[str, list[str]]) -> None:
    """generate_mermaid output starts with 'graph TD'."""
    result = generate_mermaid(simple_graph)
    assert result.startswith("graph TD")


# ---------------------------------------------------------------------------
# Test 2: generate_mermaid includes all modules and edges
# ---------------------------------------------------------------------------

def test_mermaid_includes_all_modules_and_edges(simple_graph: dict[str, list[str]]) -> None:
    """generate_mermaid includes node definitions and edge connections."""
    result = generate_mermaid(simple_graph)
    # Both modules should appear as nodes
    assert "module_a" in result
    assert "module_b" in result
    # Edge from module_a to module_b
    assert "-->" in result


# ---------------------------------------------------------------------------
# Test 3: generate_d2 produces valid D2 syntax with -> connections
# ---------------------------------------------------------------------------

def test_d2_produces_valid_syntax(simple_graph: dict[str, list[str]]) -> None:
    """generate_d2 produces lines with '->' for dependencies."""
    result = generate_d2(simple_graph)
    assert "module_a -> module_b" in result
    # Isolated nodes should still appear
    assert "module_b" in result


# ---------------------------------------------------------------------------
# Test 4: generate_mermaid zoom returns focused subgraph
# ---------------------------------------------------------------------------

def test_mermaid_zoom_returns_focused_subgraph(complex_graph: dict[str, list[str]]) -> None:
    """generate_mermaid(graph, zoom='core') returns only core and its direct deps."""
    result = generate_mermaid(complex_graph, zoom="core")
    assert "graph TD" in result
    # Core and its dependencies (db, cache) should be present
    assert "core" in result
    assert "db" in result
    assert "cache" in result
    # Modules NOT directly related to core should be absent
    assert "auth" not in result
    assert "cli" not in result
    assert "api" not in result


# ---------------------------------------------------------------------------
# Test 5: render_to_png constructs correct mermaid.ink URL (mock urllib)
# ---------------------------------------------------------------------------

def test_render_to_png_constructs_correct_url(tmp_path: Any) -> None:
    """render_to_png base64-encodes mermaid text and calls mermaid.ink API."""
    import base64

    mermaid_text = "graph TD\n    A --> B"
    output_path = str(tmp_path / "diagram.png")

    with patch("plugins.viz.diagram_generator.urllib.request.urlretrieve") as mock_retrieve:
        mock_retrieve.return_value = (output_path, MagicMock())
        result = render_to_png(mermaid_text, output_path)

    assert result is True
    mock_retrieve.assert_called_once()

    # Verify the URL contains correct base64 encoding
    called_url = mock_retrieve.call_args[0][0]
    assert called_url.startswith("https://mermaid.ink/img/")
    encoded_part = called_url.split("https://mermaid.ink/img/")[1]
    decoded = base64.urlsafe_b64decode(encoded_part).decode()
    assert decoded == mermaid_text


# ---------------------------------------------------------------------------
# Test 6: Empty graph produces empty/minimal diagram
# ---------------------------------------------------------------------------

def test_empty_graph_produces_minimal_diagram() -> None:
    """Empty graph returns minimal or empty Mermaid/D2 output."""
    mermaid_result = generate_mermaid({})
    # Should still have header or be empty string
    assert mermaid_result == "" or mermaid_result.startswith("graph TD")

    d2_result = generate_d2({})
    assert d2_result == ""


# ---------------------------------------------------------------------------
# Test 7: Graceful handling of invalid/None graph input
# ---------------------------------------------------------------------------

def test_graceful_handling_of_invalid_input() -> None:
    """None or non-dict inputs return empty string, never raise."""
    assert generate_mermaid(None) == ""  # type: ignore[arg-type]
    assert generate_d2(None) == ""  # type: ignore[arg-type]
    assert generate_mermaid("not a dict") == ""  # type: ignore[arg-type]
    assert generate_d2(42) == ""  # type: ignore[arg-type]


def test_render_to_png_returns_false_on_failure(tmp_path: Any) -> None:
    """render_to_png returns False on network/URL failure, never raises."""
    with patch("plugins.viz.diagram_generator.urllib.request.urlretrieve") as mock_retrieve:
        mock_retrieve.side_effect = Exception("Network error")
        result = render_to_png("graph TD\n    A --> B", str(tmp_path / "out.png"))

    assert result is False


# ---------------------------------------------------------------------------
# Test 8: Color-coding — Python modules get blue style directive
# ---------------------------------------------------------------------------

def test_color_coding_python_modules() -> None:
    """Python modules (.py extension metadata) get blue (#4B8BBE) style."""
    graph = {"app": ["utils"]}
    # Pass language_map to specify which modules are Python
    result = generate_mermaid(graph, language_map={"app": "python", "utils": "python"})
    assert "fill:#4B8BBE" in result


def test_color_coding_js_modules() -> None:
    """JS modules get yellow (#F7DF1E) style."""
    graph = {"index": ["react"]}
    result = generate_mermaid(graph, language_map={"index": "js"})
    assert "fill:#F7DF1E" in result


def test_color_coding_go_modules() -> None:
    """Go modules get cyan (#00ADD8) style."""
    graph = {"main": ["fmt"]}
    result = generate_mermaid(graph, language_map={"main": "go"})
    assert "fill:#00ADD8" in result


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

def test_render_to_png_with_none_input() -> None:
    """render_to_png with empty/None text returns False."""
    assert render_to_png("", "/tmp/out.png") is False
    assert render_to_png(None, "/tmp/out.png") is False  # type: ignore[arg-type]


def test_mermaid_zoom_nonexistent_module(complex_graph: dict[str, list[str]]) -> None:
    """Zooming on a module not in the graph returns empty string."""
    result = generate_mermaid(complex_graph, zoom="nonexistent")
    assert result == ""
