from abc import ABC, abstractmethod
from datetime import date as DateType
from typing import Optional

from requests_oauthlib import OAuth1Session

from app.security import Settings


BASE_URL = "https://secure.splitwise.com/api/v3.0"


# ── Interface (Dependency Inversion) ─────────────────────────────────────────

class SplitwiseClientInterface(ABC):
    @abstractmethod
    def get_expenses(self, limit: int = 20) -> list[dict]: ...

    @abstractmethod
    def get_expense(self, expense_id: int) -> dict: ...

    @abstractmethod
    def create_expense(
        self,
        amount: float,
        description: str,
        participants: list[str],
        expense_date: Optional[DateType] = None,
        group_name: Optional[str] = None,
        split_with_all_group_members: bool = False,
    ) -> dict: ...

    @abstractmethod
    def update_expense(
        self,
        expense_id: int,
        amount: Optional[float] = None,
        description: Optional[str] = None,
        expense_date: Optional[DateType] = None,
    ) -> dict: ...

    @abstractmethod
    def delete_expense(self, expense_id: int) -> bool: ...

    @abstractmethod
    def get_balances(self) -> list[dict]: ...

    @abstractmethod
    def get_groups(self) -> list[dict]: ...

    @abstractmethod
    def get_group(self, group_id: int) -> dict: ...

    @abstractmethod
    def get_comments(self, expense_id: int) -> list[dict]: ...

    @abstractmethod
    def get_currencies(self) -> list[dict]: ...


# ── Concrete implementation ───────────────────────────────────────────────────

class SplitwiseClient(SplitwiseClientInterface):
    def __init__(self, settings: Settings) -> None:
        self._session = OAuth1Session(
            client_key=settings.splitwise_consumer_key,
            client_secret=settings.splitwise_consumer_secret,
            resource_owner_key=settings.splitwise_access_token,
            resource_owner_secret=settings.splitwise_access_token_secret,
        )

    # ── HTTP helpers ─────────────────────────────────────────────────────────

    def _get(self, path: str, **params) -> dict:
        resp = self._session.get(f"{BASE_URL}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        resp = self._session.post(f"{BASE_URL}{path}", data=data)
        resp.raise_for_status()
        return resp.json()

    # ── Expenses ─────────────────────────────────────────────────────────────

    def get_expenses(self, limit: int = 20) -> list[dict]:
        data = self._get("/get_expenses", limit=limit)
        return [self._format_expense(e) for e in data.get("expenses", [])]

    def get_expense(self, expense_id: int) -> dict:
        data = self._get(f"/get_expense/{expense_id}")
        return self._format_expense(data.get("expense", {}))

    def create_expense(
        self,
        amount: float,
        description: str,
        participants: list[str],
        expense_date: Optional[DateType] = None,
        group_name: Optional[str] = None,
        split_with_all_group_members: bool = False,
    ) -> dict:
        if expense_date is None:
            expense_date = DateType.today()

        current_user = self._get("/get_current_user")["user"]
        current_user_id: int = current_user["id"]

        payload: dict = {
            "cost": str(amount),
            "description": description,
            "date": expense_date.isoformat(),
            "split_equally": False,
        }

        # Resolve group → group_id and (optionally) all member IDs.
        group_id: Optional[int] = None
        group_member_ids: list[int] = []
        if group_name:
            group_id = self._resolve_group_id(group_name)
            if group_id is not None:
                payload["group_id"] = group_id
                # Default: if user mentioned a group but no specific people,
                # treat that as "split among everyone in the group".
                if split_with_all_group_members or not participants:
                    group_member_ids = self._get_group_member_ids(group_id)

        # Build the participant ID list.
        if group_member_ids:
            all_ids = list(dict.fromkeys(group_member_ids))
            if current_user_id not in all_ids:
                all_ids.insert(0, current_user_id)
        else:
            friends = self._get("/get_friends").get("friends", [])
            participant_ids = self._resolve_participant_ids(participants, friends)
            all_ids = [current_user_id] + participant_ids

        # Split amount evenly, with rounding remainder absorbed by last share.
        shares = self._split_amount(amount, len(all_ids))

        for i, uid in enumerate(all_ids):
            payload[f"users__{i}__user_id"] = uid
            payload[f"users__{i}__paid_share"] = (
                f"{amount:.2f}" if uid == current_user_id else "0.00"
            )
            payload[f"users__{i}__owed_share"] = shares[i]

        created = self._post("/create_expense", payload)
        expense = created.get("expenses", [{}])[0]
        return self._format_expense(expense)

    def update_expense(
        self,
        expense_id: int,
        amount: Optional[float] = None,
        description: Optional[str] = None,
        expense_date: Optional[DateType] = None,
    ) -> dict:
        payload: dict = {}
        if amount is not None:
            payload["cost"] = str(amount)
        if description is not None:
            payload["description"] = description
        if expense_date is not None:
            payload["date"] = expense_date.isoformat()

        if not payload:
            raise ValueError("No fields provided to update.")

        updated = self._post(f"/update_expense/{expense_id}", payload)
        expense = updated.get("expenses", [{}])[0]
        return self._format_expense(expense)

    def delete_expense(self, expense_id: int) -> bool:
        result = self._post(f"/delete_expense/{expense_id}", {})
        return bool(result.get("success", False))

    # ── Balances / Friends ───────────────────────────────────────────────────

    def get_balances(self) -> list[dict]:
        friends = self._get("/get_friends").get("friends", [])
        balances = []
        for f in friends:
            for bal in f.get("balance", []):
                if float(bal["amount"]) != 0:
                    balances.append(
                        {
                            "friend": f"{f['first_name']} {f['last_name']}".strip(),
                            "amount": bal["amount"],
                            "currency": bal["currency_code"],
                        }
                    )
        return balances

    # ── Groups ───────────────────────────────────────────────────────────────

    def get_groups(self) -> list[dict]:
        data = self._get("/get_groups")
        return [
            {
                "id": g["id"],
                "name": g["name"],
                "members": [
                    f"{m['first_name']} {m['last_name']}".strip()
                    for m in g.get("members", [])
                ],
            }
            for g in data.get("groups", [])
        ]

    def get_group(self, group_id: int) -> dict:
        data = self._get(f"/get_group/{group_id}")
        group = data.get("group", {})
        return {
            "id": group.get("id"),
            "name": group.get("name"),
            "members": [
                f"{m['first_name']} {m['last_name']}".strip()
                for m in group.get("members", [])
            ],
            "simplify_by_default": group.get("simplify_by_default", False),
            "original_debts": group.get("original_debts", []),
            "simplified_debts": group.get("simplified_debts", []),
        }

    # ── Comments ─────────────────────────────────────────────────────────────

    def get_comments(self, expense_id: int) -> list[dict]:
        data = self._get("/get_comments", expense_id=expense_id)
        return [
            {
                "id": c.get("id"),
                "content": c.get("content"),
                "created_at": c.get("created_at"),
                "author": (
                    f"{c['user']['first_name']} {c['user']['last_name']}".strip()
                    if c.get("user")
                    else None
                ),
            }
            for c in data.get("comments", [])
        ]

    # ── Currencies ───────────────────────────────────────────────────────────

    def get_currencies(self) -> list[dict]:
        data = self._get("/get_currencies")
        return [
            {"code": c.get("currency_code"), "unit": c.get("unit")}
            for c in data.get("currencies", [])
        ]

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _format_expense(e: dict) -> dict:
        return {
            "id": e.get("id"),
            "description": e.get("description"),
            "cost": e.get("cost"),
            "currency": e.get("currency_code"),
            "date": e.get("date"),
            "group_id": e.get("group_id"),
            "created_by": (
                e["created_by"]["first_name"] if e.get("created_by") else None
            ),
            "users": [
                {
                    "name": u["user"]["first_name"],
                    "paid_share": u["paid_share"],
                    "owed_share": u["owed_share"],
                }
                for u in e.get("users", [])
            ],
        }

    @staticmethod
    def _resolve_participant_ids(participants: list[str], friends: list[dict]) -> list[int]:
        ids = []
        for name in participants:
            name_lower = name.lower()
            match = next(
                (
                    f["id"]
                    for f in friends
                    if f["first_name"].lower() == name_lower
                    or f"{f['first_name']} {f['last_name']}".lower().startswith(name_lower)
                ),
                None,
            )
            if match is not None:
                ids.append(match)
        return ids

    def _get_group_member_ids(self, group_id: int) -> list[int]:
        group = self._get(f"/get_group/{group_id}").get("group", {})
        return [m["id"] for m in group.get("members", []) if m.get("id") is not None]

    @staticmethod
    def _split_amount(amount: float, n: int) -> list[str]:
        """Split amount into n shares with 2-decimal precision; last absorbs remainder."""
        if n <= 0:
            return []
        base = round(amount / n, 2)
        shares = [base] * (n - 1)
        shares.append(round(amount - sum(shares), 2))
        return [f"{s:.2f}" for s in shares]

    def _resolve_group_id(self, group_name: str) -> Optional[int]:
        groups = self._get("/get_groups").get("groups", [])
        name_lower = group_name.lower()
        return next(
            (g["id"] for g in groups if g["name"].lower() == name_lower),
            next(
                (g["id"] for g in groups if name_lower in g["name"].lower()),
                None,
            ),
        )
