from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Pattern:
    type: str
    name: str
    frequency: int
    location: str
    snippet: str


PatternCollection = list[Pattern]


class ASTExtractor:
    _cache: dict[str, PatternCollection] = {}

    def extract(self, file_path: str) -> PatternCollection:
        import claude_experimental.patterns as patterns

        getattr(patterns, "_require_enabled")()

        path = Path(file_path)
        content = path.read_text(encoding="utf-8", errors="ignore")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        cached = self._cache.get(content_hash)
        if cached is not None:
            return list(cached)

        if path.suffix == ".py":
            patterns = self._extract_python_patterns(content=content, file_path=file_path)
        else:
            patterns = self._extract_regex_patterns(content=content, file_path=file_path)

        self._cache[content_hash] = list(patterns)
        return patterns

    def _extract_python_patterns(self, content: str, file_path: str) -> PatternCollection:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._extract_regex_patterns(content=content, file_path=file_path)

        lines = content.splitlines()
        records: list[tuple[str, str, int, str, str]] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                snippet = self._source_for_node(content=content, lines=lines, node=node)
                records.append(("function", node.name, node.lineno, f"{file_path}:{node.lineno}", snippet))

            elif isinstance(node, ast.ClassDef):
                class_snippet = self._source_for_node(content=content, lines=lines, node=node)
                records.append(("class", node.name, node.lineno, f"{file_path}:{node.lineno}", class_snippet))

                base_names = [self._ast_name(base) for base in node.bases]
                if base_names:
                    hierarchy = f"{node.name}({', '.join(base_names)})"
                    records.append(("class_hierarchy", hierarchy, node.lineno, f"{file_path}:{node.lineno}", class_snippet))

            elif isinstance(node, ast.Import):
                snippet = self._source_for_node(content=content, lines=lines, node=node)
                for alias in node.names:
                    records.append(("import", alias.name, node.lineno, f"{file_path}:{node.lineno}", snippet))

            elif isinstance(node, ast.ImportFrom):
                snippet = self._source_for_node(content=content, lines=lines, node=node)
                module_name = node.module or ""
                for alias in node.names:
                    imported = f"{module_name}.{alias.name}" if module_name else alias.name
                    records.append(("import", imported, node.lineno, f"{file_path}:{node.lineno}", snippet))

            elif isinstance(node, ast.Try):
                snippet = self._source_for_node(content=content, lines=lines, node=node)
                records.append(("error_handling", "try_except", node.lineno, f"{file_path}:{node.lineno}", snippet))

            elif isinstance(node, ast.For):
                snippet = self._source_for_node(content=content, lines=lines, node=node)
                records.append(("loop", "for_loop", node.lineno, f"{file_path}:{node.lineno}", snippet))

            elif isinstance(node, ast.While):
                snippet = self._source_for_node(content=content, lines=lines, node=node)
                records.append(("loop", "while_loop", node.lineno, f"{file_path}:{node.lineno}", snippet))

            elif isinstance(node, ast.If):
                snippet = self._source_for_node(content=content, lines=lines, node=node)
                records.append(("conditional", "if_statement", node.lineno, f"{file_path}:{node.lineno}", snippet))

        return self._with_frequencies(records)

    def _extract_regex_patterns(self, content: str, file_path: str) -> PatternCollection:
        rules = [
            ("function", re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)),
            ("class", re.compile(r"^\s*class\s+([A-Za-z_]\w*)", re.MULTILINE)),
            ("import", re.compile(r"^\s*import\s+([A-Za-z0-9_\.]+)", re.MULTILINE)),
            ("function", re.compile(r"^\s*function\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)),
        ]

        lines = content.splitlines()
        records: list[tuple[str, str, int, str, str]] = []

        for pattern_type, regex in rules:
            for match in regex.finditer(content):
                name = match.group(1)
                line = content.count("\n", 0, match.start()) + 1
                snippet = lines[line - 1].strip() if line - 1 < len(lines) else match.group(0).strip()
                records.append((pattern_type, name, line, f"{file_path}:{line}", snippet))

        return self._with_frequencies(records)

    @staticmethod
    def _source_for_node(content: str, lines: list[str], node: ast.AST) -> str:
        segment = ast.get_source_segment(content, node)
        if segment:
            return segment.strip()

        lineno = getattr(node, "lineno", 1)
        if 1 <= lineno <= len(lines):
            return lines[lineno - 1].strip()
        return ""

    @staticmethod
    def _ast_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = ASTExtractor._ast_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        if isinstance(node, ast.Subscript):
            return ASTExtractor._ast_name(node.value)
        if isinstance(node, ast.Call):
            return ASTExtractor._ast_name(node.func)
        return "unknown"

    @staticmethod
    def _with_frequencies(records: list[tuple[str, str, int, str, str]]) -> PatternCollection:
        counts: dict[tuple[str, str], int] = {}
        for pattern_type, name, _, _, _ in records:
            key = (pattern_type, name)
            counts[key] = counts.get(key, 0) + 1

        records.sort(key=lambda item: (item[2], item[0], item[1]))

        patterns: PatternCollection = []
        for pattern_type, name, _, location, snippet in records:
            patterns.append(
                Pattern(
                    type=pattern_type,
                    name=name,
                    frequency=counts[(pattern_type, name)],
                    location=location,
                    snippet=snippet,
                )
            )
        return patterns
