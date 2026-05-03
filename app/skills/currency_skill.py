"""List supported Splitwise currencies."""
import logging

from app.schemas import AgentState
from app.skills.base import Skill
from app.tools.splitwise import SplitwiseClientInterface

logger = logging.getLogger(__name__)


class CurrencySkill(Skill):
    def __init__(self, client: SplitwiseClientInterface) -> None:
        self._client = client

    def can_handle(self, intent: str) -> bool:
        return intent in ("get_comments", "get_currencies")

    def execute(self, state: AgentState) -> AgentState:
        # This skill handles two simple read intents.
        try:
            intent = state.get("intent", "")
            if intent == "get_currencies":
                return {**state, "response": self._currencies(), "error": None}
            return {**state, "response": self._comments(state), "error": None}
        except Exception as exc:
            logger.exception("CurrencySkill failed")
            return {**state, "error": str(exc), "response": None}

    def _currencies(self) -> str:
        currencies = self._client.get_currencies()
        if not currencies:
            return "Could not fetch currencies."
        codes = sorted({c["code"] for c in currencies if c.get("code")})
        preview = ", ".join(codes[:25])
        more = f" … (+{len(codes) - 25} more)" if len(codes) > 25 else ""
        return f"Splitwise supports {len(codes)} currencies: {preview}{more}"

    def _comments(self, state: AgentState) -> str:
        # Pull expense ID from message via simple parsing — no LLM needed
        import re
        messages = state.get("messages") or []
        last = messages[-1].get("content", "") if messages else ""
        match = re.search(r"\d+", last)
        if not match:
            return "Please specify an expense ID, e.g. 'show comments on expense 12345'."
        expense_id = int(match.group(0))
        comments = self._client.get_comments(expense_id)
        if not comments:
            return f"No comments on expense #{expense_id}."
        lines = [f"- *{c['author'] or 'Unknown'}*: {c['content']}" for c in comments]
        return f"Comments on expense #{expense_id}:\n" + "\n".join(lines)
