"""Intent classification — uses the cheap classifier model."""
from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.schemas import AgentState

Intent = Literal[
    "create_expense",
    "get_expenses",
    "get_group_expenses",
    "get_expense_details",
    "update_expense",
    "delete_expense",
    "get_balance",
    "get_groups",
    "get_group_details",
    "get_comments",
    "get_currencies",
    "unknown",
]


class _IntentResult(BaseModel):
    intent: Intent


_PROMPT = (
    "Classify the user's message into exactly one intent:\n"
    "- create_expense: add, log, or split a new expense\n"
    "- get_expenses: list recent expenses ACROSS ALL groups (no group filter)\n"
    "- get_group_expenses: list expenses FILTERED to a specific group. Use this "
    "when the user asks for expenses/transactions/spending OF or IN a named "
    "group (e.g., 'show expenses of Roommates', 'recent expenses in 548 Maple Ave').\n"
    "- get_expense_details: view ONE specific expense. ONLY when the user "
    "explicitly says 'expense', 'transaction', '#<number>', or 'id <number>'. "
    "A bare number is NOT enough — it's likely part of a group name.\n"
    "- update_expense: edit an existing expense by ID\n"
    "- delete_expense: delete a specific expense by ID\n"
    "- get_balance: what user owes / is owed\n"
    "- get_groups: list all groups\n"
    "- get_group_details: details/info/members of a specific group. Use this "
    "when the user asks 'show details of [group]', 'who is in [group]', "
    "'show members of [group]'. NOT for listing expenses of a group.\n"
    "- get_comments: comments on an expense\n"
    "- get_currencies: list supported currencies\n"
    "- unknown: anything else\n\n"
    "Examples:\n"
    "- 'show details of expense 12345' → get_expense_details\n"
    "- 'show details of #12345' → get_expense_details\n"
    "- 'show details of 548 Maple Ave' → get_group_details (members/info)\n"
    "- 'show details of Roommates' → get_group_details\n"
    "- 'show recent expenses' → get_expenses (across all groups)\n"
    "- 'show recent expense of 548 Maple Ave' → get_group_expenses (filtered)\n"
    "- 'expenses in Roommates' → get_group_expenses\n"
    "- 'spending of Trip 2024' → get_group_expenses\n\n"
    "Return only the intent label."
)


class IntentClassifierSkill:
    """Not a full Skill (it doesn't 'handle' an intent — it produces one)."""

    def __init__(self, classifier_llm: BaseChatModel) -> None:
        self._classifier = classifier_llm.with_structured_output(_IntentResult)

    def __call__(self, state: AgentState) -> AgentState:
        # Skip if we're mid-flow → preserve the in-progress intent
        if state.get("pending"):
            return {**state, "intent": state.get("pending").action, "error": None}

        messages = state.get("messages") or []
        if not messages:
            return {**state, "intent": "unknown", "error": "No message provided."}
        last = messages[-1].get("content", "")

        result = self._classifier.invoke(
            [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": last},
            ]
        )
        return {**state, "intent": result.intent, "error": None}
