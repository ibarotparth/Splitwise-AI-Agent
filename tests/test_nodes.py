"""Tests for skills (replaces old node tests)."""
from unittest.mock import MagicMock

from app.skills.intent_classifier_skill import IntentClassifierSkill
from app.skills.error_skill import ErrorSkill
from app.skills.balance_skill import BalanceSkill
from app.skills.expense_query_skill import ExpenseQuerySkill
from app.skills.expense_create_skill import ExpenseCreateSkill
from app.schemas import AgentState


def _state(**kwargs) -> AgentState:
    base: AgentState = {
        "messages": [],
        "intent": None,
        "response": None,
        "error": None,
    }
    base.update(kwargs)
    return base


# ── IntentClassifierSkill ─────────────────────────────────────────────────────

class TestIntentClassifier:
    def test_classifies_create_expense(self):
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = MagicMock(
            intent="create_expense"
        )
        skill = IntentClassifierSkill(llm)
        state = _state(messages=[{"role": "user", "content": "Add $20 for lunch with Bob"}])
        result = skill(state)
        assert result["intent"] == "create_expense"

    def test_returns_unknown_on_empty_messages(self):
        llm = MagicMock()
        skill = IntentClassifierSkill(llm)
        result = skill(_state())
        assert result["intent"] == "unknown"

# ── ErrorSkill ────────────────────────────────────────────────────────────────

class TestErrorSkill:
    def test_shows_error_message(self):
        skill = ErrorSkill()
        result = skill(_state(error="API failed", intent="get_expenses"))
        assert "API failed" in result["response"]

    def test_help_on_unknown(self):
        skill = ErrorSkill()
        result = skill(_state(intent="unknown"))
        assert "Add" in result["response"] and "groups" in result["response"].lower()

    def test_generic_message(self):
        skill = ErrorSkill()
        result = skill(_state(intent="get_balance"))
        assert "couldn't" in result["response"].lower()


# ── BalanceSkill ──────────────────────────────────────────────────────────────

class TestBalanceSkill:
    def test_no_balances(self):
        client = MagicMock()
        client.get_balances.return_value = []
        result = BalanceSkill(client).execute(
            _state(messages=[{"role": "user", "content": "balance"}])
        )
        assert "no outstanding" in result["response"]

    def test_shows_who_owes_whom(self):
        client = MagicMock()
        client.get_balances.return_value = [
            {"friend": "Alice", "amount": "10.00", "currency": "USD"},
            {"friend": "Bob", "amount": "-5.00", "currency": "USD"},
        ]
        result = BalanceSkill(client).execute(
            _state(messages=[{"role": "user", "content": "show all balances"}])
        )
        assert "Alice owes you" in result["response"]
        assert "You owe Bob" in result["response"]

    def test_filters_by_friend_name(self):
        client = MagicMock()
        client.get_balances.return_value = [
            {"friend": "Alice Smith", "amount": "10.00", "currency": "USD"},
            {"friend": "Bob Jones", "amount": "-5.00", "currency": "USD"},
        ]
        result = BalanceSkill(client).execute(
            _state(messages=[{"role": "user", "content": "what do I owe bob"}])
        )
        assert "Bob" in result["response"]
        assert "Alice" not in result["response"]


# ── ExpenseQuerySkill ─────────────────────────────────────────────────────────

class TestExpenseQuerySkill:
    def test_list_recent(self):
        client = MagicMock()
        client.get_expenses.return_value = [
            {"id": 1, "description": "Lunch", "cost": "20", "currency": "USD",
             "date": "2024-01-01T00:00:00Z"}
        ]
        llm = MagicMock()
        result = ExpenseQuerySkill(llm, client).execute(
            _state(intent="get_expenses", messages=[{"role": "user", "content": "show"}])
        )
        assert "Lunch" in result["response"]

    def test_details_by_id(self):
        client = MagicMock()
        client.get_expense.return_value = {
            "id": 99, "description": "Pizza", "cost": "30", "currency": "USD",
            "date": "2024-01-01T00:00:00Z", "created_by": "Alice", "users": [],
        }
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = MagicMock(expense_id=99)
        result = ExpenseQuerySkill(llm, client).execute(
            _state(
                intent="get_expense_details",
                messages=[{"role": "user", "content": "show me expense 99"}],
            )
        )
        assert "Pizza" in result["response"]
        assert "#99" in result["response"]


# ── ExpenseCreateSkill — amount validation ─────────────────────────────────────

import pytest
from app.skills.expense_create_skill import _detect_bad_amount


class TestDetectBadAmount:
    """Pre-LLM regex check on the raw user message."""

    @pytest.mark.parametrize("message", [
        "add -$50 for dinner",
        "add $-50 for dinner",
        "add -50 for dinner",
        "-$50",
        "$-50",
        "-50",
    ])
    def test_negative(self, message):
        assert _detect_bad_amount(message) == "negative"

    @pytest.mark.parametrize("message", [
        "add $0 for dinner",
        "add 0 for dinner",
        "add $0.00 for dinner",
        "$0",
    ])
    def test_zero(self, message):
        assert _detect_bad_amount(message) == "zero"

    @pytest.mark.parametrize("message", [
        "add -$0 for dinner",
        "add $-0 for dinner",
        "add -0 for dinner",
        "-$0",
        "$-0",
        "-0",
    ])
    def test_negative_zero_flagged_as_negative(self, message):
        # The minus sign trips the negative check first — either rejection is fine
        assert _detect_bad_amount(message) in ("negative", "zero")

    @pytest.mark.parametrize("message", [
        "add 50 million for dinner",
        "add $5 billion",
        "5 lakhs for dinner",
    ])
    def test_huge(self, message):
        assert _detect_bad_amount(message) == "huge"

    @pytest.mark.parametrize("message", [
        "add $50 for dinner",
        "add 50 for dinner",
        "add $0.50 for coffee",          # half-dollar — not zero
        "add $5000 for trip-25",         # hyphen in a word, not before a digit
    ])
    def test_valid_passes(self, message):
        assert _detect_bad_amount(message) is None


class TestExpenseCreateSkillValidation:
    """End-to-end check that bad amounts short-circuit before any API call."""

    def _make_skill(self, amount=50.0):
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = MagicMock(
            amount=amount,
            description="dinner",
            participants=[],
            expense_date=None,
            group_name=None,
        )
        client = MagicMock()
        return ExpenseCreateSkill(llm, client), client, llm

    def test_pre_llm_negative_rejection_skips_llm_call(self):
        skill, client, llm = self._make_skill(amount=50.0)  # LLM would say 50
        result = skill.execute(_state(
            intent="create_expense",
            messages=[{"role": "user", "content": "add -$50 for dinner"}],
        ))
        assert "negative" in result["response"].lower()
        # Critical: LLM was NEVER called
        llm.with_structured_output.return_value.invoke.assert_not_called()
        client.get_groups.assert_not_called()
        client.create_expense_with_ids.assert_not_called()

    def test_pre_llm_zero_rejection(self):
        skill, client, llm = self._make_skill(amount=0.0)
        result = skill.execute(_state(
            intent="create_expense",
            messages=[{"role": "user", "content": "add $0 for dinner"}],
        ))
        assert "greater than zero" in result["response"]
        llm.with_structured_output.return_value.invoke.assert_not_called()

    def test_pre_llm_huge_rejection(self):
        skill, client, llm = self._make_skill(amount=50.0)
        result = skill.execute(_state(
            intent="create_expense",
            messages=[{"role": "user", "content": "add 50 million for dinner"}],
        ))
        assert "unreasonably large" in result["response"]
        llm.with_structured_output.return_value.invoke.assert_not_called()

    def test_post_llm_zero_rejection_when_message_is_clean(self):
        # If the message looks fine but LLM returns 0 anyway, post-check catches it
        skill, client, llm = self._make_skill(amount=0.0)
        result = skill.execute(_state(
            intent="create_expense",
            messages=[{"role": "user", "content": "add some money for dinner"}],
        ))
        assert "greater than zero" in result["response"]
        client.create_expense_with_ids.assert_not_called()
