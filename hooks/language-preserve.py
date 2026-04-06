#!/usr/bin/env python3
"""User-language preservation hook (PostToolOutput).

Detects language mismatch and caches user language preference.
Since actual translation would require LLM calls (not available in hooks),
this hook: (1) detects the user's language, (2) caches it to memory,
(3) logs when language mismatch is detected for transparency.
"""

import json
import os
import sys
import time
from pathlib import Path

HOOKS_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(HOOKS_DIR).parent)

for path in (HOOKS_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)


def _detect_language(text: str) -> str:
    try:
        from runtime.language_pipeline import detect_language

        result = detect_language(text)
        return result.language
    except Exception:
        return "unknown"


def _load_cached_lang(project_dir: str) -> str | None:
    try:
        cache_file = Path(project_dir) / ".omg" / "state" / "user-language.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            return data.get("language")
    except Exception:
        pass
    return None


def _save_cached_lang(project_dir: str, language: str) -> None:
    try:
        cache_dir = Path(project_dir) / ".omg" / "state"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "user-language.json").write_text(
            json.dumps(
                {
                    "language": language,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
        )
    except Exception:
        pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")

    tool_input = data.get("toolInput", {})
    tool_result = data.get("toolResult", "")
    user_text = str(tool_input.get("prompt", "") or tool_input.get("message", "") or "")

    if user_text:
        detected = _detect_language(user_text)
        if detected in ("korean", "japanese", "chinese"):
            cached = _load_cached_lang(project_dir)
            if cached != detected:
                _save_cached_lang(project_dir, detected)
                try:
                    log_dir = Path(project_dir) / ".omg" / "state" / "ledger"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    entry = json.dumps(
                        {
                            "type": "language_detection",
                            "detected": detected,
                            "action": "cached_preference",
                            "timestamp": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                            ),
                        }
                    )
                    with open(log_dir / "language-events.jsonl", "a") as f:
                        f.write(entry + "\n")
                except Exception:
                    pass

    # Hook doesn't modify the output — just observes and caches
    # The actual language preservation happens at prompt level via language_pipeline.py
    sys.exit(0)


if __name__ == "__main__":
    main()
