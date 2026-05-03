"""
Multi-turn expense-creation skill.

Flow:
  extract → (select_group?) → (select_participants?) → select_split_type
  → configure_split → confirm → create

Each step returns either a finished response OR an `awaiting_input` widget
spec, so the UI can render the right control for the user's next action.
"""
import logging
import re
from datetime import date
from typing import Optional

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from app.matchers.group_matcher import find_group
from app.matchers.name_matcher import (
    Person,
    people_from_friends,
    people_from_group_members,
    resolve_participants,
)
from app.schemas import (
    AgentState,
    AwaitingInput,
    OptionItem,
    PendingAction,
)
from app.skills.base import Skill
from app.tools.splitwise import SplitwiseClientInterface

logger = logging.getLogger(__name__)


# ── LLM extraction schema ────────────────────────────────────────────────────

class _ExpenseExtraction(BaseModel):
    amount: float
    description: Optional[str] = None
    participants: list[str] = []
    expense_date: Optional[str] = None
    group_name: Optional[str] = None


_EXTRACT_PROMPT = (
    "Extract expense details from the user message.\n\n"
    "Fields:\n"
    "- amount (float): the expense amount.\n"
    "- description (string or null): the title/note. If quoted, use exact text. "
    "Do NOT include the group name. Null if not mentioned.\n"
    "- participants (list of strings): ONLY specific people's names. NEVER include "
    "phrases like 'all', 'everyone', 'all members', 'group', 'people', or any group name. "
    "If the user says 'all people of group X' or 'everyone', return [].\n"
    "- expense_date (YYYY-MM-DD or null for today).\n"
    "- group_name (string or null): the group name if explicitly mentioned. "
    "Group names may contain numbers/addresses (e.g., '548 Maple Ave').\n\n"
    "Examples:\n"
    "Input: 'add $20 for lunch with Bob in Roommates'\n"
    "Output: amount=20.0, description='lunch', participants=['Bob'], group_name='Roommates'\n\n"
    "Input: 'add $156.27 \"NIB 4/29\" in 548 Maple Ave with all people of group'\n"
    "Output: amount=156.27, description='NIB 4/29', participants=[], group_name='548 Maple Ave'\n\n"
    "Input: 'add $50 for dinner'\n"
    "Output: amount=50.0, description='dinner', participants=[], group_name=null\n"
)


_JUNK_TOKENS = {
    "all", "everyone", "everybody", "all people", "all members",
    "all the people", "the group", "group", "members", "people",
    "all people of group",
}


# ── Pre-LLM amount-sanity checks (the LLM tends to strip negatives) ──────────

# "-$50", " -50", "-.50", but not "trip-25"
_NEGATIVE_AMOUNT_RE = re.compile(r"(?:^|\s)-\s*\$?\s*\d|\$\s*-\s*\d")
# "$0", "$0.00", "add 0", "add $0" — but not "$0.5"
_ZERO_AMOUNT_RE = re.compile(
    r"\$\s*0+(?:\.0+)?(?!\.?\d)|\badd\s+\$?\s*0+(?:\.0+)?(?!\.?\d)\b",
    re.IGNORECASE,
)
# "50 million", "$5 billion", "5 lakh", etc.
_HUGE_AMOUNT_RE = re.compile(
    r"\b\d+\s*(?:million|billion|trillion|crore|lakh|lakhs)\b",
    re.IGNORECASE,
)


def _detect_bad_amount(message: str) -> Optional[str]:
    """Returns 'negative', 'zero', 'huge', or None."""
    if _NEGATIVE_AMOUNT_RE.search(message):
        return "negative"
    if _ZERO_AMOUNT_RE.search(message):
        return "zero"
    if _HUGE_AMOUNT_RE.search(message):
        return "huge"
    return None


_BAD_AMOUNT_RESPONSE = {
    "negative": (
        "⚠️ The amount must be greater than zero — you entered a **negative** value. "
        "Please rephrase, e.g. *\"add $50 for dinner with Bob\"*."
    ),
    "zero": (
        "⚠️ The amount must be greater than zero. "
        "Please rephrase with a positive amount."
    ),
    "huge": (
        "⚠️ That amount looks unreasonably large. "
        "Please use a specific number like *\"$5000\"* instead of *\"5 million\"*."
    ),
}


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _default_title(description: Optional[str], expense_date: Optional[date]) -> str:
    if description and description.strip():
        return description.strip()
    when = (expense_date or date.today()).strftime("%b %-d, %Y")
    return f"Expense — {when}"


# ── The skill ────────────────────────────────────────────────────────────────

class ExpenseCreateSkill(Skill):
    """Owns the multi-turn create-expense flow."""

    def __init__(
        self,
        extractor_llm: BaseChatModel,
        client: SplitwiseClientInterface,
    ) -> None:
        self._extractor = extractor_llm.with_structured_output(_ExpenseExtraction)
        self._client = client

    def can_handle(self, intent: str) -> bool:
        return intent == "create_expense"

    # ── Entry point ──────────────────────────────────────────────────────────

    def execute(self, state: AgentState) -> AgentState:
        try:
            # If we're mid-flow, advance based on the user's selection
            pending = state.get("pending")
            if pending and pending.action == "create_expense":
                return self._continue_flow(state, pending)
            # Otherwise this is a fresh message → start a new flow
            return self._start_flow(state)
        except Exception as exc:
            logger.exception("ExpenseCreateSkill failed")
            return {**state, "error": str(exc), "response": None}

    # ── Step 0: extract ──────────────────────────────────────────────────────

    def _start_flow(self, state: AgentState) -> AgentState:
        messages = state.get("messages") or []
        last_message = messages[-1].get("content", "") if messages else ""

        # Pre-LLM check: catch obvious bad amount patterns the LLM would silently
        # normalise away (e.g. it strips minus signs, returning -$50 as 50.0).
        bad = _detect_bad_amount(last_message)
        if bad:
            return self._reject(state, _BAD_AMOUNT_RESPONSE[bad])

        extracted = self._extractor.invoke(
            [
                {"role": "system", "content": _EXTRACT_PROMPT},
                {"role": "user", "content": last_message},
            ]
        )

        # Belt-and-suspenders: validate post-extraction too, in case a future
        # prompt change makes the LLM honour the sign.
        if extracted.amount is None or extracted.amount <= 0:
            return self._reject(state, _BAD_AMOUNT_RESPONSE["zero"])
        if extracted.amount > 1_000_000:
            return self._reject(state, _BAD_AMOUNT_RESPONSE["huge"])

        cleaned_participants = [
            p.strip()
            for p in (extracted.participants or [])
            if p and p.strip().lower() not in _JUNK_TOKENS
        ]
        title = _default_title(extracted.description, _parse_iso_date(extracted.expense_date))

        logger.info(
            "create extraction → amount=%s desc=%r participants=%s group=%r",
            extracted.amount, title, cleaned_participants, extracted.group_name,
        )

        data = {
            "amount": extracted.amount,
            "description": title,
            "expense_date": extracted.expense_date,
            "participant_names": cleaned_participants,
        }

        # Step 1: resolve / ask for group
        return self._step_group(state, data, attempted_group_name=extracted.group_name)

    # ── Step 1: select_group (only if ambiguous) ─────────────────────────────

    def _step_group(
        self,
        state: AgentState,
        data: dict,
        *,
        attempted_group_name: Optional[str] = None,
    ) -> AgentState:
        groups = self._client.get_groups()

        if attempted_group_name:
            target = find_group(groups, attempted_group_name)
            if target:
                data["group_id"] = target["id"]
                data["group_name"] = target["name"]
                return self._step_participants(state, data)
            # Group named but not found → ask which one
            note = f"I couldn't find a group called '{attempted_group_name}'. Please pick one:"
        elif not groups:
            # No groups → just non-group expense
            data["group_id"] = None
            data["group_name"] = None
            return self._step_participants(state, data)
        else:
            note = "Which group should this expense go in?"

        options = [
            OptionItem(id="__none__", label="🚫 Non-group expense", sublabel="Just split with friends")
        ]
        for g in groups:
            mc = len(g.get("members", []))
            options.append(OptionItem(id=str(g["id"]), label=g["name"], sublabel=f"{mc} members"))

        return self._await(
            state,
            data,
            step="select_group",
            awaiting=AwaitingInput(
                type="group_choice",
                prompt=note,
                options=options,
                multi_select=False,
            ),
        )

    # ── Step 2: select_participants ──────────────────────────────────────────

    def _step_participants(self, state: AgentState, data: dict) -> AgentState:
        # Build the candidate pool
        if data.get("group_id"):
            members_raw = self._client.get_group_members(data["group_id"])
            group_people = people_from_group_members(members_raw)
            friends_people = people_from_friends(self._client.get_friends())
        else:
            group_people = []
            friends_people = people_from_friends(self._client.get_friends())

        current_user = self._client.get_current_user()
        current_user_id = current_user["id"]

        names = data.get("participant_names") or []

        if names:
            resolved, ambiguous = resolve_participants(
                names,
                group_members=group_people,
                friends=friends_people,
            )
            unresolved = [r for r in ambiguous if not r.matches]

            # If ANY name was ambiguous or unresolved, ask the user
            if ambiguous:
                pool = group_people if group_people else friends_people
                # Pre-select unambiguous ones; show all as choices
                preselected = {p.id for p in resolved}
                # Add ambiguous candidates so user can clarify
                for amb in ambiguous:
                    for m in amb.matches[:3]:
                        if m.person not in pool:
                            pool.append(m.person)

                detail = []
                for amb in ambiguous:
                    if not amb.matches:
                        detail.append(f"• I couldn't find anyone named **{amb.query}**.")
                    else:
                        opts = ", ".join(m.person.full_name for m in amb.matches[:3])
                        detail.append(f"• Multiple matches for **{amb.query}**: {opts}")
                prompt = (
                    "I need help picking the right people:\n\n"
                    + "\n".join(detail)
                    + "\n\nSelect everyone who should be in this expense:"
                )

                options = [
                    OptionItem(
                        id=str(p.id),
                        label=p.full_name,
                        selected=(p.id in preselected),
                    )
                    for p in pool
                ]
                return self._await(
                    state, data,
                    step="select_participants",
                    awaiting=AwaitingInput(
                        type="participant_choice",
                        prompt=prompt,
                        options=options,
                        multi_select=True,
                    ),
                )

            # All names resolved unambiguously
            data["participant_ids"] = [p.id for p in resolved]
            return self._step_split_type(state, data, current_user_id)

        # No names provided
        if data.get("group_id"):
            # Group context → ask which members
            pool = group_people
            options = [
                OptionItem(id=str(p.id), label=p.full_name, selected=True)
                for p in pool
            ]
            prompt = f"Who should be part of this expense in **{data['group_name']}**?"
            return self._await(
                state, data,
                step="select_participants",
                awaiting=AwaitingInput(
                    type="participant_choice",
                    prompt=prompt,
                    options=options,
                    multi_select=True,
                ),
            )

        # No group, no names → must ask
        pool = friends_people
        options = [
            OptionItem(id=str(p.id), label=p.full_name)
            for p in pool[:30]
        ]
        return self._await(
            state, data,
            step="select_participants",
            awaiting=AwaitingInput(
                type="participant_choice",
                prompt="Who's part of this expense?",
                options=options,
                multi_select=True,
            ),
        )

    # ── Step 3: select_split_type ────────────────────────────────────────────

    def _step_split_type(
        self, state: AgentState, data: dict, current_user_id: int
    ) -> AgentState:
        # All participants includes the current user
        all_ids = list(dict.fromkeys([current_user_id] + data.get("participant_ids", [])))
        data["all_participant_ids"] = all_ids

        # Default to equal split — show it as a preview but let user change
        equal_share = round(data["amount"] / len(all_ids), 2)

        options = [
            OptionItem(
                id="equal", label="🟰 Split equally",
                sublabel=f"Each person owes ~${equal_share:.2f}",
                selected=True,
            ),
            OptionItem(
                id="exact", label="💵 Specify exact amounts",
                sublabel="Tell me what each person owes",
            ),
            OptionItem(
                id="percentage", label="% Percentages",
                sublabel="Split by percentage (must total 100%)",
            ),
            OptionItem(
                id="shares", label="📊 By shares",
                sublabel="e.g. 2 nights = 2 shares",
            ),
        ]

        return self._await(
            state, data,
            step="select_split_type",
            awaiting=AwaitingInput(
                type="split_type",
                prompt=f"How should ${data['amount']:.2f} be split among {len(all_ids)} people?",
                options=options,
                multi_select=False,
            ),
        )

    # ── Step 4: configure_split ──────────────────────────────────────────────

    def _step_configure_split(self, state: AgentState, data: dict) -> AgentState:
        split_type = data["split_type"]
        all_ids = data["all_participant_ids"]
        amount = data["amount"]

        # Look up display names
        names_by_id = self._lookup_names(all_ids, data.get("group_id"))

        if split_type == "equal":
            # Auto-compute shares; skip directly to confirm
            base = round(amount / len(all_ids), 2)
            shares = [base] * (len(all_ids) - 1)
            shares.append(round(amount - sum(shares), 2))
            data["split_details"] = {
                str(uid): shares[i] for i, uid in enumerate(all_ids)
            }
            return self._step_confirm(state, data, names_by_id)

        # For exact/%/shares — show numeric inputs per person
        if split_type == "exact":
            prompt = f"Enter what each person owes (must total ${amount:.2f}):"
            options = [
                OptionItem(id=str(uid), label=names_by_id.get(uid, f"User {uid}"))
                for uid in all_ids
            ]
            return self._await(
                state, data,
                step="configure_split",
                awaiting=AwaitingInput(
                    type="split_details",
                    prompt=prompt,
                    options=options,
                    numeric_total=amount,
                ),
            )

        if split_type == "percentage":
            prompt = "Enter each person's percentage (must total 100):"
            options = [
                OptionItem(id=str(uid), label=names_by_id.get(uid, f"User {uid}"))
                for uid in all_ids
            ]
            return self._await(
                state, data,
                step="configure_split",
                awaiting=AwaitingInput(
                    type="split_details",
                    prompt=prompt,
                    options=options,
                    numeric_total=100.0,
                ),
            )

        if split_type == "shares":
            prompt = "Enter each person's share count (any positive number):"
            options = [
                OptionItem(id=str(uid), label=names_by_id.get(uid, f"User {uid}"))
                for uid in all_ids
            ]
            return self._await(
                state, data,
                step="configure_split",
                awaiting=AwaitingInput(
                    type="split_details",
                    prompt=prompt,
                    options=options,
                ),
            )

        raise ValueError(f"Unknown split_type: {split_type}")

    # ── Step 5: confirm ──────────────────────────────────────────────────────

    def _step_confirm(
        self, state: AgentState, data: dict, names_by_id: dict[int, str]
    ) -> AgentState:
        amount = data["amount"]
        split_details = data["split_details"]  # {uid_str: float}

        lines = [
            f"**Title:** {data['description']}",
            f"**Amount:** ${amount:.2f}",
            f"**Group:** {data.get('group_name') or 'Non-group expense'}",
            f"**Date:** {data.get('expense_date') or 'today'}",
            "",
            "**Split:**",
        ]
        for uid_str, owed in split_details.items():
            uid = int(uid_str)
            name = names_by_id.get(uid, f"User {uid}")
            lines.append(f"  • {name}: ${owed:.2f}")

        prompt = "Looks good? Confirm to add this expense to Splitwise."
        return self._await(
            state, data,
            step="confirm",
            awaiting=AwaitingInput(
                type="confirmation",
                prompt="\n".join(lines) + "\n\n" + prompt,
                options=[
                    OptionItem(id="yes", label="✅ Confirm"),
                    OptionItem(id="no", label="❌ Cancel"),
                ],
            ),
        )

    # ── Final: create ────────────────────────────────────────────────────────

    def _create_now(self, state: AgentState, data: dict) -> AgentState:
        amount = data["amount"]
        owed = {int(uid): float(owed) for uid, owed in data["split_details"].items()}

        current_user = self._client.get_current_user()
        result = self._client.create_expense_with_ids(
            amount=amount,
            description=data["description"],
            payer_id=current_user["id"],
            owed_shares=owed,
            expense_date=_parse_iso_date(data.get("expense_date")),
            group_id=data.get("group_id"),
        )

        names_by_id = self._lookup_names(list(owed.keys()), data.get("group_id"))
        split_lines = "\n".join(
            f"  • {names_by_id.get(uid, f'User {uid}')}: ${share:.2f}"
            for uid, share in owed.items()
        )

        response = (
            f"✅ Added **{result['description']}** for ${amount:.2f} "
            f"({data.get('group_name') or 'non-group'}, id `{result['id']}`)\n\n"
            f"{split_lines}"
        )

        return {
            **state,
            "response": response,
            "pending": None,
            "awaiting_input": None,
            "error": None,
        }

    # ── Continuation logic ───────────────────────────────────────────────────

    def _continue_flow(self, state: AgentState, pending: PendingAction) -> AgentState:
        data = dict(pending.data)
        selection = state.get("selection") or []
        numeric = state.get("numeric_inputs") or {}

        if pending.step == "select_group":
            choice = selection[0] if selection else "__none__"
            if choice == "__none__":
                data["group_id"] = None
                data["group_name"] = None
            else:
                data["group_id"] = int(choice)
                # Look up name from cached groups
                groups = self._client.get_groups()
                match = next((g for g in groups if g["id"] == int(choice)), None)
                data["group_name"] = match["name"] if match else None
            return self._step_participants(state, data)

        if pending.step == "select_participants":
            data["participant_ids"] = [int(s) for s in selection if s]
            current_user = self._client.get_current_user()
            return self._step_split_type(state, data, current_user["id"])

        if pending.step == "select_split_type":
            data["split_type"] = selection[0] if selection else "equal"
            return self._step_configure_split(state, data)

        if pending.step == "configure_split":
            split_type = data["split_type"]
            all_ids = data["all_participant_ids"]
            amount = data["amount"]

            inputs = {uid: float(numeric.get(str(uid), 0)) for uid in all_ids}

            if split_type == "exact":
                shares = inputs
            elif split_type == "percentage":
                total_pct = sum(inputs.values())
                if abs(total_pct - 100) > 0.01:
                    return self._error(
                        state, f"Percentages must total 100 (got {total_pct:.2f})."
                    )
                shares = {uid: round(amount * pct / 100, 2) for uid, pct in inputs.items()}
                # Absorb rounding remainder into last entry
                diff = round(amount - sum(shares.values()), 2)
                if diff:
                    last = list(shares.keys())[-1]
                    shares[last] = round(shares[last] + diff, 2)
            elif split_type == "shares":
                total_sh = sum(inputs.values())
                if total_sh <= 0:
                    return self._error(state, "Shares must be positive.")
                shares = {uid: round(amount * sh / total_sh, 2) for uid, sh in inputs.items()}
                diff = round(amount - sum(shares.values()), 2)
                if diff:
                    last = list(shares.keys())[-1]
                    shares[last] = round(shares[last] + diff, 2)
            else:
                return self._error(state, f"Unknown split_type: {split_type}")

            data["split_details"] = {str(uid): float(v) for uid, v in shares.items()}
            names = self._lookup_names(all_ids, data.get("group_id"))
            return self._step_confirm(state, data, names)

        if pending.step == "confirm":
            choice = selection[0] if selection else "no"
            if choice == "yes":
                return self._create_now(state, data)
            return {
                **state,
                "response": "❌ Cancelled — nothing was added to Splitwise.",
                "pending": None,
                "awaiting_input": None,
                "error": None,
            }

        return self._error(state, f"Unknown step: {pending.step}")

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _await(
        self,
        state: AgentState,
        data: dict,
        *,
        step: str,
        awaiting: AwaitingInput,
    ) -> AgentState:
        return {
            **state,
            "response": awaiting.prompt,
            "awaiting_input": awaiting,
            "pending": PendingAction(action="create_expense", step=step, data=data),
            "error": None,
        }

    def _error(self, state: AgentState, msg: str) -> AgentState:
        return {**state, "response": f"⚠️ {msg}", "error": msg, "pending": None}

    def _reject(self, state: AgentState, response: str) -> AgentState:
        """Validation failure — clear pending, show user a clean message."""
        return {
            **state,
            "response": response,
            "error": None,
            "pending": None,
            "awaiting_input": None,
        }

    def _lookup_names(
        self, user_ids: list[int], group_id: Optional[int]
    ) -> dict[int, str]:
        names: dict[int, str] = {}
        # Add current user
        cu = self._client.get_current_user()
        names[cu["id"]] = f"{cu['first_name']} {cu['last_name']}".strip() + " (you)"

        # Add group members if applicable
        if group_id:
            for m in self._client.get_group_members(group_id):
                if m["id"] not in names:
                    names[m["id"]] = f"{m['first_name']} {m['last_name']}".strip()

        # Fall back to friends
        missing = [uid for uid in user_ids if uid not in names]
        if missing:
            for f in self._client.get_friends():
                if f["id"] in missing and f["id"] not in names:
                    names[f["id"]] = f"{f.get('first_name', '')} {f.get('last_name', '')}".strip()

        return names
