"""OAL Natives — image: image file info via stdlib.

Pure-Python fallback for image file metadata retrieval.
Uses ``os.path`` and ``pathlib`` — no PIL/Pillow dependency.

Feature flag: ``OAL_RUST_ENGINE_ENABLED`` (default: False)
"""

from __future__ import annotations

import os
from pathlib import Path

from oal_natives._bindings import bind_function


def image(path: str, operation: str = "info") -> dict:
    """Get image file information.

    Operations:

    - ``"info"``: returns ``{"path": str, "size_bytes": int, "exists": bool, "extension": str}``

    No PIL/Pillow dependency — stdlib only.
    """
    if operation == "info":
        p = Path(path)
        exists = p.exists()
        size_bytes = 0
        if exists:
            try:
                size_bytes = os.path.getsize(path)
            except OSError:
                pass
        return {
            "path": str(p),
            "size_bytes": size_bytes,
            "exists": exists,
            "extension": p.suffix,
        }
    else:
        return {"path": path, "size_bytes": 0, "exists": False, "extension": ""}


# Self-register with the global binding registry
bind_function(
    name="image",
    rust_symbol="oal_natives::image::image",
    python_fallback=image,
    type_hints={"path": "str", "operation": "str"},
)
