# Splitwise AI Agent — Reproduction Specification

> A complete blueprint for rebuilding this skill-based conversational agent
> for Splitwise. Any AI agent following this document should be able to
> produce an equivalent system from scratch.

---

## 1. Purpose

A natural-language assistant that lets users manage their Splitwise account
through chat. It can:

1. Add expenses (with multi-turn clarification when ambiguous)
2. List, view, update, delete, and undo expenses
3. Show balances (filtered or full)
4. List groups; show group details
5. Show comments on an expense
6. List supported currencies

The system is **conversational** for reads and **interactive (with widgets)**
for writes — it never silently guesses critical details.

---

## 2. Core principles

| Principle | How it's applied |
|---|---|
| **Clean Architecture** | Domain / Application / Infrastructure / Interface layers strictly separated. Domain (`schemas.py`) has zero deps on outer layers. |
| **SOLID** | Skill ABC + dependency injection; each skill has one responsibility; depends on `SplitwiseClientInterface`, never the concrete class. |
| **Two-model strategy** | Cheap model (`gpt-4o-mini`) for classification + simple extractions; smarter model (`gpt-4o`) only for create/update extractions. |
| **Ask, don't guess** | When confidence is low or context is missing, return a structured `awaiting_input` for the UI to render a widget — never auto-pick. |
| **Stateless backend, stateful client** | Multi-turn state is serialized into responses and replayed by the UI on the next call. The backend itself is stateless. |

---

## 3. Tech stack

| Layer | Tech | Notes |
|---|---|---|
| Language | Python 3.10+ | Uses `typing_extensions.TypedDict` for `total=False` |
| LLM orchestration | LangGraph 1.x + langchain-openai | StateGraph with intent → router → skill |
| LLM provider | OpenAI | Two models from env: `OPENAI_CLASSIFIER_MODEL`, `OPENAI_EXTRACTOR_MODEL` |
| Validation | Pydantic v2 | Used both for API contracts and for structured LLM outputs |
| API framework | FastAPI | Single `POST /chat` + `GET /health` |
| External API | Splitwise REST v3 | OAuth 1.0 HMAC-SHA1 via `requests-oauthlib` |
| UI | Streamlit | Chat + sidebar + dynamic widgets driven by response payload |
| Tests | pytest | Mock-based unit tests; no live API |

---

## 4. Directory layout

```
app/
├── security.py                        # Settings dataclass (env loading)
├── schemas.py                         # Domain models, AgentState, API contracts
├── graph.py                           # LangGraph factory (build_graph)
├── main.py                            # FastAPI app
├── tools/
│   └── splitwise.py                   # SplitwiseClientInterface (ABC) + concrete client
├── matchers/
│   ├── group_matcher.py               # find_group()  — fuzzy group resolution
│   └── name_matcher.py                # resolve_participants()  — confidence-scored matching
├── skills/
│   ├── base.py                        # Skill ABC
│   ├── intent_classifier_skill.py     # cheap-model classification
│   ├── expense_create_skill.py        # multi-turn create flow ⭐ (largest)
│   ├── expense_query_skill.py         # list / details
│   ├── expense_modify_skill.py        # update / delete / undo
│   ├── balance_skill.py
│   ├── group_skill.py
│   ├── currency_skill.py              # also handles get_comments
│   └── error_skill.py                 # help text + error rendering
└── nodes/
    └── router.py                      # SkillRouter — dispatch intent → skill

ui/
└── chat_app.py                        # Streamlit chat + sidebar + widget renderer

tests/
├── test_matchers.py                   # 13 tests
├── test_nodes.py                      # 11 tests (skills)
└── test_tools.py                      # 15 tests (Splitwise client)
```

---

## 5. Configuration (`Settings`)

A frozen dataclass loaded once from `.env`. All env vars are required except
the two model names (which default).

```python
@dataclass(frozen=True)
class Settings:
    splitwise_consumer_key: str           # SPLITWISE_CONSUMER_KEY
    splitwise_consumer_secret: str        # SPLITWISE_CONSUMER_SECRET
    splitwise_access_token: str           # SPLITWISE_ACCESS_TOKEN
    splitwise_access_token_secret: str    # SPLITWISE_ACCESS_TOKEN_SECRET
    openai_api_key: str                   # OPENAI_API_KEY
    classifier_model: str                 # OPENAI_CLASSIFIER_MODEL  (default "gpt-4o-mini")
    extractor_model: str                  # OPENAI_EXTRACTOR_MODEL   (default "gpt-4o")
```

`Settings.from_env()` validates required keys and raises `EnvironmentError`
listing what's missing.

---

## 6. Splitwise API surface

All calls go through `SplitwiseClientInterface`, an ABC with **11 methods**.
The concrete `SplitwiseClient` uses `OAuth1Session` (HMAC-SHA1).

### Reads (GET)

| Endpoint | Interface method | Purpose |
|---|---|---|
| `/get_current_user` | `get_current_user()` | User ID for "paid by" share |
| `/get_friends` | `get_friends()` | Raw list; balance source |
| `/get_groups` | `get_groups()` | Group list (with members) |
| `/get_group/{id}` | `get_group(id)` | Group + simplified debts |
| `/get_group/{id}` | `get_group_members(id)` | Just member id+name list |
| `/get_expenses?limit=N` | `get_expenses(limit)` | Recent expenses |
| `/get_expense/{id}` | `get_expense(id)` | Single expense |
| `/get_comments?expense_id=N` | `get_comments(id)` | Comments on an expense |
| `/get_currencies` | `get_currencies()` | Currency list |

Plus a balance helper: `get_balances()` — derives non-zero balances from
`/get_friends`.

### Writes (POST)

| Endpoint | Interface method | Notes |
|---|---|---|
| `/create_expense` | `create_expense(...)` | High-level — name resolution, group expansion, equal split |
| `/create_expense` | `create_expense_with_ids(...)` | Low-level — caller provides exact `{user_id: owed_share}` map. Used by multi-turn flow once split is finalized. |
| `/update_expense/{id}` | `update_expense(...)` | Only sends provided fields; raises if none |
| `/delete_expense/{id}` | `delete_expense(id)` | Returns bool |

### Internal helpers (private, on the concrete class)

- `_get(path, **params)` / `_post(path, data)` — auth + raise_for_status
- `_format_expense(raw)` — normalize Splitwise's nested response shape
- `_resolve_participant_ids(names, friends)` — name → friend ID
- `_resolve_group_id(name)` — group name → ID via `_get_groups`
- `_get_group_member_ids(group_id)` — IDs only
- `_split_amount(amount, n)` — equal split with last share absorbing the
  rounding remainder (e.g. 156.27 / 4 → `["39.07", "39.07", "39.07", "39.06"]`)

---

## 7. Domain & state schema

### Pydantic models (`app/schemas.py`)

**Public API contracts:**

```python
class ChatRequest(BaseModel):
    message: Optional[str] = None              # free text input
    history: list[AgentMessage] = []
    selection: Optional[list[str]] = None      # widget selection (option ids)
    numeric_inputs: Optional[dict[str, float]] = None  # for split_details widget
    pending: Optional[PendingAction] = None    # state from previous turn

class ChatResponse(BaseModel):
    reply: str
    awaiting_input: Optional[AwaitingInput] = None
    pending: Optional[PendingAction] = None    # to be echoed back next turn
```

**Multi-turn primitives:**

```python
AwaitingInputType = Literal[
    "group_choice",          # radio
    "participant_choice",    # multi-select checkboxes
    "split_type",            # radio
    "split_details",         # numeric inputs per person
    "confirmation",          # confirm/cancel
]

class OptionItem(BaseModel):
    id: str               # stable id sent back as selection
    label: str
    sublabel: Optional[str] = None
    selected: bool = False  # default selection

class AwaitingInput(BaseModel):
    type: AwaitingInputType
    prompt: str           # user-facing text
    options: list[OptionItem]
    multi_select: bool = False
    numeric_total: Optional[float] = None   # for split_details validation
    currency: Optional[str] = None

class PendingAction(BaseModel):
    action: Literal["create_expense"]
    step: Literal[
        "select_group", "select_participants",
        "select_split_type", "configure_split", "confirm",
    ]
    data: dict[str, Any]   # accumulated context
```

### LangGraph state (`AgentState`)

A `TypedDict(total=False)` so any subset of keys may be present:

```python
class AgentState(TypedDict, total=False):
    messages: list[dict]                # [{"role": "user"|"assistant", "content": str}]
    intent: Optional[str]
    response: Optional[str]
    error: Optional[str]
    awaiting_input: Optional[AwaitingInput]
    pending: Optional[PendingAction]
    selection: Optional[list[str]]
    numeric_inputs: Optional[dict[str, float]]
    recent_expenses: Optional[list[int]]   # for undo
```

---

## 8. Skill contract

```python
# app/skills/base.py
class Skill(ABC):
    @abstractmethod
    def can_handle(self, intent: str) -> bool: ...

    @abstractmethod
    def execute(self, state: AgentState) -> AgentState: ...
```

Every skill:

1. Receives a state with `intent` already set
2. Either returns a final `response` OR sets `awaiting_input` + `pending` for
   multi-turn continuation
3. On exception, sets `error` (skill itself wraps with try/except)
4. Receives its dependencies (LLMs, client) via constructor — no globals

Some "skills" don't quite fit the ABC (intent classifier, error renderer)
and are exposed as plain callables; they implement `__call__(state) -> state`.

---

## 9. Intents (the closed enum)

```python
Intent = Literal[
    "create_expense",
    "get_expenses",
    "get_expense_details",
    "update_expense",
    "delete_expense",
    "undo_expense",
    "get_balance",
    "get_groups",
    "get_group_details",
    "get_comments",
    "get_currencies",
    "unknown",
]
```

### Routing table

| Intent(s) | Skill |
|---|---|
| `create_expense` | `ExpenseCreateSkill` |
| `get_expenses`, `get_expense_details` | `ExpenseQuerySkill` |
| `update_expense`, `delete_expense`, `undo_expense` | `ExpenseModifySkill` |
| `get_balance` | `BalanceSkill` |
| `get_groups`, `get_group_details` | `GroupSkill` |
| `get_comments`, `get_currencies` | `CurrencySkill` |
| `unknown` | falls through → `ErrorSkill` |

### Intent classifier requirements

The classifier MUST:

- Skip the LLM call when input is the literal string `"undo"` /
  `"undo last"` / `"undo last expense"` → `undo_expense`
- Skip the LLM call when `state["pending"]` exists (we're mid-flow) →
  preserve the in-progress action's intent
- Distinguish bare numbers (likely group name parts) from explicit expense
  IDs. The prompt must include examples like:
  - `"show details of #12345"` → `get_expense_details`
  - `"show details of 548 Maple Ave"` → `get_group_details`
  - `"show details of Trip 2024"` → `get_group_details`

---

## 10. Multi-turn create-expense flow

The **flagship** of this system. Every other skill is a single round-trip;
this one is a state machine.

### State diagram

```
   User free text
        │
        ▼
   [extract]                ← gpt-4o structured output
        │
        ▼
   group resolution
        │
        ├─ found → continue
        ├─ named-but-not-found → ask: "I couldn't find X. Pick one:"
        └─ no name given → ask: "Which group?" (with "Non-group" option)
        │
        ▼  (after select_group)
   participant resolution
        │
        ├─ all names unambiguously match → continue
        ├─ any ambiguous/unresolved → ask: multi-select with candidates
        └─ no names + group known → ask: multi-select group members
        │
        ▼  (after select_participants)
   ask: split_type [equal | exact | percentage | shares]
        │
        ▼  (after select_split_type)
   if equal → auto-compute, skip to confirm
   else    → ask: split_details (numeric input per person)
        │
        ▼  (after configure_split)
   ask: confirmation [✅ Confirm | ❌ Cancel]
        │
        ▼  (after confirm)
   POST /create_expense via create_expense_with_ids()
   record id in state.recent_expenses (for undo)
   return success summary
```

### Step ↔ widget mapping

| Step | `awaiting_input.type` | UI widget |
|---|---|---|
| select_group | `group_choice` | Radio (single) |
| select_participants | `participant_choice` | Checkbox (multi) |
| select_split_type | `split_type` | Radio (single) |
| configure_split | `split_details` | Number inputs per person |
| confirm | `confirmation` | Radio (yes/no) |

### Extraction schema (gpt-4o structured output)

```python
class _ExpenseExtraction(BaseModel):
    amount: float
    description: Optional[str] = None
    participants: list[str] = []
    expense_date: Optional[str] = None    # ISO YYYY-MM-DD
    group_name: Optional[str] = None
```

The prompt MUST:

- Give explicit examples (including ones with quoted titles and addresses
  containing numbers like `"548 Maple Ave"`)
- Forbid junk strings (`"all"`, `"everyone"`, `"all members"`, group names,
  etc.) from appearing in `participants`
- Allow `description=null` (defaulted later)

After extraction, the skill applies these post-processing rules:

1. **Junk filter**: drop `participants` entries whose lowercased value is in
   `{"all", "everyone", "everybody", "all people", "all members",
   "all the people", "the group", "group", "members", "people",
   "all people of group"}`.
2. **Default title**: if `description` is empty, use
   `"Expense — {Mon D, YYYY}"`.

### Split type implementations

Each split type produces a `dict[user_id_str, owed_share_float]` that totals
the expense amount (within $0.02 tolerance). All four flavors POST the same
`/create_expense` endpoint via `create_expense_with_ids` — Splitwise itself
doesn't have a "split type" parameter; it just receives final per-user
paid/owed shares.

| Type | UI input | Computation |
|---|---|---|
| `equal` | none | `amount/n` per person; last absorbs rounding remainder |
| `exact` | dollars per person | input values used directly; must total amount ±0.02 |
| `percentage` | percent per person | `amount × pct/100`; must total 100 ±0.01; last absorbs rounding remainder |
| `shares` | share count per person | `amount × my_shares / total_shares`; total must be > 0; last absorbs rounding remainder |

### Continuation logic (replay)

When `state.pending` is set, the skill bypasses extraction and dispatches by
`pending.step` against the user's `selection` / `numeric_inputs`:

```python
if pending.step == "select_group":
    # selection[0] is "__none__" or str(group_id)
elif pending.step == "select_participants":
    # selection is list of str(user_id)
elif pending.step == "select_split_type":
    # selection[0] is "equal"|"exact"|"percentage"|"shares"
elif pending.step == "configure_split":
    # numeric_inputs is {str(user_id): float}
elif pending.step == "confirm":
    # selection[0] is "yes"|"no"
```

---

## 11. Name & group matching

### Group matcher (`matchers/group_matcher.py`)

`find_group(groups, name)` tries (in order):

1. Exact case-insensitive match on `name`
2. Substring match
3. Alphanumerics-only equality (strip punctuation/whitespace)
4. Alphanumerics-only substring

Returns the first hit, or `None`.

### Name matcher (`matchers/name_matcher.py`)

#### Confidence ladder

| Strategy | Confidence |
|---|---|
| Exact full-name match | 1.0 |
| Exact first-name match | 0.95 |
| Exact last-name match | 0.85 |
| Prefix match on full name (q ≥ 3 chars) | 0.80 |
| Prefix match on first name (q ≥ 3 chars) | 0.75 |
| Substring in full name (q ≥ 3 chars) | 0.65 |
| Levenshtein ≤ 1 vs first name (q ≥ 3 chars) | 0.60 |

#### Resolution policy

```python
HIGH_CONFIDENCE = 0.85
LOW_CONFIDENCE  = 0.50
```

`resolve_participants(queries, group_members, friends)` returns
`(resolved, needs_input)`:

1. **Group-first**: For each query, search group members with a +0.05 boost.
   If the result is unambiguous, use it and skip friends entirely.
2. **Fallback merge**: Otherwise merge group + friend matches (dedupe by
   id, keep highest confidence). If unambiguous, use; else add to
   `needs_input` so the skill can ask the user.
3. **Silent drop**: If no matches anywhere, the name is dropped — caller can
   detect via list-length mismatch.

A match is "unambiguous" when there's exactly one candidate at HIGH
confidence (no other ≥ HIGH).

---

## 12. Graph wiring (`app/graph.py`)

```
                  ┌────────────────────┐
   user input ──▶│ intent_classifier │
                  └─────────┬──────────┘
                            │  set state.intent
                            ▼
                ┌────────── routing ──────────┐
                │ intent in known? ─Yes─▶ router
                │                  ─No──▶ error_node
                └─────────────────────────────┘
                       │                 │
                       ▼                 ▼
               ┌────────────┐    ┌────────────┐
               │ SkillRouter│    │ ErrorSkill │
               └─────┬──────┘    └─────┬──────┘
                     │                 │
                     ▼                 ▼
                  Skill.execute()      response
                     │
                     ▼
                response (or awaiting_input + pending)
                     │
                     ▼
                    END
```

Construction:

```python
def build_graph(settings: Settings):
    classifier_llm = ChatOpenAI(model=settings.classifier_model, temperature=0, ...)
    extractor_llm  = ChatOpenAI(model=settings.extractor_model,  temperature=0, ...)
    client = SplitwiseClient(settings)

    router = SkillRouter([
        ExpenseCreateSkill(extractor_llm, client),
        ExpenseQuerySkill(classifier_llm, client),
        ExpenseModifySkill(extractor_llm, client),
        BalanceSkill(client),
        GroupSkill(classifier_llm, client),
        CurrencySkill(client),
    ])
    # add nodes, set entry, add conditional edges, compile
```

`SkillRouter.__call__(state)` iterates skills; first one whose
`can_handle(intent)` returns True is invoked.

---

## 13. FastAPI surface (`app/main.py`)

| Route | Method | Body | Returns |
|---|---|---|---|
| `/health` | GET | — | `{"status": "ok"}` |
| `/chat` | POST | `ChatRequest` | `ChatResponse` |

The chat handler is intentionally thin:

```python
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [{"role": m.role, "content": m.content} for m in request.history]
    if request.message:
        messages.append({"role": "user", "content": request.message})
    state = await graph.ainvoke({
        "messages": messages,
        "pending": request.pending,
        "selection": request.selection,
        "numeric_inputs": request.numeric_inputs,
        # rest default to None
    })
    return ChatResponse(
        reply=state.get("response") or state.get("error") or "Sorry…",
        awaiting_input=state.get("awaiting_input"),
        pending=state.get("pending"),
    )
```

---

## 14. UI requirements (`ui/chat_app.py`)

The Streamlit app:

- Holds chat history + `pending_state` + `awaiting` in `st.session_state`
- Sends each turn to `POST /chat` with the cached `pending_state`
- On response, replaces `pending_state` and `awaiting` from the response
- Renders the appropriate widget for `awaiting.type`

### Widget renderer pseudocode

```python
if awaiting.type in ("group_choice", "split_type", "confirmation"):
    pick = st.radio(options=labels, index=default_selected_index)
    if st.button("Continue", type="primary"):
        send(selection=[ids[pick]])

elif awaiting.type == "participant_choice":
    picks = [opt.id for opt in options if st.checkbox(opt.label, opt.selected)]
    if st.button("Continue") and picks:
        send(selection=picks)

elif awaiting.type == "split_details":
    inputs = {opt.id: st.number_input(opt.label, min_value=0.0) for opt in options}
    # show running total vs awaiting.numeric_total in green/orange
    if st.button("Continue"):
        send(selection=list(inputs.keys()), numeric_inputs=inputs)
```

### Sidebar requirements

- Brand title, short tagline (no implementation details)
- Categorized features in collapsible sections (Expenses, Balances, Groups,
  Other) — each with example prompts
- "Try" buttons that queue an example prompt
- Clear-chat button
- Dark gradient background with light text (CSS `!important` overrides
  needed because Streamlit injects its own theme)

---

## 15. Reproducibility checklist

To rebuild this system, an AI agent must:

- [ ] Create `Settings` dataclass with frozen fields and `from_env()`
      classmethod that validates required keys.
- [ ] Define `SplitwiseClientInterface` ABC with all 11 methods listed in §6.
- [ ] Implement `SplitwiseClient` with `OAuth1Session`. Include
      `_split_amount` rounding helper.
- [ ] Define `AgentState` (`TypedDict, total=False`) and the multi-turn
      Pydantic primitives (`AwaitingInput`, `OptionItem`, `PendingAction`).
- [ ] Implement `find_group()` with 4-tier fuzzy matching.
- [ ] Implement `resolve_participants()` with confidence ladder + group-first
      preference + silent-drop on no match.
- [ ] Define the `Skill` ABC with `can_handle` + `execute`.
- [ ] Implement 7 skills following §9's routing table. The
      `ExpenseCreateSkill` must implement the §10 state machine.
- [ ] Implement intent classifier with §9's two short-circuits (undo
      keyword, mid-flow `pending`) and the bare-number disambiguation
      examples.
- [ ] Build the LangGraph as in §12.
- [ ] Build the FastAPI app per §13.
- [ ] Build the Streamlit UI per §14.
- [ ] Write unit tests covering: matchers (exact/ambiguous/group-first),
      skills (each intent path), and Splitwise client (each endpoint mocked).
      Target: ≥35 tests, all passing.

---

## 16. Extension patterns

### Adding a new intent

1. Add the literal to the `Intent` union in
   `app/skills/intent_classifier_skill.py` and add a one-line description
   in the prompt.
2. Add a routing entry in §9 (and to `_KNOWN_INTENTS` in `app/graph.py` if
   it's a new top-level intent).
3. Either create a new `Skill` subclass or extend `can_handle()` of an
   existing one.
4. Register the skill in `build_graph()`.
5. Update `ErrorSkill`'s help text.
6. Add tests.

### Adding a new split type

1. Add the literal to `OptionItem` choices in `_step_split_type`.
2. Add the configuration step in `_step_configure_split` (UI prompt + total).
3. Add the computation branch in `_continue_flow`'s `configure_split` step.
4. Add a unit test that confirms the computed `owed_shares` totals the
   expense amount.

### Swapping models

Set `OPENAI_CLASSIFIER_MODEL` and/or `OPENAI_EXTRACTOR_MODEL` in `.env`.
The factory in `build_graph()` uses both — no code change required.

### Mocking Splitwise (for tests)

Create a `FakeSplitwiseClient(SplitwiseClientInterface)` returning fixture
data. Inject it into skills directly; LangGraph isn't needed for skill-level
tests.

---

## 17. Required environment

```
SPLITWISE_CONSUMER_KEY=...
SPLITWISE_CONSUMER_SECRET=...
SPLITWISE_ACCESS_TOKEN=...
SPLITWISE_ACCESS_TOKEN_SECRET=...
OPENAI_API_KEY=sk-...
OPENAI_CLASSIFIER_MODEL=gpt-4o-mini   # optional
OPENAI_EXTRACTOR_MODEL=gpt-4o         # optional
```

Run:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # backend on :8000
streamlit run ui/chat_app.py           # UI on :8501
```

---

## 18. Acceptance criteria

A reproduction is correct if **all** of the following hold:

1. The backend starts cleanly with valid `.env` and exposes `/health`,
   `/chat`.
2. `pytest tests/` reports ≥ 35 passing tests with no failures.
3. The user can type *"add $156.27 NIB in 548 Maple Ave with all members"*
   and observe:
   - Group "548 Maple Ave" auto-resolved (no widget shown for group)
   - All members of the group pre-selected and shown for confirmation
   - Default split type radio rendered with "equal" preselected
   - Confirmation summary listing each person's owed share
   - On confirm: an expense appears in the actual Splitwise account, tagged
     to the group, with the correct member shares
4. The user can type *"add $20 for dinner"* and observe a multi-turn flow:
   group selector → participants → split type → confirmation.
5. The user can type *"undo"* to delete the most recently AI-created
   expense in the session.
6. Asking *"show details of 548 Maple Ave"* routes to `get_group_details`
   (NOT `get_expense_details`).
