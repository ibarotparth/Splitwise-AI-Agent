# Requirements: Splitwise AI Agent

## Overview

A skill-based conversational agent over the Splitwise API. Users interact in natural language; the agent classifies intent, dispatches to a dedicated skill, and either returns a response or asks for clarification via interactive widgets when something is ambiguous.

---

## Functional requirements

### F1. Expenses

| ID | Requirement |
|---|---|
| F1.1 | **Create** an expense from natural language (amount, description, participants, optional date, optional group). |
| F1.2 | When the user mentions a group, **auto-resolve** the group ID via fuzzy matching (exact → substring → alphanumerics-only). |
| F1.3 | When a group is matched and no specific people are named, default to **splitting among all group members**. |
| F1.4 | Support **four split types**: equal, exact amounts, percentages, shares. The user picks via a radio widget; configures via per-person number inputs (except equal, which is auto-computed). |
| F1.5 | When the user names participants, **resolve them with confidence scoring**, preferring group members over generic friends. If any name is ambiguous or missing, ask the user via a multi-select widget. |
| F1.6 | If the user provides no description / title, use **`Expense — {Mon D, YYYY}`** as a default. |
| F1.7 | Always show a **confirmation widget** before posting any expense to Splitwise. |
| F1.8 | **List** the user's recent expenses (default: last 10). |
| F1.9 | View **details** of one expense by ID, including who paid and who owes what. |
| F1.10 | **Update** an existing expense (any subset of: amount, description, date). |
| F1.11 | **Delete** an expense by ID. |
| F1.12 | **Undo** the most recently AI-created expense in the current session via the literal command `undo` (no LLM round-trip). |

### F2. Balances

| ID | Requirement |
|---|---|
| F2.1 | Show all outstanding balances (filters out zero balances). |
| F2.2 | When the user mentions a friend by name, **filter** to that friend only (case-insensitive substring match). |
| F2.3 | Format positive amounts as "X owes you Y" and negative as "You owe X Y". |

### F3. Groups

| ID | Requirement |
|---|---|
| F3.1 | List all groups with member names and counts. |
| F3.2 | Show details of a specific group: members, simplify-debts setting, count of outstanding debts. |
| F3.3 | Group name resolution must be tolerant of punctuation, case, and partial matches. |
| F3.4 | Distinguish "show details of [name with numbers]" (group lookup) from "show details of expense [number]" (expense lookup) — the intent classifier must not confuse a bare number with an expense ID. |

### F4. Comments & currencies

| ID | Requirement |
|---|---|
| F4.1 | Show comments on a specific expense by ID. |
| F4.2 | List supported Splitwise currencies (top 25 + total count). |

### F5. Conversational behavior

| ID | Requirement |
|---|---|
| F5.1 | The agent must **never silently guess** when participant or group resolution is ambiguous. |
| F5.2 | All write operations must show a confirmation summary before submitting to Splitwise. |
| F5.3 | The user can **type a free-text message at any time** to break out of a multi-turn flow. |
| F5.4 | The agent must respond to `undo` (and variants) without invoking the LLM. |

### F6. Error handling

| ID | Requirement |
|---|---|
| F6.1 | API failures must surface a clean message (not a stack trace). |
| F6.2 | When intent is `unknown`, show a help message listing all supported actions with examples. |
| F6.3 | If the LLM returns junk participant tokens (e.g. "all", "everyone", "members"), filter them out and treat as "all group members". |

---

## Non-functional requirements

| Concern | Requirement |
|---|---|
| Latency | Read queries < 3 s; create flow each step < 4 s on `gpt-4o`. |
| Cost | Reads use `gpt-4o-mini` (~$0.15 / 1M input tokens). Writes use `gpt-4o`. Both configurable. |
| Security | Splitwise OAuth 1.0 credentials in `.env` only — never logged or persisted. UI never talks to Splitwise directly. |
| Reliability | Skills wrap their own exceptions; failure in one skill does not corrupt graph state. |
| Maintainability | Each skill has one responsibility; depends on `SplitwiseClientInterface` (ABC), not the concrete client. New intents add ~1 file + 1 routing entry. |
| Testability | Unit tests inject mocks for both the client and the LLM. Target: ≥35 tests, no live API in CI. |
| Statelessness | The backend is stateless; multi-turn `pending` state is round-tripped via the API contract. |

---

## API contracts

### `POST /chat`

**Request (`ChatRequest`):**

| Field | Type | Notes |
|---|---|---|
| `message` | `str?` | Free-text user input. Optional when `selection` / `numeric_inputs` is provided. |
| `history` | `list[AgentMessage]` | Prior chat turns. |
| `selection` | `list[str]?` | Option IDs picked from a widget. |
| `numeric_inputs` | `dict[str, float]?` | For the `split_details` widget. |
| `pending` | `PendingAction?` | State from previous turn (echoed by client). |

**Response (`ChatResponse`):**

| Field | Type | Notes |
|---|---|---|
| `reply` | `str` | Markdown-rendered text for the chat. |
| `awaiting_input` | `AwaitingInput?` | If present, UI must render a widget. |
| `pending` | `PendingAction?` | If present, UI must echo it back next turn. |

### `GET /health`

Returns `{"status": "ok"}`.

---

## Out of scope (current)

- Voice input
- Native mobile apps
- Multi-user authentication (single-user only)
- Real-time push notifications
- Settlement / debt-simplification write operations
- Friend management (add/remove)
- Expense attachments (receipts, photos)

---

## API dependencies

| API | Purpose | Auth | Cost |
|---|---|---|---|
| Splitwise REST v3 | Expense CRUD, balances, groups, currencies, comments | OAuth 1.0 HMAC-SHA1 | Free |
| OpenAI API | Intent classification + structured extraction | API key | ~$0.15–$3 / 1M tokens depending on model |
