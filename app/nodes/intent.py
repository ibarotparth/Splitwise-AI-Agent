from typing import Literal
from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel

from app.schemas import AgentState


Intent = Literal[
    "create_expense",
    "get_expenses",
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


_SYSTEM_PROMPT = (
    "Classify the user's message into exactly one intent:\n"
    "- create_expense: add, log, or split a new expense (optionally in a group)\n"
    "- get_expenses: list recent expenses or transactions\n"
    "- get_expense_details: view details of a specific expense by ID\n"
    "- update_expense: edit/modify an existing expense by ID\n"
    "- delete_expense: delete or remove an expense by ID\n"
    "- get_balance: what the user owes or is owed by someone\n"
    "- get_groups: list all Splitwise groups\n"
    "- get_group_details: view details/members of a specific group by name\n"
    "- get_comments: view comments on a specific expense by ID\n"
    "- get_currencies: list supported Splitwise currencies\n"
    "- unknown: anything else\n"
    "Return only the intent label."
)


class IntentClassifierNode:
    """Single-responsibility node: classify user intent via structured LLM output."""

    def __init__(self, llm: BaseChatModel) -> None:
        self._classifier = llm.with_structured_output(_IntentResult)

    def __call__(self, state: AgentState) -> AgentState:
        messages = state.get("messages", [])
        if not messages:
            return {**state, "intent": "unknown", "error": "No message provided."}

        last_message = messages[-1].get("content", "")
        result: _IntentResult = self._classifier.invoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": last_message},
            ]
        )
        return {**state, "intent": result.intent, "error": None}
