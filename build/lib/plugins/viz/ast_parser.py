from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import override


def parse_python_imports(file_path: str) -> list[str]:
    source = Path(file_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    collector = _ImportCollector()
    collector.visit(tree)
    return collector.imports


def build_dependency_graph(project_dir: str) -> dict[str, object]:
    root = Path(project_dir)
    py_files = sorted(root.rglob("*.py"))

    graph: dict[str, list[str]] = {}
    for py_file in py_files:
        module_name = _module_name_for_path(root, py_file)
        imports = parse_python_imports(str(py_file))
        graph[module_name] = _dedupe_preserve_order(imports)

    cycles = _detect_cycles(graph)
    stats = {
        "module_count": len(graph),
        "edge_count": sum(len(edges) for edges in graph.values()),
        "max_depth": _compute_max_depth(graph),
        "has_cycles": bool(cycles),
    }

    payload: dict[str, object] = {
        "graph": graph,
        "cycles": cycles,
        "stats": stats,
    }

    output_path = root / ".omg" / "state" / "dependency-graph.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    return payload


class _ImportCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: list[str] = []

    @override
    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self.imports.append(alias.name)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.level > 0:
            prefix = "." * node.level
            self.imports.append(f"{prefix}{node.module or ''}")
            return

        if node.module:
            self.imports.append(node.module)


def _module_name_for_path(root: Path, py_file: Path) -> str:
    rel = py_file.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__init__"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _detect_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
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

        _ = stack.pop()
        on_stack.remove(node)

    for module in graph:
        if module not in visited:
            dfs(module)

    return [list(cycle) for cycle in sorted(cycle_set)]


def _canonical_cycle(cycle: list[str]) -> tuple[str, ...]:
    core = cycle[:-1]
    if not core:
        return tuple(cycle)

    rotations = [tuple(core[idx:] + core[:idx]) for idx in range(len(core))]
    minimal = min(rotations)
    return minimal + (minimal[0],)


def _compute_max_depth(graph: dict[str, list[str]]) -> int:
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
