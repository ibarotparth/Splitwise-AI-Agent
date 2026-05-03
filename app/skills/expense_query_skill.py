"""Read-only expense queries: list recent (all/group), view single."""
import logging
from typing import Optional

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.matchers.group_matcher import find_group
from app.schemas import AgentState
from app.skills.base import Skill
from app.tools.splitwise import SplitwiseClientInterface

logger = logging.getLogger(__name__)


class _ExpenseIdExtraction(BaseModel):
    expense_id: int


class _GroupNameExtraction(BaseModel):
    group_name: str


_ID_PROMPT = (
    "Extract the expense ID (integer) from the user message. "
    "Look for patterns like 'expense 123', '#123', 'id 123'."
)

_GROUP_NAME_PROMPT = "Extract the group name from the user message."


class ExpenseQuerySkill(Skill):
    def __init__(
        self, classifier_llm: BaseChatModel, client: SplitwiseClientInterface
    ) -> None:
        self._extract_id = classifier_llm.with_structured_output(_ExpenseIdExtraction)
        self._extract_group = classifier_llm.with_structured_output(_GroupNameExtraction)
        self._client = client

    def can_handle(self, intent: str) -> bool:
        return intent in (
            "get_expenses",
            "get_expense_details",
            "get_group_expenses",
        )

    def execute(self, state: AgentState) -> AgentState:
        try:
            intent = state.get("intent", "")
            messages = state.get("messages") or []
            last_message = messages[-1].get("content", "") if messages else ""
            if intent == "get_expenses":
                response = self._list_all()
            elif intent == "get_group_expenses":
                response = self._list_for_group(last_message)
            else:
                response = self._details(last_message)
        except Exception as exc:
            logger.exception("ExpenseQuerySkill failed")
            return {**state, "error": str(exc), "response": None}
        return {**state, "response": response, "error": None}

    def _list_all(self) -> str:
        expenses = self._client.get_expenses(limit=10)
        if not expenses:
            return "You have no recent expenses."
        return self._format_list(expenses, header="Your recent expenses:")

    def _list_for_group(self, message: str) -> str:
        name = self._extract_group.invoke(
            [
                {"role": "system", "content": _GROUP_NAME_PROMPT},
                {"role": "user", "content": message},
            ]
        ).group_name

        groups = self._client.get_groups()
        match = find_group(groups, name)
        if not match:
            available = "\n".join(f"- {g['name']}" for g in groups) or "(none)"
            return (
                f"⚠️ I couldn't find a group called **{name}**.\n\n"
                f"Your groups:\n{available}"
            )

        expenses = self._client.get_expenses(limit=10, group_id=match["id"])
        if not expenses:
            return f"No recent expenses in **{match['name']}**."

        return self._format_list(
            expenses,
            header=f"Recent expenses in **{match['name']}**:",
        )

    def _details(self, message: str) -> str:
        expense_id = self._extract_id.invoke(
            [
                {"role": "system", "content": _ID_PROMPT},
                {"role": "user", "content": message},
            ]
        ).expense_id
        e = self._client.get_expense(expense_id)
        if not e.get("id"):
            return f"Expense #{expense_id} not found."
        lines = [
            f"**Expense #{e['id']}** — {e['description']}",
            f"- Amount: {e['currency']} {e['cost']}",
            f"- Date: {(e['date'] or '')[:10] or 'n/a'}",
            f"- Created by: {e['created_by'] or 'n/a'}",
        ]
        if e["users"]:
            lines.append("- Split:")
            for u in e["users"]:
                lines.append(
                    f"  • {u['name']} — paid {u['paid_share']}, owes {u['owed_share']}"
                )
        return "\n".join(lines)

    @staticmethod
    def _format_list(expenses: list[dict], *, header: str) -> str:
        lines = [
            f"- `#{e['id']}` {e['description']}: {e['currency']} {e['cost']} "
            f"({(e['date'] or '')[:10]})"
            for e in expenses
        ]
        return header + "\n" + "\n".join(lines)
