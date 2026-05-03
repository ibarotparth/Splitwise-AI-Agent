"""
Multi-strategy participant name matching.

Returns matches with confidence scores so the caller can decide whether to
proceed automatically or ask the user to disambiguate.
"""
from dataclasses import dataclass
from typing import Optional


# Confidence thresholds
HIGH_CONFIDENCE = 0.85    # auto-pick
LOW_CONFIDENCE = 0.50     # below this → ignore


@dataclass(frozen=True)
class Person:
    id: int
    first_name: str
    last_name: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class Match:
    person: Person
    confidence: float
    reason: str


@dataclass(frozen=True)
class MatchResult:
    query: str
    matches: list[Match]

    @property
    def best(self) -> Optional[Match]:
        return self.matches[0] if self.matches else None

    @property
    def is_unambiguous(self) -> bool:
        """True when there's exactly one high-confidence match."""
        if not self.matches:
            return False
        if self.best.confidence < HIGH_CONFIDENCE:
            return False
        # If there's a second match with same confidence, it's ambiguous
        if len(self.matches) > 1 and self.matches[1].confidence >= HIGH_CONFIDENCE:
            return False
        return True

    @property
    def needs_disambiguation(self) -> bool:
        """True when there are multiple plausible matches."""
        if len(self.matches) < 2:
            return False
        return self.matches[1].confidence >= LOW_CONFIDENCE


def people_from_friends(friends: list[dict]) -> list[Person]:
    return [
        Person(
            id=f["id"],
            first_name=f.get("first_name", "") or "",
            last_name=f.get("last_name", "") or "",
        )
        for f in friends
        if f.get("id") is not None
    ]


def people_from_group_members(members: list[dict]) -> list[Person]:
    return [
        Person(
            id=m["id"],
            first_name=m.get("first_name", "") or "",
            last_name=m.get("last_name", "") or "",
        )
        for m in members
        if m.get("id") is not None
    ]


def match_name(
    query: str,
    candidates: list[Person],
    *,
    boost_first: bool = False,
) -> MatchResult:
    """
    Match a single name query against a candidate pool.
    `boost_first=True` adds 0.05 to scores when candidates come from a group
    context (group members are preferred over generic friends).
    """
    q = (query or "").strip().lower()
    if not q:
        return MatchResult(query=query, matches=[])

    boost = 0.05 if boost_first else 0.0
    matches: list[Match] = []

    for p in candidates:
        first = p.first_name.lower()
        last = p.last_name.lower()
        full = p.full_name.lower()

        score = 0.0
        reason = ""

        if full == q:
            score, reason = 1.0, "exact full match"
        elif first == q:
            score, reason = 0.95, "exact first name"
        elif last == q:
            score, reason = 0.85, "exact last name"
        elif full.startswith(q) and len(q) >= 3:
            score, reason = 0.80, "prefix match"
        elif first.startswith(q) and len(q) >= 3:
            score, reason = 0.75, "first name prefix"
        elif q in full and len(q) >= 3:
            score, reason = 0.65, "substring match"
        elif _levenshtein(q, first) <= 1 and len(q) >= 3:
            score, reason = 0.60, "close to first name"

        if score > 0:
            matches.append(
                Match(person=p, confidence=min(1.0, score + boost), reason=reason)
            )

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return MatchResult(query=query, matches=matches)


def resolve_participants(
    queries: list[str],
    *,
    group_members: list[Person],
    friends: list[Person],
) -> tuple[list[Person], list[MatchResult]]:
    """
    Resolve a list of name strings into Person objects.
    Searches group members first (with confidence boost), then friends.

    Returns:
        (resolved, unresolved_or_ambiguous)
        resolved: high-confidence unambiguous matches
        unresolved_or_ambiguous: results that need user input
    """
    resolved: list[Person] = []
    needs_input: list[MatchResult] = []
    seen_ids: set[int] = set()

    for query in queries:
        # 1. Try group members first — if we get an unambiguous match here,
        #    prefer it over any friend with the same name.
        if group_members:
            group_result = match_name(query, group_members, boost_first=True)
            if (
                group_result.is_unambiguous
                and group_result.best.person.id not in seen_ids
            ):
                resolved.append(group_result.best.person)
                seen_ids.add(group_result.best.person.id)
                continue

        # 2. Fall back to merged group + friends pool
        group_matches = (
            match_name(query, group_members, boost_first=True).matches
            if group_members else []
        )
        friends_matches = match_name(query, friends).matches

        combined: dict[int, Match] = {}
        for m in group_matches + friends_matches:
            existing = combined.get(m.person.id)
            if existing is None or m.confidence > existing.confidence:
                combined[m.person.id] = m

        merged = MatchResult(
            query=query,
            matches=sorted(combined.values(), key=lambda m: m.confidence, reverse=True),
        )

        if merged.is_unambiguous and merged.best.person.id not in seen_ids:
            resolved.append(merged.best.person)
            seen_ids.add(merged.best.person.id)
        elif merged.matches:
            needs_input.append(merged)
        # No matches at all → silently dropped

    return resolved, needs_input


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance (small strings only)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                prev[j] + 1,        # deletion
                curr[j - 1] + 1,    # insertion
                prev[j - 1] + (ca != cb),  # substitution
            )
        prev = curr
    return prev[-1]
