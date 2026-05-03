"""Update / delete an existing expense."""
import logging
from datetime import date
from typing import Optional

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.schemas import AgentState
from app.skills.base import Skill
from app.tools.splitwise import SplitwiseClientInterface

logger = logging.getLogger(__name__)


class _UpdateExtraction(BaseModel):
    expense_id: int
    amount: Optional[float] = None
    description: Optional[str] = None
    expense_date: Optional[str] = None


class _DeleteExtraction(BaseModel):
    expense_id: int


_UPDATE_PROMPT = (
    "Extract the expense_id (integer) and any fields to update: "
    "amount (float or null), description (string or null), "
    "expense_date (YYYY-MM-DD or null)."
)

_DELETE_PROMPT = "Extract the expense_id (integer) the user wants to delete."


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class ExpenseModifySkill(Skill):
    def __init__(self, extractor_llm: BaseChatModel, client: SplitwiseClientInterface) -> None:
        self._extract_update = extractor_llm.with_structured_output(_UpdateExtraction)
        self._extract_delete = extractor_llm.with_structured_output(_DeleteExtraction)
        self._client = client

    def can_handle(self, intent: str) -> bool:
        return intent in ("update_expense", "delete_expense")

    def execute(self, state: AgentState) -> AgentState:
        try:
            intent = state.get("intent", "")
            messages = state.get("messages") or []
            last = messages[-1].get("content", "") if messages else ""
            if intent == "update_expense":
                response = self._update(last)
            else:
                response = self._delete(last)
        except Exception as exc:
            logger.exception("ExpenseModifySkill failed")
            return {**state, "error": str(exc), "response": None}
        return {**state, "response": response, "error": None}

    def _update(self, message: str) -> str:
        e = self._extract_update.invoke(
            [
                {"role": "system", "content": _UPDATE_PROMPT},
                {"role": "user", "content": message},
            ]
        )
        result = self._client.update_expense(
            expense_id=e.expense_id,
            amount=e.amount,
            description=e.description,
            expense_date=_parse_iso_date(e.expense_date),
        )
        return (
            f"✏️ Updated expense **#{result['id']}** — {result['description']} "
            f"({result['currency']} {result['cost']})."
        )

    def _delete(self, message: str) -> str:
        e = self._extract_delete.invoke(
            [
                {"role": "system", "content": _DELETE_PROMPT},
                {"role": "user", "content": message},
            ]
        )
        ok = self._client.delete_expense(e.expense_id)
        return (
            f"🗑️ Deleted expense **#{e.expense_id}**."
            if ok
            else f"Could not delete expense #{e.expense_id}."
        )
