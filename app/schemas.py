from datetime import date
from typing import Literal, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


# ── Domain models ────────────────────────────────────────────────────────────

class Expense(BaseModel):
    amount: float
    description: str
    participants: list[str]
    date: Optional[date] = None


class BalanceEntry(BaseModel):
    friend: str
    amount: str
    currency: str


class AgentMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


# ── API contracts ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[AgentMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


# ── LangGraph state ───────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: list[dict]
    intent: Optional[str]
    expense_data: Optional[dict]
    response: Optional[str]
    error: Optional[str]
