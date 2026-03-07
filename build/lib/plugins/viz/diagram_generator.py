"""Mermaid and D2 diagram generator for dependency graphs.

Converts adjacency-list dependency graphs (from graph_builder.py) into
Mermaid and D2 diagram text, with optional PNG rendering via mermaid.ink.

All functions are crash-isolated: they return empty strings or False on error,
never raise exceptions to the caller.

Feature-gated behind CODEBASE_VIZ for hook integration, but library functions
work independently of the flag.
"""

from __future__ import annotations

import base64
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Language → color mapping for Mermaid style directives
# ---------------------------------------------------------------------------

_LANG_COLORS: dict[str, str] = {
    "python": "#4B8BBE",
    "py": "#4B8BBE",
    "js": "#F7DF1E",
    "javascript": "#F7DF1E",
    "ts": "#F7DF1E",
    "typescript": "#F7DF1E",
    "go": "#00ADD8",
    "golang": "#00ADD8",
}


def _sanitize_node_id(name: str) -> str:
    """Convert a module name to a valid Mermaid/D2 node identifier.

    Replaces dots and hyphens with underscores to avoid syntax issues.
    """
    return name.replace(".", "_").replace("-", "_")


# ---------------------------------------------------------------------------
# Mermaid generation
# ---------------------------------------------------------------------------


def generate_mermaid(
    graph: dict[str, list[str]] | None,
    *,
    zoom: str | None = None,
    language_map: dict[str, str] | None = None,
) -> str:
    """Generate Mermaid ``graph TD`` text from an adjacency-list graph.

    Args:
        graph: Adjacency list ``{module: [dep1, dep2, ...]}``.
        zoom: If provided, return a focused subgraph showing only this
              module and its direct dependencies.
        language_map: Optional mapping of ``{module_name: language}`` for
                      color-coding nodes by language.

    Returns:
        Mermaid diagram text, or empty string on error/empty input.
    """
    try:
        if not isinstance(graph, dict) or not graph:
            return ""

        # Zoom: filter to only the target module + its direct deps
        if zoom is not None:
            if zoom not in graph:
                return ""
            deps = graph[zoom]
            filtered: dict[str, list[str]] = {zoom: deps}
            for dep in deps:
                if dep in graph:
                    # Include dep node but only edges within the zoom scope
                    filtered[dep] = []
                else:
                    filtered[dep] = []
            graph = filtered

        lines: list[str] = ["graph TD"]

        # Collect all unique nodes (both sources and targets)
        all_nodes: set[str] = set()
        for module, deps in graph.items():
            all_nodes.add(module)
            for dep in deps:
                all_nodes.add(dep)

        # Emit node definitions
        for node in sorted(all_nodes):
            node_id = _sanitize_node_id(node)
            lines.append(f'    {node_id}["{node}"]')

        # Emit edges
        for module in sorted(graph):
            src_id = _sanitize_node_id(module)
            for dep in graph[module]:
                dst_id = _sanitize_node_id(dep)
                lines.append(f"    {src_id} --> {dst_id}")

        # Emit style directives for language color-coding
        if language_map:
            for node in sorted(all_nodes):
                lang = language_map.get(node)
                if lang:
                    color = _LANG_COLORS.get(lang.lower())
                    if color:
                        node_id = _sanitize_node_id(node)
                        lines.append(f"    style {node_id} fill:{color}")

        return "\n".join(lines)

    except Exception:
        return ""


# ---------------------------------------------------------------------------
# D2 generation
# ---------------------------------------------------------------------------


def generate_d2(graph: dict[str, list[str]] | None) -> str:
    """Generate D2 diagram text from an adjacency-list graph.

    Args:
        graph: Adjacency list ``{module: [dep1, dep2, ...]}``.

    Returns:
        D2 diagram text, or empty string on error/empty input.
    """
    try:
        if not isinstance(graph, dict) or not graph:
            return ""

        lines: list[str] = []
        emitted_nodes: set[str] = set()

        for module in sorted(graph):
            deps = graph[module]
            if deps:
                for dep in deps:
                    lines.append(f"{module} -> {dep}")
                    emitted_nodes.add(module)
                    emitted_nodes.add(dep)
            else:
                # Isolated node with no dependencies
                if module not in emitted_nodes:
                    lines.append(module)
                    emitted_nodes.add(module)

        return "\n".join(lines)

    except Exception:
        return ""


# ---------------------------------------------------------------------------
# PNG rendering via mermaid.ink
# ---------------------------------------------------------------------------


def render_to_png(
    mermaid_text: str | None,
    output_path: str,
) -> bool:
    """Render Mermaid text to a PNG file via the mermaid.ink public API.

    Constructs URL: ``https://mermaid.ink/img/{base64_encoded}``
    Downloads the PNG using ``urllib.request.urlretrieve``.

    Args:
        mermaid_text: Valid Mermaid diagram text.
        output_path: File path where the PNG will be saved.

    Returns:
        True on success, False on any failure (never raises).
    """
    try:
        if not mermaid_text or not isinstance(mermaid_text, str):
            return False

        encoded = base64.urlsafe_b64encode(mermaid_text.encode()).decode()
        url = f"https://mermaid.ink/img/{encoded}"
        urllib.request.urlretrieve(url, output_path)
        return True

    except Exception:
        return False
