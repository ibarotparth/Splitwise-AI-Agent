"""
Skill router — picks the correct skill for the current intent and executes it.
"""
import logging

from app.schemas import AgentState
from app.skills.base import Skill

logger = logging.getLogger(__name__)


class SkillRouter:
    def __init__(self, skills: list[Skill]) -> None:
        self._skills = skills

    def __call__(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "unknown")
        for skill in self._skills:
            if skill.can_handle(intent):
                logger.info("Dispatching intent=%r → %s", intent, skill.__class__.__name__)
                return skill.execute(state)
        # No matching skill → set error and fall through to error node
        logger.warning("No skill for intent=%r", intent)
        return {**state, "error": f"No skill registered for intent '{intent}'"}
