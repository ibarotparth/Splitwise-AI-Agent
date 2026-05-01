from unittest.mock import MagicMock

from app.nodes.intent import IntentClassifierNode
from app.nodes.error import ErrorHandlerNode
from app.nodes.expense import ExpenseExecutorNode
from app.schemas import AgentState


def _state(**kwargs) -> AgentState:
    base: AgentState = {
        "messages": [],
        "intent": None,
        "expense_data": None,
        "response": None,
        "error": None,
    }
    base.update(kwargs)
    return base


def _make_executor(client) -> ExpenseExecutorNode:
    """LLM mock that returns sensible defaults for every structured-output call."""
    llm = MagicMock()

    def with_structured_output(model_cls):
        runnable = MagicMock()
        # Map model class name → default extraction object
        defaults = {
            "_ExpenseExtraction": MagicMock(
                amount=20.0,
                description="Lunch",
                participants=["Alice"],
                expense_date=None,
                group_name=None,
                split_with_all_group_members=False,
            ),
            "_ExpenseIdExtraction": MagicMock(expense_id=99),
            "_GroupNameExtraction": MagicMock(group_name="Roommates"),
            "_UpdateExpenseExtraction": MagicMock(
                expense_id=99,
                amount=40.0,
                description=None,
                expense_date=None,
            ),
        }
        runnable.invoke.return_value = defaults.get(model_cls.__name__, MagicMock())
        return runnable

    llm.with_structured_output.side_effect = with_structured_output
    return ExpenseExecutorNode(llm, client)


# ── IntentClassifierNode ──────────────────────────────────────────────────────

class TestIntentClassifierNode:
    def test_classifies_create_expense(self):
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = MagicMock(
            intent="create_expense"
        )
        node = IntentClassifierNode(llm)
        state = _state(messages=[{"role": "user", "content": "Add $20 for lunch with Bob"}])
        result = node(state)
        assert result["intent"] == "create_expense"
        assert result["error"] is None

    def test_returns_unknown_on_empty_messages(self):
        llm = MagicMock()
        node = IntentClassifierNode(llm)
        result = node(_state())
        assert result["intent"] == "unknown"
        assert result["error"] is not None


# ── ErrorHandlerNode ──────────────────────────────────────────────────────────

class TestErrorHandlerNode:
    def test_shows_error_message_when_error_present(self):
        node = ErrorHandlerNode()
        result = node(_state(error="API failed", intent="get_expenses"))
        assert "API failed" in result["response"]

    def test_shows_help_on_unknown_intent(self):
        node = ErrorHandlerNode()
        result = node(_state(intent="unknown"))
        assert "Add" in result["response"]
        assert "groups" in result["response"].lower()
        assert "Delete" in result["response"]

    def test_generic_message_on_known_intent_no_error(self):
        node = ErrorHandlerNode()
        result = node(_state(intent="get_balance"))
        assert "couldn't complete" in result["response"]


# ── ExpenseExecutorNode ───────────────────────────────────────────────────────

class TestExpenseExecutorNode:
    def test_get_expenses_returns_formatted_list(self):
        client = MagicMock()
        client.get_expenses.return_value = [
            {
                "id": 1,
                "description": "Pizza",
                "cost": "30.00",
                "currency": "USD",
                "date": "2024-01-01T00:00:00Z",
            }
        ]
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "show expenses"}],
                intent="get_expenses",
            )
        )
        assert "Pizza" in result["response"]

    def test_get_expenses_empty(self):
        client = MagicMock()
        client.get_expenses.return_value = []
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "show expenses"}],
                intent="get_expenses",
            )
        )
        assert "no recent expenses" in result["response"]

    def test_create_expense_calls_client(self):
        client = MagicMock()
        client.create_expense.return_value = {
            "id": 1,
            "description": "Lunch",
            "cost": "20.00",
            "currency": "USD",
            "date": "2024-01-01",
        }
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "Add $20 for lunch with Alice"}],
                intent="create_expense",
            )
        )
        client.create_expense.assert_called_once()
        assert "Lunch" in result["response"]

    def test_get_expense_details(self):
        client = MagicMock()
        client.get_expense.return_value = {
            "id": 99,
            "description": "Pizza",
            "cost": "30.00",
            "currency": "USD",
            "date": "2024-01-01T00:00:00Z",
            "created_by": "Alice",
            "users": [{"name": "Alice", "paid_share": "30", "owed_share": "15"}],
        }
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "show me expense 99"}],
                intent="get_expense_details",
            )
        )
        client.get_expense.assert_called_once_with(99)
        assert "#99" in result["response"]

    def test_update_expense(self):
        client = MagicMock()
        client.update_expense.return_value = {
            "id": 99,
            "description": "Lunch",
            "cost": "40.00",
            "currency": "USD",
        }
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "update expense 99 to $40"}],
                intent="update_expense",
            )
        )
        client.update_expense.assert_called_once()
        assert "Updated" in result["response"]

    def test_delete_expense(self):
        client = MagicMock()
        client.delete_expense.return_value = True
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "delete expense 99"}],
                intent="delete_expense",
            )
        )
        client.delete_expense.assert_called_once_with(99)
        assert "Deleted" in result["response"]

    def test_list_groups(self):
        client = MagicMock()
        client.get_groups.return_value = [
            {"id": 1, "name": "Roommates", "members": ["Alice", "Bob"]}
        ]
        node = _make_executor(client)
        result = node(_state(messages=[{"role": "user", "content": "groups"}], intent="get_groups"))
        assert "Roommates" in result["response"]

    def test_group_details_found(self):
        client = MagicMock()
        client.get_groups.return_value = [
            {"id": 1, "name": "Roommates", "members": ["Alice", "Bob"]}
        ]
        client.get_group.return_value = {
            "id": 1,
            "name": "Roommates",
            "members": ["Alice", "Bob"],
            "simplify_by_default": True,
            "simplified_debts": [],
        }
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "details of Roommates"}],
                intent="get_group_details",
            )
        )
        assert "Roommates" in result["response"]
        client.get_group.assert_called_once_with(1)

    def test_group_details_not_found(self):
        client = MagicMock()
        client.get_groups.return_value = [
            {"id": 1, "name": "OtherGroup", "members": []}
        ]
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "details of Roommates"}],
                intent="get_group_details",
            )
        )
        assert "not found" in result["response"]

    def test_get_comments(self):
        client = MagicMock()
        client.get_comments.return_value = [
            {"id": 1, "content": "Thanks", "created_at": "now", "author": "Alice"}
        ]
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "comments on 99"}],
                intent="get_comments",
            )
        )
        client.get_comments.assert_called_once_with(99)
        assert "Thanks" in result["response"]

    def test_get_currencies(self):
        client = MagicMock()
        client.get_currencies.return_value = [
            {"code": "USD", "unit": "$"},
            {"code": "EUR", "unit": "€"},
        ]
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "what currencies"}],
                intent="get_currencies",
            )
        )
        assert "USD" in result["response"] and "EUR" in result["response"]

    def test_expense_node_captures_exception(self):
        client = MagicMock()
        client.get_expenses.side_effect = RuntimeError("network error")
        node = _make_executor(client)
        result = node(
            _state(
                messages=[{"role": "user", "content": "show expenses"}],
                intent="get_expenses",
            )
        )
        assert "network error" in result["error"]
        assert result["response"] is None
