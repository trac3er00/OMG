from __future__ import annotations

import math
import re
from collections import Counter
from typing import cast

_CANDIDATE_PATTERN = re.compile(r"[A-Za-z0-9+/=_\-.]{21,}")
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_HEX_HASH_PATTERN = re.compile(r"^[0-9a-f]{32,64}$", re.IGNORECASE)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _is_allowlisted_candidate(candidate: str) -> bool:
    lowered = candidate.lower()
    if lowered.startswith("data:image/"):
        return True
    if _UUID_PATTERN.match(candidate):
        return True
    if _HEX_HASH_PATTERN.match(candidate):
        return True
    return False


def detect_high_entropy_strings(text: str, entropy_threshold: float = 4.5, min_length: int = 21) -> list[str]:
    findings: list[str] = []
    seen: set[str] = set()
    for candidate in cast(list[str], _CANDIDATE_PATTERN.findall(text)):
        if candidate in seen:
            continue
        seen.add(candidate)
        if len(candidate) < min_length or _is_allowlisted_candidate(candidate):
            continue
        if _shannon_entropy(candidate) > entropy_threshold:
            findings.append(candidate)
    return findings
