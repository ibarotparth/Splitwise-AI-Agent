import re
from typing import Optional


def find_group(groups: list[dict], name: str) -> Optional[dict]:
    """
    Resolve a group by name with progressively looser matching.
    Returns the group dict, or None if no match found.
    """
    if not name:
        return None

    target = name.strip().lower()

    # 1. Exact case-insensitive match
    for g in groups:
        if g["name"].strip().lower() == target:
            return g

    # 2. Substring match
    for g in groups:
        if target in g["name"].strip().lower():
            return g

    # 3. Alphanumerics-only match
    target_norm = _normalize(target)
    if not target_norm:
        return None

    for g in groups:
        if _normalize(g["name"]) == target_norm:
            return g

    for g in groups:
        if target_norm in _normalize(g["name"]):
            return g

    return None


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())
