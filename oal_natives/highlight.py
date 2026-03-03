"""OAL Natives — highlight: basic syntax highlighting.

Pure-Python fallback that returns code unchanged (no Pygments dependency).
Optionally wraps code with a language comment header.

Feature flag: ``OAL_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

from oal_natives._bindings import bind_function

# Known language comment prefixes
_COMMENT_STYLES = {
    "python": "#",
    "javascript": "//",
    "typescript": "//",
    "rust": "//",
    "go": "//",
    "java": "//",
    "c": "//",
    "cpp": "//",
    "ruby": "#",
    "bash": "#",
    "shell": "#",
    "sh": "#",
    "yaml": "#",
    "toml": "#",
}


def highlight(code: str, language: str = "") -> str:
    """Basic syntax highlighting — returns code unchanged (no Pygments).

    If *language* is known, prepends a comment header indicating the language.
    Otherwise returns *code* as-is.
    """
    if not language:
        return code

    lang_lower = language.lower()
    comment = _COMMENT_STYLES.get(lang_lower)
    if comment:
        return f"{comment} [{lang_lower}]\n{code}"
    return code


# Self-register with the global binding registry
bind_function(
    name="highlight",
    rust_symbol="oal_natives::highlight::highlight",
    python_fallback=highlight,
    type_hints={"code": "str", "language": "str"},
)
