import ast
import re
from pathlib import Path
from typing import Any


_CRITICAL_PATTERN = re.compile(r"\bcritical\b", re.IGNORECASE)
_HIGH_PATTERN = re.compile(r"\bhigh\b", re.IGNORECASE)


def analyze_reachability(cve_result: dict[str, Any], project_dir: str) -> dict[str, Any]:
    package = str(cve_result.get("package", "")).strip()
    cve_id = str(cve_result.get("id", "")).strip()
    summary = str(cve_result.get("summary", "")).strip()
    fixed_version = str(cve_result.get("fixed_version", "")).strip()

    imported_files: list[str] = []
    usage_found = False

    for py_file in Path(project_dir).rglob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        imported, used = _inspect_python_file(source, package)
        if imported:
            imported_files.append(py_file.relative_to(project_dir).as_posix())
        if used:
            usage_found = True

    reachability = _classify_reachability(imported_files, usage_found)
    risk_level = _classify_risk(reachability, summary)
    recommendation = _build_recommendation(package, fixed_version, reachability)

    return {
        "package": package,
        "cve_id": cve_id,
        "reachability": reachability,
        "import_locations": sorted(imported_files),
        "risk_level": risk_level,
        "recommendation": recommendation,
    }


def _inspect_python_file(source: str, package: str) -> tuple[bool, bool]:
    imported, module_aliases, imported_symbols = _grep_like_import_scan(source, package)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imported, False

    ast_imported, ast_module_aliases, ast_imported_symbols = _ast_import_scan(tree, package)
    imported = imported or ast_imported
    module_aliases.update(ast_module_aliases)
    imported_symbols.update(ast_imported_symbols)

    used = _ast_usage_scan(tree, module_aliases, imported_symbols)
    return imported, used


def _grep_like_import_scan(source: str, package: str) -> tuple[bool, set[str], set[str]]:
    imported = False
    module_aliases: set[str] = set()
    imported_symbols: set[str] = set()

    if not package:
        return imported, module_aliases, imported_symbols

    pkg = re.escape(package)
    import_re = re.compile(rf"^\s*import\s+{pkg}(?:\.|\s|,|$)", re.MULTILINE)
    from_re = re.compile(rf"^\s*from\s+{pkg}(?:\.|\s)", re.MULTILINE)
    alias_re = re.compile(rf"^\s*import\s+{pkg}\s+as\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
    from_names_re = re.compile(rf"^\s*from\s+{pkg}(?:\.[A-Za-z0-9_\.]+)?\s+import\s+(.+)$", re.MULTILINE)

    if import_re.search(source) or from_re.search(source):
        imported = True

    module_aliases.add(package.split(".")[0])
    for match in alias_re.findall(source):
        module_aliases.add(match)

    for line in from_names_re.findall(source):
        for item in line.split(","):
            part = item.strip()
            if not part:
                continue
            if " as " in part:
                imported_symbols.add(part.rsplit(" as ", 1)[1].strip())
            else:
                imported_symbols.add(part)

    return imported, module_aliases, imported_symbols


def _ast_import_scan(tree: ast.AST, package: str) -> tuple[bool, set[str], set[str]]:
    imported = False
    module_aliases: set[str] = set()
    imported_symbols: set[str] = set()

    if not package:
        return imported, module_aliases, imported_symbols

    root = package.split(".")[0]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == package or alias.name.startswith(f"{package}."):
                    imported = True
                    module_aliases.add(alias.asname or alias.name.split(".")[0])
                elif alias.name.split(".")[0] == root:
                    imported = True
                    module_aliases.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == package or node.module.startswith(f"{package}."):
                imported = True
                for alias in node.names:
                    imported_symbols.add(alias.asname or alias.name)
            elif node.module.split(".")[0] == root:
                imported = True
                for alias in node.names:
                    imported_symbols.add(alias.asname or alias.name)

    return imported, module_aliases, imported_symbols


def _ast_usage_scan(tree: ast.AST, module_aliases: set[str], imported_symbols: set[str]) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in module_aliases or func.value.id in imported_symbols:
                return True
        elif isinstance(func, ast.Name) and func.id in imported_symbols:
            return True

    return False


def _classify_reachability(imported_files: list[str], usage_found: bool) -> str:
    if usage_found:
        return "REACHABLE"
    if imported_files:
        return "POTENTIALLY_REACHABLE"
    return "UNREACHABLE"


def _classify_risk(reachability: str, summary: str) -> str:
    if reachability == "UNREACHABLE":
        return "LOW"
    if reachability == "POTENTIALLY_REACHABLE":
        return "MEDIUM"
    if _CRITICAL_PATTERN.search(summary):
        return "CRITICAL"
    if _HIGH_PATTERN.search(summary):
        return "HIGH"
    return "HIGH"


def _build_recommendation(package: str, fixed_version: str, reachability: str) -> str:
    if reachability == "UNREACHABLE":
        return "No action needed (unreachable)"
    if fixed_version:
        return f"Upgrade {package} to {fixed_version}"
    return f"Upgrade {package} to a fixed version"
