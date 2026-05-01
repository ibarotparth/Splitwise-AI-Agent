import logging
from datetime import date
from typing import Optional
from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel

from app.schemas import AgentState
from app.tools.splitwise import SplitwiseClientInterface

logger = logging.getLogger(__name__)

# Phrases the LLM sometimes mistakenly returns as "participant names"
_JUNK_PARTICIPANT_TOKENS = {
    "all", "everyone", "everybody", "all people", "all members",
    "all the people", "all of group", "the group", "group",
    "members", "people", "all people of group",
}


# ── Structured-extraction schemas ────────────────────────────────────────────

class _ExpenseExtraction(BaseModel):
    amount: float
    description: str
    participants: list[str]
    expense_date: Optional[str] = None
    group_name: Optional[str] = None
    split_with_all_group_members: bool = False


class _ExpenseIdExtraction(BaseModel):
    expense_id: int


class _GroupNameExtraction(BaseModel):
    group_name: str


class _UpdateExpenseExtraction(BaseModel):
    expense_id: int
    amount: Optional[float] = None
    description: Optional[str] = None
    expense_date: Optional[str] = None


# ── Prompts ──────────────────────────────────────────────────────────────────

_CREATE_PROMPT = (
    "Extract expense details from the user message.\n\n"
    "Fields:\n"
    "- amount (float): the expense amount.\n"
    "- description (string): the title/note. If the user gives a quoted title, "
    "use the EXACT text inside the quotes. Do NOT include the group name in "
    "the description.\n"
    "- participants (list of strings): ONLY specific people's names. "
    "DO NOT include phrases like 'all', 'all people', 'everyone', 'all members', "
    "'group', 'people', or any group name. If the user says 'all people of group X' "
    "or 'everyone', return an empty list [].\n"
    "- expense_date (YYYY-MM-DD or null for today).\n"
    "- group_name (string or null): the group name if mentioned with phrases like "
    "'in [GROUP]', 'in the [GROUP] group', 'to [GROUP]'. Group names may include "
    "numbers and addresses (e.g. '548 Maple Ave', 'Apt 4B').\n"
    "- split_with_all_group_members (bool): true ONLY if the user explicitly says "
    "'all people of group', 'everyone in group', 'all members', 'with all of them', "
    "etc. Otherwise false.\n\n"
    "Examples:\n"
    "Input: 'add $20 for lunch with Bob in Roommates'\n"
    "Output: amount=20.0, description='lunch', participants=['Bob'], "
    "group_name='Roommates', split_with_all_group_members=false\n\n"
    "Input: 'add $156.27 as title \"NIB 4/29 - Added by AI Agent\" in 548 Maple Ave "
    "with all people of group'\n"
    "Output: amount=156.27, description='NIB 4/29 - Added by AI Agent', "
    "participants=[], group_name='548 Maple Ave', split_with_all_group_members=true\n\n"
    "Input: 'add $30 for pizza with Alice and Bob'\n"
    "Output: amount=30.0, description='pizza', participants=['Alice', 'Bob'], "
    "group_name=null, split_with_all_group_members=false\n"
)

_EXPENSE_ID_PROMPT = (
    "Extract the expense ID (integer) the user is referring to. "
    "Look for numbers like 'expense 123' or '#123' or 'id 123'."
)

_GROUP_NAME_PROMPT = "Extract the group name the user is referring to."

_UPDATE_PROMPT = (
    "Extract the expense ID being updated and the new values. "
    "Return: expense_id (integer), amount (float or null), "
    "description (string or null), expense_date (YYYY-MM-DD or null)."
)


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ── Node ─────────────────────────────────────────────────────────────────────

class ExpenseExecutorNode:
    """Single-responsibility node: dispatch Splitwise operations based on intent."""

    def __init__(self, llm: BaseChatModel, client: SplitwiseClientInterface) -> None:
        self._client = client
        self._extract_expense = llm.with_structured_output(_ExpenseExtraction)
        self._extract_expense_id = llm.with_structured_output(_ExpenseIdExtraction)
        self._extract_group_name = llm.with_structured_output(_GroupNameExtraction)
        self._extract_update = llm.with_structured_output(_UpdateExpenseExtraction)

    def __call__(self, state: AgentState) -> AgentState:
        messages = state.get("messages", [])
        last_message = messages[-1].get("content", "") if messages else ""
        intent = state.get("intent", "unknown")

        try:
            response = self._dispatch(intent, last_message)
        except Exception as exc:
            return {**state, "error": str(exc), "response": None}

        return {**state, "response": response, "error": None}

    def _dispatch(self, intent: str, message: str) -> str:
        handlers = {
            "create_expense": lambda: self._create(message),
            "get_expenses": lambda: self._list_expenses(),
            "get_expense_details": lambda: self._expense_details(message),
            "update_expense": lambda: self._update(message),
            "delete_expense": lambda: self._delete(message),
            "get_balance": lambda: self._balance(message),
            "get_groups": lambda: self._list_groups(),
            "get_group_details": lambda: self._group_details(message),
            "get_comments": lambda: self._comments(message),
            "get_currencies": lambda: self._currencies(),
        }
        handler = handlers.get(intent)
        if handler is None:
            return "Unrecognised intent."
        return handler()

    # ── Expense handlers ─────────────────────────────────────────────────────

    def _create(self, message: str) -> str:
        extracted = self._extract_expense.invoke(
            [
                {"role": "system", "content": _CREATE_PROMPT},
                {"role": "user", "content": message},
            ]
        )

        # Filter out non-name junk the LLM sometimes returns
        cleaned_participants = [
            p.strip()
            for p in extracted.participants
            if p and p.strip().lower() not in _JUNK_PARTICIPANT_TOKENS
        ]
        # If user said "all members of group" but LLM put junk in participants,
        # also force the all-members flag.
        forced_all_members = (
            extracted.split_with_all_group_members
            or (
                bool(extracted.group_name)
                and len(cleaned_participants) < len(extracted.participants)
            )
        )

        logger.info(
            "create_expense extraction → amount=%s desc=%r participants=%s "
            "group=%r all_members=%s",
            extracted.amount,
            extracted.description,
            cleaned_participants,
            extracted.group_name,
            forced_all_members,
        )

        # Pre-validate the group exists; show available groups if not.
        if extracted.group_name:
            groups = self._client.get_groups()
            target = self._find_group(groups, extracted.group_name)
            if not target:
                available = (
                    "\n".join(f"- {g['name']}" for g in groups)
                    if groups
                    else "(you don't have any groups)"
                )
                return (
                    f"⚠️ I couldn't find a group called **{extracted.group_name}**.\n\n"
                    f"Your existing groups:\n{available}\n\n"
                    f"Try again with the exact group name."
                )
            logger.info("Resolved group %r → id=%s", target["name"], target["id"])

        result = self._client.create_expense(
            amount=extracted.amount,
            description=extracted.description,
            participants=cleaned_participants,
            expense_date=_parse_iso_date(extracted.expense_date),
            group_name=extracted.group_name,
            split_with_all_group_members=forced_all_members,
        )

        if forced_all_members or (extracted.group_name and not cleaned_participants):
            split_desc = f"all members of **{extracted.group_name}**"
        elif cleaned_participants:
            split_desc = ", ".join(cleaned_participants)
            if extracted.group_name:
                split_desc += f" in **{extracted.group_name}**"
        else:
            split_desc = "yourself"

        return (
            f"✅ Added **{result['description']}** "
            f"for {result['currency']} {result['cost']} "
            f"split with {split_desc}. (id: `{result['id']}`)"
        )

    @staticmethod
    def _find_group(groups: list[dict], name: str) -> Optional[dict]:
        """Resolve a group by name with progressively looser matching."""
        import re

        target = name.strip().lower()
        # 1. exact case-insensitive match
        for g in groups:
            if g["name"].strip().lower() == target:
                return g
        # 2. substring match
        for g in groups:
            if target in g["name"].strip().lower():
                return g
        # 3. ignore non-alphanumerics
        normalize = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
        target_norm = normalize(target)
        for g in groups:
            if normalize(g["name"]) == target_norm:
                return g
        for g in groups:
            if target_norm and target_norm in normalize(g["name"]):
                return g
        return None

    def _list_expenses(self) -> str:
        expenses = self._client.get_expenses(limit=10)
        if not expenses:
            return "You have no recent expenses."
        lines = [
            f"- `#{e['id']}` {e['description']}: {e['currency']} {e['cost']} ({e['date'][:10]})"
            for e in expenses
        ]
        return "Your recent expenses:\n" + "\n".join(lines)

    def _expense_details(self, message: str) -> str:
        expense_id = self._extract_expense_id.invoke(
            [
                {"role": "system", "content": _EXPENSE_ID_PROMPT},
                {"role": "user", "content": message},
            ]
        ).expense_id
        e = self._client.get_expense(expense_id)
        if not e.get("id"):
            return f"Expense #{expense_id} not found."

        lines = [
            f"**Expense #{e['id']}** — {e['description']}",
            f"- Amount: {e['currency']} {e['cost']}",
            f"- Date: {e['date'][:10] if e['date'] else 'n/a'}",
            f"- Created by: {e['created_by'] or 'n/a'}",
        ]
        if e["users"]:
            lines.append("- Split:")
            for u in e["users"]:
                lines.append(
                    f"  • {u['name']} — paid {u['paid_share']}, owes {u['owed_share']}"
                )
        return "\n".join(lines)

    def _update(self, message: str) -> str:
        extracted = self._extract_update.invoke(
            [
                {"role": "system", "content": _UPDATE_PROMPT},
                {"role": "user", "content": message},
            ]
        )
        result = self._client.update_expense(
            expense_id=extracted.expense_id,
            amount=extracted.amount,
            description=extracted.description,
            expense_date=_parse_iso_date(extracted.expense_date),
        )
        return (
            f"Updated expense **#{result['id']}** — {result['description']} "
            f"({result['currency']} {result['cost']})."
        )

    def _delete(self, message: str) -> str:
        expense_id = self._extract_expense_id.invoke(
            [
                {"role": "system", "content": _EXPENSE_ID_PROMPT},
                {"role": "user", "content": message},
            ]
        ).expense_id
        success = self._client.delete_expense(expense_id)
        if success:
            return f"🗑️ Deleted expense **#{expense_id}**."
        return f"Could not delete expense #{expense_id}."

    # ── Balance ──────────────────────────────────────────────────────────────

    def _balance(self, message: str) -> str:
        balances = self._client.get_balances()
        if not balances:
            return "You have no outstanding balances."

        message_lower = message.lower()
        filtered = [
            b for b in balances
            if b["friend"].lower().split()[0] in message_lower
            or b["friend"].lower() in message_lower
        ]
        target = filtered if filtered else balances

        lines = []
        for b in target:
            amount = float(b["amount"])
            if amount > 0:
                lines.append(f"- {b['friend']} owes you {b['currency']} {b['amount']}")
            else:
                lines.append(
                    f"- You owe {b['friend']} {b['currency']} {abs(amount):.2f}"
                )
        return "Balances:\n" + "\n".join(lines)

    # ── Groups ───────────────────────────────────────────────────────────────

    def _list_groups(self) -> str:
        groups = self._client.get_groups()
        if not groups:
            return "You have no Splitwise groups."
        lines = [
            f"- `#{g['id']}` **{g['name']}** ({len(g['members'])} members: {', '.join(g['members'])})"
            for g in groups
        ]
        return "Your groups:\n" + "\n".join(lines)

    def _group_details(self, message: str) -> str:
        group_name = self._extract_group_name.invoke(
            [
                {"role": "system", "content": _GROUP_NAME_PROMPT},
                {"role": "user", "content": message},
            ]
        ).group_name

        groups = self._client.get_groups()
        match = next(
            (g for g in groups if g["name"].lower() == group_name.lower()),
            next(
                (g for g in groups if group_name.lower() in g["name"].lower()),
                None,
            ),
        )
        if not match:
            return f"Group '{group_name}' not found."

        details = self._client.get_group(match["id"])
        lines = [
            f"**{details['name']}** (id: {details['id']})",
            f"- Members ({len(details['members'])}): {', '.join(details['members'])}",
            f"- Simplify debts: {'on' if details['simplify_by_default'] else 'off'}",
        ]
        if details.get("simplified_debts"):
            lines.append(f"- Outstanding debts: {len(details['simplified_debts'])}")
        return "\n".join(lines)

    # ── Comments ─────────────────────────────────────────────────────────────

    def _comments(self, message: str) -> str:
        expense_id = self._extract_expense_id.invoke(
            [
                {"role": "system", "content": _EXPENSE_ID_PROMPT},
                {"role": "user", "content": message},
            ]
        ).expense_id
        comments = self._client.get_comments(expense_id)
        if not comments:
            return f"No comments on expense #{expense_id}."
        lines = [
            f"- *{c['author'] or 'Unknown'}*: {c['content']}"
            for c in comments
        ]
        return f"Comments on expense #{expense_id}:\n" + "\n".join(lines)

    # ── Currencies ───────────────────────────────────────────────────────────

    def _currencies(self) -> str:
        currencies = self._client.get_currencies()
        if not currencies:
            return "Could not fetch currencies."
        codes = sorted({c["code"] for c in currencies if c.get("code")})
        preview = ", ".join(codes[:25])
        more = f" … (+{len(codes) - 25} more)" if len(codes) > 25 else ""
        return f"Splitwise supports {len(codes)} currencies: {preview}{more}"
