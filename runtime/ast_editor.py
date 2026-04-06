"""AST precision editing with multi-pattern replace and undo support.

Uses ast-grep for pattern-based code transformation when available.
Supports multi-pattern replace, extract function, and undo history.
"""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EditOperation:
    file_path: str
    pattern: str
    replacement: str
    language: str
    backup_content: str = ""
    applied: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class EditResult:
    success: bool
    file_path: str
    replacements_made: int
    original_content: str = ""
    new_content: str = ""
    error: str = ""


class ASTEditor:
    """Multi-pattern AST editor with undo capability."""

    def __init__(self) -> None:
        self._history: list[EditOperation] = []

    def multi_replace(
        self,
        file_path: str | Path,
        patterns: list[tuple[str, str]],
        language: str = "python",
    ) -> list[EditResult]:
        """Apply multiple pattern replacements to a file.

        Tries ast-grep first for structural replacement and gracefully falls back
        to direct string replacement when ast-grep is unavailable or the pattern
        is not compatible.
        """
        target = Path(file_path)
        if not target.exists():
            return [
                EditResult(
                    success=False,
                    file_path=str(target),
                    replacements_made=0,
                    error="File not found",
                )
            ]

        current = target.read_text(encoding="utf-8")
        results: list[EditResult] = []

        for pattern, replacement in patterns:
            result = self._apply_pattern(
                file_path=str(target),
                content=current,
                pattern=pattern,
                replacement=replacement,
                language=language,
            )
            results.append(result)

            if not result.success:
                continue

            self._history.append(
                EditOperation(
                    file_path=str(target),
                    pattern=pattern,
                    replacement=replacement,
                    language=language,
                    backup_content=current,
                    applied=True,
                )
            )
            current = result.new_content
            _ = target.write_text(current, encoding="utf-8")

        return results

    def extract_function(
        self,
        file_path: str | Path,
        source_snippet: str,
        function_name: str,
        *,
        language: str = "python",
        parameters: list[str] | None = None,
    ) -> EditResult:
        """Extract an exact source snippet into a new function.

        This intentionally uses a conservative exact-snippet strategy so it can
        operate without ast-grep. It is currently tailored for Python source.
        """
        target = Path(file_path)
        if not target.exists():
            return EditResult(
                success=False,
                file_path=str(target),
                replacements_made=0,
                error="File not found",
            )
        if language != "python":
            return EditResult(
                success=False,
                file_path=str(target),
                replacements_made=0,
                error=f"extract_function does not support language: {language}",
            )

        original = target.read_text(encoding="utf-8")
        if source_snippet not in original:
            return EditResult(
                success=False,
                file_path=str(target),
                replacements_made=0,
                original_content=original,
                new_content=original,
                error="Source snippet not found",
            )

        params = parameters or []
        indent = self._leading_indent(source_snippet)
        trimmed_body = self._dedent_block(source_snippet)
        function_def = self._build_python_function(function_name, params, trimmed_body)
        call_line = f"{indent}{function_name}({', '.join(params)})"
        updated = original.replace(source_snippet, call_line, 1)
        updated = self._append_function(updated, function_def)

        self._history.append(
            EditOperation(
                file_path=str(target),
                pattern=source_snippet,
                replacement=call_line,
                language=language,
                backup_content=original,
                applied=True,
                metadata={"operation": "extract_function", "function_name": function_name},
            )
        )
        _ = target.write_text(updated, encoding="utf-8")
        return EditResult(
            success=True,
            file_path=str(target),
            replacements_made=1,
            original_content=original,
            new_content=updated,
        )

    def _apply_pattern(
        self,
        file_path: str,
        content: str,
        pattern: str,
        replacement: str,
        language: str,
    ) -> EditResult:
        """Apply a single pattern, preferring ast-grep when available."""
        ast_result = self._apply_with_ast_grep(content, pattern, replacement, language)
        if ast_result is not None:
            return EditResult(
                success=ast_result != content,
                file_path=file_path,
                replacements_made=1 if ast_result != content else 0,
                original_content=content,
                new_content=ast_result,
                error="" if ast_result != content else f"Pattern not found: {pattern[:50]}",
            )

        if pattern in content:
            new_content = content.replace(pattern, replacement)
            return EditResult(
                success=True,
                file_path=file_path,
                replacements_made=content.count(pattern),
                original_content=content,
                new_content=new_content,
            )

        return EditResult(
            success=False,
            file_path=file_path,
            replacements_made=0,
            original_content=content,
            new_content=content,
            error=f"Pattern not found: {pattern[:50]}",
        )

    def _apply_with_ast_grep(
        self,
        content: str,
        pattern: str,
        replacement: str,
        language: str,
    ) -> str | None:
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=self._get_suffix(language),
                delete=False,
                encoding="utf-8",
            ) as tmp:
                _ = tmp.write(content)
                tmp_path = tmp.name

            result = subprocess.run(
                [
                    "sg",
                    "--pattern",
                    pattern,
                    "--rewrite",
                    replacement,
                    "--lang",
                    language,
                    tmp_path,
                    "--update-all",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                return None
            return Path(tmp_path).read_text(encoding="utf-8")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        finally:
            if tmp_path is not None:
                try:
                    Path(tmp_path).unlink()
                except OSError:
                    pass

    def _get_suffix(self, language: str) -> str:
        return {
            "python": ".py",
            "typescript": ".ts",
            "javascript": ".js",
            "rust": ".rs",
            "go": ".go",
        }.get(language, ".txt")

    def _leading_indent(self, snippet: str) -> str:
        first_line = next((line for line in snippet.splitlines() if line.strip()), "")
        return first_line[: len(first_line) - len(first_line.lstrip())]

    def _dedent_block(self, snippet: str) -> str:
        lines = snippet.splitlines()
        non_empty = [line for line in lines if line.strip()]
        if not non_empty:
            return ""
        indent = min(len(line) - len(line.lstrip()) for line in non_empty)
        return "\n".join(line[indent:] if line.strip() else "" for line in lines)

    def _build_python_function(self, function_name: str, parameters: list[str], body: str) -> str:
        body_lines = body.splitlines() or ["pass"]
        indented_body = "\n".join(f"    {line}" if line else "" for line in body_lines)
        params = ", ".join(parameters)
        return f"def {function_name}({params}):\n{indented_body}\n"

    def _append_function(self, content: str, function_def: str) -> str:
        stripped = content.rstrip()
        return f"{stripped}\n\n\n{function_def}"

    def undo_last(self) -> bool:
        """Undo the last applied edit operation."""
        for op in reversed(self._history):
            if not op.applied:
                continue
            try:
                _ = Path(op.file_path).write_text(op.backup_content, encoding="utf-8")
            except OSError:
                return False
            op.applied = False
            return True
        return False

    def get_history(self) -> list[dict[str, object]]:
        return [
            {
                "file": op.file_path,
                "pattern": op.pattern,
                "replacement": op.replacement,
                "language": op.language,
                "applied": op.applied,
                **({"metadata": op.metadata} if op.metadata else {}),
            }
            for op in self._history
        ]
