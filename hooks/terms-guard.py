#!/usr/bin/env python3
import re
import sys
from pathlib import Path

HOOKS_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(HOOKS_DIR).parent)
PORTABLE_RUNTIME_ROOT = str(Path(PROJECT_ROOT) / "omg-runtime")
for path in (HOOKS_DIR, PROJECT_ROOT, PORTABLE_RUNTIME_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from hooks._common import bootstrap_runtime_paths, setup_crash_handler, json_input, deny_decision, get_feature_flag

bootstrap_runtime_paths(__file__)
setup_crash_handler("terms-guard", fail_closed=True)

MODEL_TOKENS = ("claude", "codex", "gemini", "kimi", "gpt", "openai", "anthropic")


def _collect_mutation_text(tool_name: str, tool_input: object) -> str:
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return ""
    if not isinstance(tool_input, dict):
        return ""

    parts: list[str] = []
    for key in ("content", "new_string", "old_string", "insert_text", "text"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            parts.append(value)

    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for item in edits:
            if not isinstance(item, dict):
                continue
            for key in ("newText", "oldText", "new_string", "old_string", "content"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    parts.append(value)

    return "\n".join(parts)


def _model_mentions(text: str) -> int:
    seen = {token for token in MODEL_TOKENS if re.search(rf"\b{re.escape(token)}\b", text, flags=re.IGNORECASE)}
    return len(seen)


def _detect_violation_reason(text: str) -> str | None:
    lowered = text.lower()
    has_star = re.search(r"\b(star|starring|upvote)\b", lowered) is not None
    has_share = re.search(r"\b(share|forward|broadcast|cross-model|cross model|copy this prompt|paste this prompt)\b", lowered) is not None
    if has_star and has_share and _model_mentions(lowered) >= 2:
        return "promotion_star_cross_model"

    has_switching = re.search(r"\b(route|switch|proxy|forward|delegate)\b", lowered) is not None
    has_identity_claim = re.search(
        r"\b(tell\s+the\s+user|claim|pretend|masquerade|say\s+this\s+came\s+from|present\s+as)\b",
        lowered,
    ) is not None
    has_hidden = re.search(
        r"\b(hidden|hide\s+this|secretly|without\s+disclos(?:ing|ure)|do\s+not\s+disclose|don['’]?t\s+disclose|undisclosed)\b",
        lowered,
    ) is not None
    if has_switching and has_identity_claim and has_hidden and _model_mentions(lowered) >= 2:
        return "hidden_model_identity_switch"

    has_third_party = re.search(r"\b(third[- ]party|external\s+(?:api|service|vendor)|analytics\s+(?:api|service))\b", lowered) is not None
    has_data = re.search(r"\b(logs?|conversation|prompt|chat\s*history|transcript|user\s*data)\b", lowered) is not None
    has_no_disclosure = re.search(
        r"\b(without\s+(?:user\s+)?disclos(?:ing|ure)|without\s+consent|undisclosed|do\s+not\s+disclose|don['’]?t\s+disclose)\b",
        lowered,
    ) is not None
    if has_third_party and has_data and has_no_disclosure:
        return "undisclosed_third_party_sharing"

    return None


data = json_input()
if not get_feature_flag("TERMS_ENFORCEMENT", default=False):
    sys.exit(0)

tool_name = data.get("tool_name", "") if isinstance(data, dict) else ""
tool_input = data.get("tool_input", {}) if isinstance(data, dict) else {}
mutation_text = _collect_mutation_text(tool_name, tool_input)
if not mutation_text:
    sys.exit(0)

reason = _detect_violation_reason(mutation_text)
if reason is not None:
    deny_decision(f"terms_guard:{reason}")

sys.exit(0)
