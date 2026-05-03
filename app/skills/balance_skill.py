"""Read balances; filter by friend if mentioned."""
import logging

from app.schemas import AgentState
from app.skills.base import Skill
from app.tools.splitwise import SplitwiseClientInterface

logger = logging.getLogger(__name__)


class BalanceSkill(Skill):
    def __init__(self, client: SplitwiseClientInterface) -> None:
        self._client = client

    def can_handle(self, intent: str) -> bool:
        return intent == "get_balance"

    def execute(self, state: AgentState) -> AgentState:
        try:
            messages = state.get("messages") or []
            last = messages[-1].get("content", "") if messages else ""
            balances = self._client.get_balances()
            if not balances:
                return {**state, "response": "You have no outstanding balances.", "error": None}

            ml = last.lower()
            filtered = [
                b for b in balances
                if b["friend"].lower().split()[0] in ml or b["friend"].lower() in ml
            ]
            target = filtered or balances

            lines = []
            for b in target:
                amount = float(b["amount"])
                if amount > 0:
                    lines.append(f"- {b['friend']} owes you {b['currency']} {b['amount']}")
                else:
                    lines.append(f"- You owe {b['friend']} {b['currency']} {abs(amount):.2f}")

            return {**state, "response": "Balances:\n" + "\n".join(lines), "error": None}
        except Exception as exc:
            logger.exception("BalanceSkill failed")
            return {**state, "error": str(exc), "response": None}
