"""List groups + show group details."""
import logging

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.matchers.group_matcher import find_group
from app.schemas import AgentState
from app.skills.base import Skill
from app.tools.splitwise import SplitwiseClientInterface

logger = logging.getLogger(__name__)


class _GroupNameExtraction(BaseModel):
    group_name: str


_PROMPT = "Extract the group name the user is referring to."


class GroupSkill(Skill):
    def __init__(self, classifier_llm: BaseChatModel, client: SplitwiseClientInterface) -> None:
        self._extract_name = classifier_llm.with_structured_output(_GroupNameExtraction)
        self._client = client

    def can_handle(self, intent: str) -> bool:
        return intent in ("get_groups", "get_group_details")

    def execute(self, state: AgentState) -> AgentState:
        try:
            intent = state.get("intent", "")
            messages = state.get("messages") or []
            last = messages[-1].get("content", "") if messages else ""
            if intent == "get_groups":
                response = self._list()
            else:
                response = self._details(last)
        except Exception as exc:
            logger.exception("GroupSkill failed")
            return {**state, "error": str(exc), "response": None}
        return {**state, "response": response, "error": None}

    def _list(self) -> str:
        groups = self._client.get_groups()
        if not groups:
            return "You have no Splitwise groups."
        lines = [
            f"- `#{g['id']}` **{g['name']}** ({len(g['members'])} members: {', '.join(g['members'])})"
            for g in groups
        ]
        return "Your groups:\n" + "\n".join(lines)

    def _details(self, message: str) -> str:
        name = self._extract_name.invoke(
            [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": message},
            ]
        ).group_name
        groups = self._client.get_groups()
        match = find_group(groups, name)
        if not match:
            return f"Group '{name}' not found."
        details = self._client.get_group(match["id"])
        lines = [
            f"**{details['name']}** (id: {details['id']})",
            f"- Members ({len(details['members'])}): {', '.join(details['members'])}",
            f"- Simplify debts: {'on' if details['simplify_by_default'] else 'off'}",
        ]
        if details.get("simplified_debts"):
            lines.append(f"- Outstanding debts: {len(details['simplified_debts'])}")
        return "\n".join(lines)
