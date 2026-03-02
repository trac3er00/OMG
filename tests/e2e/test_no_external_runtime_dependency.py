"""Guardrails: runtime code must not require external companion installation."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_runtime_paths_have_no_external_hard_dependency():
    targets = [
        ROOT / "scripts" / "oal.py",
        ROOT / "OAL-setup.sh",
        ROOT / "install.sh",
    ]
    targets.extend((ROOT / "hooks").glob("*.py"))
    targets.extend((ROOT / "runtime").rglob("*.py"))

    banned = [
        "OMC_STATE_DIR",
        "OAL_COEXIST_MODE",
        "oh-my-claudecode",
        "/omc-setup",
        "/omc-doctor",
    ]

    violations: list[str] = []
    for file in targets:
        content = _read(file)
        for token in banned:
            if token in content:
                violations.append(f"{file.relative_to(ROOT)} contains {token}")

    assert not violations, "Runtime hard dependency detected:\n" + "\n".join(violations)
