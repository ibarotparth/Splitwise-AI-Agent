from unittest.mock import MagicMock, patch

import pytest

from app.tools.splitwise import SplitwiseClient, SplitwiseClientInterface
from app.security import Settings


@pytest.fixture
def settings():
    return Settings(
        splitwise_consumer_key="key",
        splitwise_consumer_secret="secret",
        splitwise_access_token="token",
        splitwise_access_token_secret="token_secret",
        openai_api_key="sk-test",
        openai_model="gpt-4o-mini",
    )


@pytest.fixture
def client(settings):
    with patch("app.tools.splitwise.OAuth1Session"):
        return SplitwiseClient(settings)


def _mock_response(client, json_payload: dict):
    client._session.get.return_value = MagicMock(
        status_code=200,
        json=lambda: json_payload,
        raise_for_status=lambda: None,
    )
    client._session.post.return_value = MagicMock(
        status_code=200,
        json=lambda: json_payload,
        raise_for_status=lambda: None,
    )


# ── Interface compliance ─────────────────────────────────────────────────────

def test_implements_interface(client):
    assert isinstance(client, SplitwiseClientInterface)


# ── Existing API tests ───────────────────────────────────────────────────────

def test_get_expenses_returns_parsed_list(client):
    _mock_response(
        client,
        {
            "expenses": [
                {
                    "id": 1,
                    "description": "Lunch",
                    "cost": "20.00",
                    "currency_code": "USD",
                    "date": "2024-01-01T00:00:00Z",
                    "created_by": {"first_name": "Alice"},
                    "users": [],
                }
            ]
        },
    )
    result = client.get_expenses(limit=1)
    assert len(result) == 1
    assert result[0]["description"] == "Lunch"
    assert result[0]["currency"] == "USD"


def test_get_balances_filters_zero(client):
    _mock_response(
        client,
        {
            "friends": [
                {
                    "id": 2,
                    "first_name": "Bob",
                    "last_name": "Smith",
                    "balance": [{"amount": "0.00", "currency_code": "USD"}],
                },
                {
                    "id": 3,
                    "first_name": "Carol",
                    "last_name": "Jones",
                    "balance": [{"amount": "15.00", "currency_code": "USD"}],
                },
            ]
        },
    )
    result = client.get_balances()
    assert len(result) == 1
    assert result[0]["friend"] == "Carol Jones"


def test_resolve_participant_ids_matches_first_name():
    friends = [
        {"id": 10, "first_name": "alice", "last_name": "wonder"},
        {"id": 11, "first_name": "bob", "last_name": "builder"},
    ]
    ids = SplitwiseClient._resolve_participant_ids(["alice"], friends)
    assert ids == [10]


def test_resolve_participant_ids_no_match():
    friends = [{"id": 10, "first_name": "alice", "last_name": "wonder"}]
    ids = SplitwiseClient._resolve_participant_ids(["unknown"], friends)
    assert ids == []


# ── New API tests ────────────────────────────────────────────────────────────

def test_get_expense_returns_single(client):
    _mock_response(
        client,
        {
            "expense": {
                "id": 99,
                "description": "Pizza",
                "cost": "30.00",
                "currency_code": "USD",
                "date": "2024-02-02T00:00:00Z",
                "users": [],
            }
        },
    )
    result = client.get_expense(99)
    assert result["id"] == 99
    assert result["description"] == "Pizza"


def test_update_expense_sends_only_provided_fields(client):
    _mock_response(
        client,
        {"expenses": [{"id": 99, "description": "Updated", "cost": "40.00", "currency_code": "USD"}]},
    )
    result = client.update_expense(99, amount=40.0, description="Updated")
    assert result["description"] == "Updated"
    args, kwargs = client._session.post.call_args
    posted_data = kwargs.get("data") or args[1]
    assert posted_data == {"cost": "40.0", "description": "Updated"}


def test_update_expense_raises_when_no_fields(client):
    with pytest.raises(ValueError):
        client.update_expense(99)


def test_delete_expense_returns_true_on_success(client):
    _mock_response(client, {"success": True})
    assert client.delete_expense(99) is True


def test_get_groups_returns_parsed(client):
    _mock_response(
        client,
        {
            "groups": [
                {
                    "id": 1,
                    "name": "Roommates",
                    "members": [
                        {"first_name": "Alice", "last_name": "A"},
                        {"first_name": "Bob", "last_name": "B"},
                    ],
                }
            ]
        },
    )
    result = client.get_groups()
    assert result[0]["name"] == "Roommates"
    assert "Alice A" in result[0]["members"]


def test_get_group_returns_details(client):
    _mock_response(
        client,
        {
            "group": {
                "id": 5,
                "name": "Trip",
                "members": [{"first_name": "Bob", "last_name": "B"}],
                "simplify_by_default": True,
                "original_debts": [],
                "simplified_debts": [{"from": 1, "to": 2, "amount": "10"}],
            }
        },
    )
    result = client.get_group(5)
    assert result["id"] == 5
    assert result["simplify_by_default"] is True
    assert len(result["simplified_debts"]) == 1


def test_get_comments_returns_parsed(client):
    _mock_response(
        client,
        {
            "comments": [
                {
                    "id": 1,
                    "content": "Thanks!",
                    "created_at": "2024-01-01",
                    "user": {"first_name": "Bob", "last_name": "B"},
                }
            ]
        },
    )
    result = client.get_comments(99)
    assert result[0]["content"] == "Thanks!"
    assert result[0]["author"] == "Bob B"


def test_split_amount_absorbs_remainder():
    shares = SplitwiseClient._split_amount(156.27, 5)
    assert shares == ["31.25", "31.25", "31.25", "31.25", "31.27"]
    assert sum(float(s) for s in shares) == pytest.approx(156.27)


def test_create_expense_with_all_group_members(client):
    # Need to script multiple GET responses in order:
    #  1. /get_current_user
    #  2. /get_groups (resolve group name → id)
    #  3. /get_group/{id} (fetch member ids)
    get_responses = [
        {"user": {"id": 1, "first_name": "Me"}},
        {"groups": [{"id": 100, "name": "548 Maple Ave"}]},
        {"group": {"id": 100, "members": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]}},
    ]
    client._session.get.side_effect = [
        MagicMock(json=lambda r=r: r, raise_for_status=lambda: None)
        for r in get_responses
    ]
    client._session.post.return_value = MagicMock(
        json=lambda: {"expenses": [{"id": 555, "description": "NIB", "cost": "156.27", "currency_code": "USD"}]},
        raise_for_status=lambda: None,
    )

    result = client.create_expense(
        amount=156.27,
        description="NIB",
        participants=[],
        group_name="548 Maple Ave",
        split_with_all_group_members=True,
    )

    assert result["id"] == 555
    posted = client._session.post.call_args.kwargs["data"]
    assert posted["group_id"] == 100
    # All 4 group members should appear
    user_ids = {posted[f"users__{i}__user_id"] for i in range(4)}
    assert user_ids == {1, 2, 3, 4}
    # Total of owed shares should equal the amount
    total_owed = sum(float(posted[f"users__{i}__owed_share"]) for i in range(4))
    assert total_owed == pytest.approx(156.27)
    # Current user (id 1) paid the full amount
    paid_by_user = {
        posted[f"users__{i}__user_id"]: posted[f"users__{i}__paid_share"]
        for i in range(4)
    }
    assert paid_by_user[1] == "156.27"
    assert paid_by_user[2] == "0.00"


def test_get_currencies_returns_codes(client):
    _mock_response(
        client,
        {
            "currencies": [
                {"currency_code": "USD", "unit": "$"},
                {"currency_code": "EUR", "unit": "€"},
            ]
        },
    )
    result = client.get_currencies()
    codes = {c["code"] for c in result}
    assert codes == {"USD", "EUR"}
