"""Unified multi-language dependency graph builder.

Combines Python AST parser and JS/TS/Go regex parsers into
a single project-wide dependency graph with metrics and persistence.

Feature-gated behind CODEBASE_VIZ (default: off).
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language extension mapping
# ---------------------------------------------------------------------------
_PYTHON_EXTS: frozenset[str] = frozenset({".py"})
_JS_EXTS: frozenset[str] = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})
_GO_EXTS: frozenset[str] = frozenset({".go"})

# ---------------------------------------------------------------------------
# Lazy parser imports — crash-safe
# ---------------------------------------------------------------------------

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def _import_parsers() -> tuple[Any, Any]:
    """Import ast_parser and regex_parser lazily. Returns (ast_mod, regex_mod)."""
    try:
        ast_mod = importlib.import_module("plugins.viz.ast_parser")
    except Exception:
        ast_mod = None
    try:
        regex_mod = importlib.import_module("plugins.viz.regex_parser")
    except Exception:
        regex_mod = None
    return ast_mod, regex_mod


def _get_feature_flag(name: str, default: bool = False) -> bool:
    """Get feature flag value, importing hooks._common if available."""
    # Environment variable always takes precedence
    env_key = f"OMG_{name.upper()}_ENABLED"
    env_val = os.environ.get(env_key, "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    # Try hooks._common
    try:
        _common = importlib.import_module("hooks._common")
        return _common.get_feature_flag(name, default)
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Module naming
# ---------------------------------------------------------------------------

def _module_name_for_path(root: Path, file_path: Path) -> str:
    """Convert a file path to a dotted module name relative to root."""
    rel = file_path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__init__"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    """Deduplicate list while preserving insertion order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

def _collect_files(root: Path) -> dict[str, list[Path]]:
    """Collect project files by language category, excluding hidden/venv dirs."""
    result: dict[str, list[Path]] = {"python": [], "js": [], "go": []}
    if not root.is_dir():
        return result

    skip_dirs = {".omg", ".git", ".venv", "venv", "node_modules", "__pycache__", ".tox"}

    for item in sorted(root.rglob("*")):
        if not item.is_file():
            continue
        # Skip hidden/venv directories
        rel_parts = item.relative_to(root).parts
        if any(p in skip_dirs or p.startswith(".") for p in rel_parts[:-1]):
            continue

        ext = item.suffix
        if ext in _PYTHON_EXTS:
            result["python"].append(item)
        elif ext in _JS_EXTS:
            result["js"].append(item)
        elif ext in _GO_EXTS:
            result["go"].append(item)

    return result


# ---------------------------------------------------------------------------
# Per-language parsing
# ---------------------------------------------------------------------------

def _parse_python_files(
    root: Path,
    files: list[Path],
    ast_mod: Any,
    cached_graph: dict[str, list[str]],
    cached_mtimes: dict[str, float],
    new_mtimes: dict[str, float],
) -> dict[str, list[str]]:
    """Parse Python files into adjacency list entries."""
    graph: dict[str, list[str]] = {}
    if ast_mod is None:
        return graph

    parse_fn = getattr(ast_mod, "parse_python_imports", None)
    if parse_fn is None:
        return graph

    for py_file in files:
        module_name = _module_name_for_path(root, py_file)
        rel_key = str(py_file.relative_to(root))
        current_mtime = py_file.stat().st_mtime

        # Incremental: reuse cached result if mtime unchanged
        if (
            rel_key in cached_mtimes
            and cached_mtimes[rel_key] == current_mtime
            and module_name in cached_graph
        ):
            graph[module_name] = cached_graph[module_name]
        else:
            try:
                imports = parse_fn(str(py_file))
                graph[module_name] = _dedupe_preserve_order(imports)
            except Exception:
                graph[module_name] = []

        new_mtimes[rel_key] = current_mtime

    return graph


def _parse_js_files(
    root: Path,
    files: list[Path],
    regex_mod: Any,
    cached_graph: dict[str, list[str]],
    cached_mtimes: dict[str, float],
    new_mtimes: dict[str, float],
) -> dict[str, list[str]]:
    """Parse JS/TS files into adjacency list entries."""
    graph: dict[str, list[str]] = {}
    if regex_mod is None:
        return graph

    parse_fn = getattr(regex_mod, "parse_js_imports", None)
    if parse_fn is None:
        return graph

    for js_file in files:
        module_name = _module_name_for_path(root, js_file)
        rel_key = str(js_file.relative_to(root))
        current_mtime = js_file.stat().st_mtime

        if (
            rel_key in cached_mtimes
            and cached_mtimes[rel_key] == current_mtime
            and module_name in cached_graph
        ):
            graph[module_name] = cached_graph[module_name]
        else:
            try:
                result = parse_fn(str(js_file))
                graph[module_name] = _dedupe_preserve_order(result.get("imports", []))
            except Exception:
                graph[module_name] = []

        new_mtimes[rel_key] = current_mtime

    return graph


def _parse_go_files(
    root: Path,
    files: list[Path],
    regex_mod: Any,
    cached_graph: dict[str, list[str]],
    cached_mtimes: dict[str, float],
    new_mtimes: dict[str, float],
) -> dict[str, list[str]]:
    """Parse Go files into adjacency list entries."""
    graph: dict[str, list[str]] = {}
    if regex_mod is None:
        return graph

    parse_fn = getattr(regex_mod, "parse_go_imports", None)
    if parse_fn is None:
        return graph

    for go_file in files:
        module_name = _module_name_for_path(root, go_file)
        rel_key = str(go_file.relative_to(root))
        current_mtime = go_file.stat().st_mtime

        if (
            rel_key in cached_mtimes
            and cached_mtimes[rel_key] == current_mtime
            and module_name in cached_graph
        ):
            graph[module_name] = cached_graph[module_name]
        else:
            try:
                result = parse_fn(str(go_file))
                graph[module_name] = _dedupe_preserve_order(result.get("imports", []))
            except Exception:
                graph[module_name] = []

        new_mtimes[rel_key] = current_mtime

    return graph


# ---------------------------------------------------------------------------
# Cycle detection (DFS-based)
# ---------------------------------------------------------------------------

def _detect_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Detect circular dependency cycles via DFS."""
    visited: set[str] = set()
    on_stack: set[str] = set()
    stack: list[str] = []
    cycle_set: set[tuple[str, ...]] = set()

    def dfs(node: str) -> None:
        visited.add(node)
        on_stack.add(node)
        stack.append(node)

        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if nxt not in visited:
                dfs(nxt)
            elif nxt in on_stack:
                start_idx = stack.index(nxt)
                cycle = stack[start_idx:] + [nxt]
                cycle_set.add(_canonical_cycle(cycle))

        stack.pop()
        on_stack.remove(node)

    for module in graph:
        if module not in visited:
            dfs(module)

    return [list(c) for c in sorted(cycle_set)]


def _canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    """Normalize a cycle to a canonical rotation for deduplication."""
    core = cycle[:-1]
    if not core:
        return tuple(cycle)
    rotations = [tuple(core[i:] + core[:i]) for i in range(len(core))]
    minimal = min(rotations)
    return minimal + (minimal[0],)


# ---------------------------------------------------------------------------
# Max depth computation
# ---------------------------------------------------------------------------

def _compute_max_depth(graph: dict[str, list[str]]) -> int:
    """Compute the longest dependency chain depth."""
    def depth(node: str, path: set[str]) -> int:
        best = 0
        for nxt in graph.get(node, []):
            if nxt not in graph or nxt in path:
                continue
            best = max(best, 1 + depth(nxt, path | {nxt}))
        return best

    best_depth = 0
    for module in graph:
        best_depth = max(best_depth, depth(module, {module}))
    return best_depth


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------

def _compute_metrics(graph: dict[str, list[str]], cycles: list[list[str]]) -> dict[str, object]:
    """Compute graph metrics."""
    module_count = len(graph)
    edge_count = sum(len(deps) for deps in graph.values())
    max_depth = _compute_max_depth(graph)
    coupling_score = edge_count / module_count if module_count > 0 else 0.0

    return {
        "module_count": module_count,
        "edge_count": edge_count,
        "max_depth": max_depth,
        "circular_deps": cycles,
        "coupling_score": coupling_score,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load_cached_state(project_dir: Path) -> tuple[dict[str, list[str]], dict[str, float]]:
    """Load previously persisted graph and mtime cache."""
    state_path = project_dir / ".omg" / "state" / "dependency-graph.json"
    if not state_path.exists():
        return {}, {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        graph = data.get("graph", {})
        mtimes = data.get("_mtime_cache", {})
        return graph, mtimes
    except Exception:
        return {}, {}


def _persist(project_dir: Path, payload: dict[str, object]) -> None:
    """Save full graph + metrics to .omg/state/dependency-graph.json."""
    try:
        output_path = project_dir / ".omg" / "state" / "dependency-graph.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        _logger.debug("Failed to persist dependency graph payload", exc_info=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_EMPTY_RESULT: dict[str, object] = {
    "graph": {},
    "metrics": {
        "module_count": 0,
        "edge_count": 0,
        "max_depth": 0,
        "circular_deps": [],
        "coupling_score": 0.0,
    },
}


def build_project_graph(project_dir: str) -> dict[str, object]:
    """Build unified dependency graph across all detected languages.

    Combines Python AST parser and JS/TS/Go regex parsers into a single
    adjacency-list graph with computed metrics.

    Feature-gated behind ``CODEBASE_VIZ`` (default: disabled).
    Supports incremental updates via file mtime tracking.

    Returns:
        dict with keys ``graph`` (adjacency list) and ``metrics``.
    """
    try:
        # Feature flag gate
        if not _get_feature_flag("CODEBASE_VIZ", default=False):
            return dict(_EMPTY_RESULT)

        root = Path(project_dir)
        if not root.is_dir():
            return dict(_EMPTY_RESULT)

        # Load cached state for incremental updates
        cached_graph, cached_mtimes = _load_cached_state(root)
        new_mtimes: dict[str, float] = {}

        # Import parsers
        ast_mod, regex_mod = _import_parsers()

        # Collect files by language
        files_by_lang = _collect_files(root)

        # Parse each language
        unified_graph: dict[str, list[str]] = {}

        py_graph = _parse_python_files(
            root, files_by_lang["python"], ast_mod, cached_graph, cached_mtimes, new_mtimes
        )
        unified_graph.update(py_graph)

        js_graph = _parse_js_files(
            root, files_by_lang["js"], regex_mod, cached_graph, cached_mtimes, new_mtimes
        )
        unified_graph.update(js_graph)

        go_graph = _parse_go_files(
            root, files_by_lang["go"], regex_mod, cached_graph, cached_mtimes, new_mtimes
        )
        unified_graph.update(go_graph)

        # Compute metrics
        cycles = _detect_cycles(unified_graph)
        metrics = _compute_metrics(unified_graph, cycles)

        # Build payload
        payload: dict[str, object] = {
            "graph": unified_graph,
            "metrics": metrics,
            "_mtime_cache": new_mtimes,
        }

        # Persist
        _persist(root, payload)

        return payload

    except Exception:
        # Crash isolation: never raise to caller
        return dict(_EMPTY_RESULT)
