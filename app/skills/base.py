from abc import ABC, abstractmethod

from app.schemas import AgentState


class Skill(ABC):
    """
    Base contract for a single agent capability.
    A skill takes the conversation state and returns updated state.
    """

    @abstractmethod
    def can_handle(self, intent: str) -> bool:
        """Return True if this skill should run for the given intent."""

    @abstractmethod
    def execute(self, state: AgentState) -> AgentState:
        """Mutate state to include a response (or set awaiting_input for multi-turn)."""
