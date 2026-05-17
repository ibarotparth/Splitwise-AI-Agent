# 💸 Splitwise AI Agent

A skill-based conversational agent for [Splitwise](https://www.splitwise.com/), powered by **LangGraph + OpenAI**. Add expenses, check balances, manage groups, and undo mistakes — all in plain English, with smart interactive widgets when something is ambiguous.

```text
You: add $156.27 NIB 4/29 in 548 Maple Ave with all members
Bot: ✅ Added NIB 4/29 for $156.27 in 548 Maple Ave (id #12345)
       • You (you):   $39.07
       • Alice:       $39.07
       • Bob:         $39.07
       • Carol:       $39.06
     Type "undo" to delete this expense.
```

---

## ✨ What it does

| Capability        | Example                                                                                    |
| ----------------- | ------------------------------------------------------------------------------------------ |
| Smart expense add | _"add $30 dinner with Alice"_ — agent asks for group / split type via widgets if ambiguous |
| Group expense     | _"add $156 in Roommates with all members"_ — auto-resolves group + member IDs              |
| List recent       | _"show recent expenses"_                                                                   |
| View one          | _"show details of expense 12345"_                                                          |
| Update            | _"change expense 12345 amount to $30"_                                                     |
| Delete            | _"delete expense 12345"_                                                                   |
| **Undo**          | _"undo"_ — removes the last AI-created expense in the session                              |
| Balances          | _"what do I owe John?"_ (or _"show all balances"_)                                         |
| Groups            | _"show all my groups"_ / _"show details of 548 Maple Ave"_                                 |
| Comments          | _"show comments on expense 12345"_                                                         |
| Currencies        | _"what currencies are supported?"_                                                         |

### How it stays accurate

- **Multi-turn flow** for writes: agent asks for clarification with **interactive widgets** (radio, checkboxes, sliders) — never silently guesses
- **Confidence-scored name matching** with group-first preference (a friend named "Alice" loses to a group member named "Alice")
- **Four split modes**: equal · exact · percentage · shares
- **Undo button** as a safety net for AI-created expenses

---

## 🏗️ Architecture

A skill-based agent built on LangGraph with a two-model strategy:

```
User input
    ▼
intent_classifier  ── gpt-4o-mini (cheap)
    ▼
SkillRouter ──▶ ExpenseCreateSkill   ── gpt-4o (smart)
                ExpenseQuerySkill    ── gpt-4o-mini
                ExpenseModifySkill   ── gpt-4o
                BalanceSkill         ── no LLM
                GroupSkill           ── gpt-4o-mini
                CurrencySkill        ── no LLM
    ▼
response  +  optional `awaiting_input` widget spec
```

Reads use the cheap classifier model. Only writes/extractions use the smarter extractor model. Configurable via env.

---

## 🚀 Quick start

### 1. Clone & venv

```bash
git clone https://github.com/yourusername/splitwise-ai-agent.git
cd splitwise-ai-agent
python -m venv venv && source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure `.env`

Copy and fill in:

```bash
cp .env.example .env
```

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_CLASSIFIER_MODEL=gpt-4o-mini   # optional
OPENAI_EXTRACTOR_MODEL=gpt-4o         # optional

# Splitwise OAuth 1.0 (HMAC-SHA1)
# Get from: https://secure.splitwise.com/oauth_clients
SPLITWISE_CONSUMER_KEY=...
SPLITWISE_CONSUMER_SECRET=...
SPLITWISE_ACCESS_TOKEN=...
SPLITWISE_ACCESS_TOKEN_SECRET=...
```

### 4. Run

Two terminals (both with venv activated):

```bash
# Terminal 1 — backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — UI
streamlit run ui/chat_app.py --server.port 8501
```

Open **http://localhost:8501**.

---

## 📁 Project structure

```
splitwise-ai-agent/
├── app/
│   ├── main.py                       # FastAPI: GET /health, POST /chat
│   ├── graph.py                      # LangGraph factory (build_graph)
│   ├── schemas.py                    # Pydantic + AgentState + multi-turn primitives
│   ├── security.py                   # Settings dataclass (env loading)
│   ├── tools/
│   │   └── splitwise.py              # SplitwiseClientInterface (ABC) + OAuth 1.0 client
│   ├── matchers/
│   │   ├── group_matcher.py          # find_group() — fuzzy resolution
│   │   └── name_matcher.py           # confidence-scored participant matching
│   ├── skills/
│   │   ├── base.py                   # Skill ABC
│   │   ├── intent_classifier_skill.py
│   │   ├── expense_create_skill.py   # ⭐ multi-turn flow
│   │   ├── expense_query_skill.py    # list / details
│   │   ├── expense_modify_skill.py   # update / delete / undo
│   │   ├── balance_skill.py
│   │   ├── group_skill.py
│   │   ├── currency_skill.py
│   │   └── error_skill.py
│   └── nodes/
│       └── router.py                 # SkillRouter dispatcher
├── ui/
│   └── chat_app.py                   # Streamlit chat + sidebar + widget renderer
├── tests/
│   ├── test_matchers.py              # 13 tests
│   ├── test_nodes.py                 # 11 tests (skills)
│   └── test_tools.py                 # 15 tests (Splitwise client)
```

---

## 🧪 Testing

```bash
pytest tests/ -v
```

39 tests covering matchers, skills, and the Splitwise client (mocked — no live API calls).

---

## 🛠️ Splitwise APIs in use

11 endpoints across reads + writes:

| Endpoint                    | Purpose                           |
| --------------------------- | --------------------------------- |
| `GET /get_current_user`     | "Paid by" user ID                 |
| `GET /get_friends`          | Name resolution + balances        |
| `GET /get_groups`           | List + name resolution            |
| `GET /get_group/{id}`       | Members + simplified debts        |
| `GET /get_expenses`         | Recent expenses                   |
| `GET /get_expense/{id}`     | Single expense                    |
| `GET /get_comments`         | Comments on an expense            |
| `GET /get_currencies`       | Currency list                     |
| `POST /create_expense`      | Create (with optional `group_id`) |
| `POST /update_expense/{id}` | Edit                              |
| `POST /delete_expense/{id}` | Delete (used by undo)             |

Auth: OAuth 1.0 HMAC-SHA1 via `requests-oauthlib`.

---

## 🎨 UI

The Streamlit UI:

- Sidebar with categorized features + "Try" buttons that queue example prompts
- Free-text chat input
- **Interactive widgets** rendered when the agent needs clarification:
  - Radio buttons for group choice / split type / confirmation
  - Checkboxes for participant selection
  - Per-person number inputs for split details (with live total validation)
- "Clear chat history" button

---

## 🔐 Security notes

- `.env` is gitignored — never commit Splitwise/OpenAI keys
- All Splitwise calls are proxied through the FastAPI backend; the UI has no direct API access
- The agent will not perform destructive operations without showing a confirmation widget first
