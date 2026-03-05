from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_setup_script_does_not_inline_script_dir_into_python_c() -> None:
    script = (ROOT / "OMG-setup.sh").read_text(encoding="utf-8")

    assert "python3 -c \"import json; print(json.load(open('$SCRIPT_DIR/package.json'))['version'])\"" not in script
    assert "sys.argv[1]" in script
