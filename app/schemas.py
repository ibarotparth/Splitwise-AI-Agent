from datetime import date
from typing import Any, Literal, Optional
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


# ── Multi-turn flow primitives ───────────────────────────────────────────────

# What kind of widget the UI should render for the next user input
AwaitingInputType = Literal[
    "group_choice",          # radio: pick group or non-group
    "participant_choice",    # multi-select checkboxes
    "split_type",            # radio: equal/exact/percent/shares
    "split_details",         # per-person numeric input
    "confirmation",          # confirm/cancel
]


class OptionItem(BaseModel):
    """An option to render in a UI widget."""
    id: str                  # stable identifier sent back as selection
    label: str               # human-readable label
    sublabel: Optional[str] = None
    selected: bool = False   # default selection state


class AwaitingInput(BaseModel):
    """Tells the UI what widget to render and what context to show."""
    type: AwaitingInputType
    prompt: str                            # user-facing text
    options: list[OptionItem] = Field(default_factory=list)
    multi_select: bool = False
    numeric_total: Optional[float] = None  # for split_details: total to validate against
    currency: Optional[str] = None         # for split_details


class PendingAction(BaseModel):
    """Persisted between turns when the agent is in the middle of a multi-step flow."""
    action: Literal["create_expense"] = "create_expense"
    step: Literal[
        "select_group",
        "select_participants",
        "select_split_type",
        "configure_split",
        "confirm",
    ]
    data: dict[str, Any] = Field(default_factory=dict)
    # Common keys in `data`:
    #   amount, description, expense_date
    #   group_id, group_name, participant_ids (list[int]), participant_names (list[str])
    #   split_type, split_details (dict[user_id -> share value])
    #   available_groups, available_members  (cached choices for the UI)


# ── API contracts ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: Optional[str] = None
    history: list[AgentMessage] = Field(default_factory=list)
    # When the user picks options in a widget, the UI sends them back here
    # instead of (or alongside) a free-text message.
    selection: Optional[list[str]] = None         # ids picked from options
    numeric_inputs: Optional[dict[str, float]] = None  # for split_details widget
    pending: Optional[PendingAction] = None       # state from previous turn


class ChatResponse(BaseModel):
    reply: str
    awaiting_input: Optional[AwaitingInput] = None
    pending: Optional[PendingAction] = None       # carried back to UI for next turn


# ── LangGraph state ───────────────────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    messages: list[dict]
    intent: Optional[str]
    response: Optional[str]
    error: Optional[str]
    # Multi-turn fields
    awaiting_input: Optional[AwaitingInput]
    pending: Optional[PendingAction]
    # Inputs from a widget-driven turn
    selection: Optional[list[str]]
    numeric_inputs: Optional[dict[str, float]]
    # (Backend remains stateless — no cross-turn fields here)
