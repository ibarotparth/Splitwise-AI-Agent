# Tech Stack: Splitwise AI Agent

## Decision summary

| Decision | Choice | Why |
|---|---|---|
| **LLM provider** | OpenAI only | Best structured-output support; two-model strategy keeps costs low |
| **Two-model strategy** | `gpt-4o-mini` for reads/classification, `gpt-4o` for create/extract | Cheap model is accurate enough for intent classification + small extractions; smarter model only used where mistakes are expensive |
| **Agent framework** | LangGraph | Explicit state, conditional routing, easy multi-turn — no AgentExecutor magic |
| **Architecture** | Skill-based (one file per capability) | Each skill is independently testable and depends on an interface, not a concrete client |
| **Splitwise auth** | OAuth 1.0 HMAC-SHA1 | The only signed-call method Splitwise supports for personal apps; uses `requests-oauthlib` |
| **API surface** | Single `POST /chat` + multi-turn state in payload | Backend stays stateless; UI replays `pending` between turns |
| **UI** | Streamlit with dynamic widgets | Free chat input + agent-driven radio/checkbox/number widgets when clarification is needed |

---

## Runtime

- **Python 3.11+**

## Core dependencies

| Package | Version | Purpose |
|---|---|---|
| `langgraph` | 1.x | StateGraph orchestration |
| `langchain-core` | 1.x | Base types, `BaseChatModel`, `Runnable` |
| `langchain-openai` | 1.x | OpenAI chat model adapter |
| `openai` | 2.x | Underlying SDK |
| `fastapi` | latest | Async web framework |
| `uvicorn` | latest | ASGI server |
| `streamlit` | latest | Chat UI |
| `pydantic` | v2 | API contracts + structured LLM outputs |
| `requests-oauthlib` | latest | OAuth 1.0 HMAC-SHA1 signing |
| `requests` | latest | HTTP client (used by `requests-oauthlib`) |
| `python-dotenv` | latest | Load `.env` |

> Do **not** install `langchain` (the monolith) or `langchain-nvidia-ai-endpoints` — they introduce conflicting `langchain-core` pins.

## Dev dependencies

| Tool | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |
| `black` | Auto-formatter |
| `ruff` | Linter |
| `mypy` | Static type checking |

---

## Layered architecture

| Layer | Files | Allowed imports |
|---|---|---|
| **Domain** | `app/schemas.py` | none (stdlib + pydantic) |
| **Infrastructure** | `app/security.py`, `app/tools/splitwise.py` | Domain |
| **Application** | `app/skills/*`, `app/matchers/*`, `app/nodes/router.py`, `app/graph.py` | Domain + Infrastructure |
| **Interface** | `app/main.py`, `ui/chat_app.py` | All inner layers |

Strict rule: nothing in **Domain** imports from outer layers. Skills depend on `SplitwiseClientInterface` (ABC), not on `SplitwiseClient` directly.

---

## Skill-based design

Every capability is a class in `app/skills/`:

```python
class Skill(ABC):
    @abstractmethod
    def can_handle(self, intent: str) -> bool: ...

    @abstractmethod
    def execute(self, state: AgentState) -> AgentState: ...
```

The router (`app/nodes/router.py`) iterates registered skills and dispatches the first that claims the intent. Adding a new capability = create one skill file + add it to the list in `build_graph()`.

| Skill | Handles | Model used |
|---|---|---|
| `IntentClassifierSkill` | (produces intent) | classifier (cheap) |
| `ExpenseCreateSkill` | `create_expense` | extractor (smart) |
| `ExpenseQuerySkill` | `get_expenses`, `get_expense_details` | classifier |
| `ExpenseModifySkill` | `update_expense`, `delete_expense`, `undo_expense` | extractor |
| `BalanceSkill` | `get_balance` | none |
| `GroupSkill` | `get_groups`, `get_group_details` | classifier |
| `CurrencySkill` | `get_currencies`, `get_comments` | none |
| `ErrorSkill` | unknown / errors | none |

---

## Multi-turn state

The backend is **stateless**. Multi-turn flows persist state by sending it back to the UI in each response, then echoing it back on the next request.

```python
class PendingAction(BaseModel):
    action: Literal["create_expense"]
    step: Literal[
        "select_group", "select_participants",
        "select_split_type", "configure_split", "confirm",
    ]
    data: dict[str, Any]
```

UI flow:

```
turn 1: user types "add $30 dinner"
  → POST /chat { message }
  ← { reply: "Which group?", awaiting_input: {...}, pending: {step: select_group, ...} }

turn 2: user picks "Roommates"
  → POST /chat { selection: ["123"], pending: {step: select_group, data: {...}} }
  ← { reply: "Who?", awaiting_input: {...}, pending: {step: select_participants, ...} }

(...continues until step="confirm" → user clicks ✅ → expense posted)
```

---

## Matcher modules

`app/matchers/` houses pure functions for ambiguity-resolution. They have no LLM dependency, no API client dependency — only inputs and outputs. This makes them the easiest part to test exhaustively.

| Module | Function | Strategy |
|---|---|---|
| `group_matcher.py` | `find_group(groups, name)` | Exact → substring → alphanumerics-only |
| `name_matcher.py` | `resolve_participants(queries, group_members, friends)` | Confidence ladder (1.0 exact full → 0.6 Levenshtein); group-first preference; ambiguous → ask user |

Key constants:

```python
HIGH_CONFIDENCE = 0.85   # auto-pick threshold
LOW_CONFIDENCE  = 0.50   # below → ignore
```

---

## Splitwise client (Infrastructure)

`SplitwiseClientInterface` is an ABC declaring 11 methods. The concrete `SplitwiseClient` implements them all using `OAuth1Session` from `requests-oauthlib`.

Two distinct create methods:

- `create_expense(...)` — high-level: resolves names, expands group → all members if needed, computes equal split internally
- `create_expense_with_ids(payer_id, owed_shares, group_id, ...)` — low-level: caller provides exact `{user_id: owed_share}` map. Used by the multi-turn create flow once the user confirms the split.

This separation lets the skill control the split type (equal/exact/percentage/shares) without leaking that logic into the client.

---

## Environment variables

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CLASSIFIER_MODEL=gpt-4o-mini   # optional; default
OPENAI_EXTRACTOR_MODEL=gpt-4o         # optional; default

# Splitwise OAuth 1.0 (HMAC-SHA1)
# Register at: https://secure.splitwise.com/oauth_clients
SPLITWISE_CONSUMER_KEY=...
SPLITWISE_CONSUMER_SECRET=...
SPLITWISE_ACCESS_TOKEN=...
SPLITWISE_ACCESS_TOKEN_SECRET=...
```

Loaded once via `Settings.from_env()` (a frozen dataclass). Missing required vars raise `EnvironmentError` listing them.

---

## Project structure

```
app/
├── security.py                        # Settings dataclass
├── schemas.py                         # Pydantic + AgentState + multi-turn types
├── graph.py                           # build_graph() factory
├── main.py                            # FastAPI: /health, /chat
├── tools/
│   └── splitwise.py                   # ABC + concrete OAuth 1.0 client
├── matchers/
│   ├── group_matcher.py
│   └── name_matcher.py
├── skills/
│   ├── base.py                        # Skill ABC
│   ├── intent_classifier_skill.py
│   ├── expense_create_skill.py        # ⭐ multi-turn flow
│   ├── expense_query_skill.py
│   ├── expense_modify_skill.py
│   ├── balance_skill.py
│   ├── group_skill.py
│   ├── currency_skill.py
│   └── error_skill.py
└── nodes/
    └── router.py                      # SkillRouter

ui/
└── chat_app.py                        # Streamlit + sidebar + widget renderer

tests/
├── test_matchers.py
├── test_nodes.py
└── test_tools.py
```

---

## LangGraph wiring

```
            ┌────────────────────┐
input ──▶  │ intent_classifier │  ── classifier_llm
            └──────────┬─────────┘
                       │ state.intent set
                       ▼
              ┌─── routing ───┐
              │ known intent? │
              │  Yes ──▶ router
              │   No ──▶ error_node
              └───────────────┘
                  │             │
                  ▼             ▼
            SkillRouter     ErrorSkill
                  │             │
                  ▼             ▼
           Skill.execute()    response
                  │
                  ▼
       response (or awaiting_input + pending)
                  │
                  ▼
                 END
```

Construction (`app/graph.py`):

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

---

## Installation

```bash
git clone https://github.com/yourusername/splitwise-ai-agent.git
cd splitwise-ai-agent

python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env  # fill in keys

# Run
uvicorn app.main:app --reload          # API on :8000
streamlit run ui/chat_app.py           # UI on :8501
```

---

## Testing

```bash
pytest tests/ -v
```

39 tests, all mock-based (no live API calls):

| File | Tests | Coverage |
|---|---|---|
| `test_matchers.py` | 13 | Group + name matching, confidence levels, group-first preference, ambiguity detection |
| `test_nodes.py` | 11 | Intent classifier, error skill, balance skill, query skill |
| `test_tools.py` | 15 | Every Splitwise client method, including `create_expense_with_ids` and rounding behavior |

---

## Cost estimate

| Workload | Model | Estimated cost |
|---|---|---|
| Intent classification (per turn) | `gpt-4o-mini` | ~$0.0001 |
| Read query handling | `gpt-4o-mini` | ~$0.0002 |
| Create flow (one full multi-turn) | `gpt-4o` | ~$0.005–0.01 |
| Personal use (~50 turns/day) | mix | ~$0.10–0.30 / day |
| Splitwise API | — | Free |

---

## Why these choices

### Why two models?
The intent classifier is a low-risk task with a closed enum of 12 outputs — `gpt-4o-mini` is plenty. But participant extraction from a fuzzy sentence like *"add $156 NIB in 548 Maple Ave with all members"* is high-risk: a wrong field becomes a wrong real-world expense. `gpt-4o` is worth the price difference there.

### Why skill-based over a single big agent?
- Each skill is < 150 lines (except the create skill which is the flagship)
- Adding a new intent = one new file + one routing entry
- Tests for one skill don't import any other skill
- Errors are localized — one broken skill doesn't break the rest

### Why widgets instead of free-text everything?
Free-text confirmation ("yes I want to add $156 to Roommates with everyone") is brittle: typos, ambiguous answers, and the agent re-running the LLM each turn. Widgets are unambiguous, render once, and the user clicks. The state-machine approach pays for itself the first time the user adds a complex split.

### Why stateless backend?
LangGraph itself supports checkpointers (`SqliteSaver`, etc.) but we don't use them — the multi-turn `pending` state is small enough to round-trip via the API. This means:
- No DB to manage in dev
- Horizontal scaling is free
- Each request is fully self-contained (easier to debug from logs)

---

## Future enhancements

| Idea | Why deferred |
|---|---|
| Settlement / debt-simplification API | Not in current scope |
| Friend management (add/remove) | Splitwise UI handles this fine |
| Receipt photo attachments | Requires file upload endpoints |
| Multi-user auth | Single-user is sufficient for personal use |
| Persistent chat history (DB) | Streamlit `session_state` is enough for now |
| Voice input | Out of scope for the chat-first UX |
