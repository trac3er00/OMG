from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "hooks" / "prompt-enhancer.py"


def _load_pipeline_functions():
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    keep = {
        "signal_matches_text",
        "classify_intent",
        "route_mode",
        "inject_context",
        "emit_output",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in keep
    ]
    module = ast.Module(body=selected, type_ignores=[])
    namespace: dict[str, object] = {
        "re": re,
        "_KOREAN_CHAR_RE": re.compile(r"[\uac00-\ud7a3]"),
    }
    exec(compile(module, str(SCRIPT), "exec"), namespace)
    return namespace


def test_pipeline_stage_outputs_are_composable() -> None:
    ns = _load_pipeline_functions()
    classify_intent = ns["classify_intent"]
    route_mode = ns["route_mode"]
    inject_context = ns["inject_context"]
    emit_output = ns["emit_output"]

    intent_map = {
        "fix": {
            "signals": ["fix", "bug"],
            "directive": "FIX",
        }
    }
    intent = classify_intent("fix this auth bug", intent_map)
    is_ulw, is_crazy = route_mode("crazy fix this auth bug")

    context: list[str] = []
    context = inject_context(context, f"@intent:{intent}", 240)
    if is_crazy:
        context = inject_context(context, "@mode:CRAZY", 240)
    if is_ulw:
        context = inject_context(context, "@mode:PERSISTENT", 240)
    output = emit_output(context, 240)

    assert "@intent:fix" in output
    assert "@mode:CRAZY" in output
