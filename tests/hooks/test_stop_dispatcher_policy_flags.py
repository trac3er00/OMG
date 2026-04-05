from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "hooks" / "stop_dispatcher.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("stop_dispatcher_hook", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reads_require_evidence_pack_from_nested_yaml(tmp_path: Path) -> None:
    policy_dir = tmp_path / ".omg"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "policy.yaml").write_text(
        """
policy:
  mode: strict
  require_evidence_pack: true
""".strip()
        + "\n",
        encoding="utf-8",
    )

    module = _load_module()
    mode, require_evidence_pack = module._read_policy_flags(str(tmp_path))

    assert mode == "strict"
    assert require_evidence_pack is True
