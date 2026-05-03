"""Tests for the name and group matchers."""
from app.matchers.group_matcher import find_group
from app.matchers.name_matcher import (
    Person,
    match_name,
    resolve_participants,
)


# ── group_matcher ─────────────────────────────────────────────────────────────

class TestFindGroup:
    def test_exact_match(self):
        groups = [{"id": 1, "name": "Roommates"}]
        assert find_group(groups, "Roommates")["id"] == 1

    def test_case_insensitive(self):
        groups = [{"id": 1, "name": "Roommates"}]
        assert find_group(groups, "roommates")["id"] == 1

    def test_substring(self):
        groups = [{"id": 1, "name": "548 Maple Avenue"}]
        assert find_group(groups, "Maple")["id"] == 1

    def test_punctuation_normalization(self):
        groups = [{"id": 1, "name": "548 Maple Ave."}]
        assert find_group(groups, "548 maple ave")["id"] == 1

    def test_no_match(self):
        groups = [{"id": 1, "name": "Roommates"}]
        assert find_group(groups, "Trip") is None


# ── name_matcher ──────────────────────────────────────────────────────────────

class TestMatchName:
    def test_exact_full_name_highest(self):
        people = [Person(1, "Alice", "Smith"), Person(2, "Alice", "Jones")]
        result = match_name("Alice Smith", people)
        assert result.best.person.id == 1
        assert result.best.confidence >= 0.95

    def test_first_name_only(self):
        people = [Person(1, "Alice", "Smith")]
        result = match_name("Alice", people)
        assert result.best.person.id == 1

    def test_ambiguous_first_name(self):
        people = [Person(1, "Alice", "Smith"), Person(2, "Alice", "Jones")]
        result = match_name("Alice", people)
        assert result.needs_disambiguation

    def test_no_match_for_unknown_name(self):
        people = [Person(1, "Alice", "Smith")]
        result = match_name("Zachary", people)
        assert result.matches == []


class TestResolveParticipants:
    def test_unambiguous_resolved(self):
        group_members = [Person(1, "Alice", "Smith"), Person(2, "Bob", "Jones")]
        friends = []
        resolved, ambiguous = resolve_participants(
            ["Alice", "Bob"], group_members=group_members, friends=friends
        )
        assert {p.id for p in resolved} == {1, 2}
        assert ambiguous == []

    def test_ambiguous_returned_for_user_input(self):
        group_members = [Person(1, "Alice", "Smith"), Person(2, "Alice", "Jones")]
        resolved, ambiguous = resolve_participants(
            ["Alice"], group_members=group_members, friends=[]
        )
        assert resolved == []
        assert len(ambiguous) == 1
        assert len(ambiguous[0].matches) == 2

    def test_group_members_preferred_over_friends(self):
        # Same name in both — group member should win due to boost
        group = [Person(10, "Alice", "Smith")]
        friends = [Person(20, "Alice", "Smith")]
        resolved, _ = resolve_participants(
            ["Alice Smith"], group_members=group, friends=friends
        )
        assert resolved[0].id == 10

    def test_unknown_name_silently_dropped(self):
        resolved, ambiguous = resolve_participants(
            ["Zachary"], group_members=[], friends=[]
        )
        assert resolved == []
        assert ambiguous == []
