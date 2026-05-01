# Tech Stack: Splitwise AI Agent

## Decision Summary

**LLM provider: OpenAI only (for now)**

Three-provider architecture (OpenAI + NVIDIA + Ollama) was considered and rejected. NVIDIA's `langchain_nvidia_ai_endpoints` has a known `ModelProfile` compatibility break with `langchain-core >= 0.2`. Ollama is not part of this project. OpenAI is the sole LLM provider — model is switchable via env var (`gpt-4o-mini` for dev, `gpt-4o` for production).

**Agent framework: LangGraph (replaces LangChain AgentExecutor)**

LangGraph gives explicit control over agent state, retry loops, and human-in-the-loop pauses — all things needed here — without the implicit magic of AgentExecutor that makes debugging painful.

---

## Core Stack

### Language & Runtime

- **Python 3.11+** — use 3.11 over 3.10; better error messages and ~10–15% faster async

### AI & Agent

| Package            | Version | Purpose                              |
| ------------------ | ------- | ------------------------------------ |
| `langgraph`        | `>=0.2` | StateGraph-based agent orchestration |
| `langchain-core`   | `>=0.2` | Base types, Runnable interface       |
| `langchain-openai` | latest  | OpenAI chat model integration        |
| `openai`           | `>=1.0` | Direct SDK (fallback, cost tracking) |

> Do NOT install `langchain-nvidia-ai-endpoints` or `langchain` (the monolith) — they pull in conflicting `langchain-core` pins.

### Web Backend

- **FastAPI** `>=0.110` — async REST API, auto-docs at `/docs`
- **Uvicorn** — ASGI server
- **Pydantic v2** — request/response validation and LLM structured output schemas

### Frontend

- **Streamlit** `>=1.32` — chat interface; `st.chat_message` + `st.chat_input` for the conversation UI

### Security

- **python-jose[cryptography]** — JWT for session tokens
- **slowapi** (Phase 3) — rate limiting middleware for FastAPI

> `cryptography` (Fernet) has been removed. The original design encrypted a simple Splitwise API key at rest, but Splitwise uses OAuth 1.0 — the four OAuth credentials live in `.env` and are never stored in the database.

### HTTP

- **httpx** — async HTTP client for general requests
- **requests-oauthlib** — OAuth 1.0 HMAC-SHA1 request signing for Splitwise API calls

### Persistence

- **Phase 1–2**: SQLite via LangGraph's built-in `SqliteSaver` checkpointer
- **Phase 3**: PostgreSQL via `asyncpg` + LangGraph `PostgresSaver`

### Dev Tooling

| Tool                        | Purpose                                |
| --------------------------- | -------------------------------------- |
| `black`                     | Auto-formatter                         |
| `ruff`                      | Linter (faster replacement for flake8) |
| `mypy`                      | Static type checking                   |
| `pytest` + `pytest-asyncio` | Testing (unit + async)                 |
| `python-dotenv`             | `.env` loading                         |

---

## Project Structure

```
splitwise-ai-agent/
├── app/
│   ├── main.py              # FastAPI app, route definitions
│   ├── graph.py             # LangGraph StateGraph definition
│   ├── nodes/
│   │   ├── intent.py        # Intent classification node
│   │   ├── expense.py       # Expense tool executor node
│   │   ├── analytics.py     # Analytics agent node (Phase 2)
│   │   └── error.py         # Error handler node
│   ├── tools/
│   │   └── splitwise.py     # Splitwise API tool wrappers
│   ├── schemas.py           # Pydantic models for all I/O
│   └── security.py          # Key encryption, JWT utils
├── ui/
│   └── chat_app.py          # Streamlit chat interface
├── tests/
│   ├── test_nodes.py        # Unit tests per graph node
│   └── test_tools.py        # Splitwise API mock tests
├── docker-compose.yml       # Phase 3
├── Dockerfile.api
├── Dockerfile.ui
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── requirements.md
└── tech-stack.md
```

---

## LangGraph Architecture

```
User message
     │
     ▼
┌─────────────────┐
│ intent_classifier│  ← LLM call: classify as expense / query / analytics / unknown
└────────┬────────┘
         │
    ┌────▼─────────────────────┐
    │                          │
    ▼                          ▼
expense_node            analytics_node
(create / retrieve       (summarise /
 / balance)               by category)
    │                          │
    ▼                          │
confirm_node  ◄────────────────┘
(human-in-the-loop pause)
    │
    ▼
response_formatter
    │
    ▼
  Reply
    │
    └──► error_node (on any exception, with 1 retry)
```

### Key LangGraph concepts used

- `StateGraph` with a typed `AgentState` (TypedDict)
- `SqliteSaver` checkpointer for memory persistence
- `interrupt_before=["confirm_node"]` for human-in-the-loop
- Conditional edges for routing (intent → correct agent node)

---

## Environment Variables

```bash
# .env.example

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini          # swap to gpt-4o for production

# Splitwise OAuth 1.0 (HMAC-SHA1)
# Get these from: https://secure.splitwise.com/oauth_clients
SPLITWISE_CONSUMER_KEY=your-consumer-key
SPLITWISE_CONSUMER_SECRET=your-consumer-secret
SPLITWISE_ACCESS_TOKEN=your-access-token
SPLITWISE_ACCESS_TOKEN_SECRET=your-access-token-secret
SPLITWISE_BASE_URL=https://secure.splitwise.com/api/v3.0

# App security
APP_SECRET_KEY=...                # generated: python -c "import secrets; print(secrets.token_hex(32))"

# Database
DATABASE_URL=sqlite:///./agent.db  # swap to postgres:// in Phase 3
```

> Splitwise uses OAuth 1.0 with HMAC-SHA1 signing. All four OAuth credentials are required. Use `requests-oauthlib` to handle request signing automatically (see HTTP dependencies).

---

## Installation

```bash
# 1. Clone and enter
git clone https://github.com/yourusername/splitwise-ai-agent.git
cd splitwise-ai-agent

# 2. Create venv
python -m venv venv && source venv/bin/activate

# 3. Install runtime deps
pip install fastapi uvicorn[standard] streamlit langgraph langchain-core \
            langchain-openai openai httpx requests requests-oauthlib \
            pydantic python-jose python-dotenv

# 4. Install dev deps
pip install black ruff mypy pytest pytest-asyncio

# 5. Configure
cp .env.example .env
# Fill in all four SPLITWISE_* OAuth keys and OPENAI_API_KEY

# 6. Run
uvicorn app.main:app --reload          # API on :8000
streamlit run ui/chat_app.py           # UI on :8501
```

---

## Cost Estimate

| Component          | Model            | Est. cost                          |
| ------------------ | ---------------- | ---------------------------------- |
| Chat turns (MVP)   | gpt-4o-mini      | ~$0.01–0.05 / day for personal use |
| Structured outputs | gpt-4o-mini      | included above                     |
| Hosting (Phase 3)  | Render free tier | $0 (750 hrs/month)                 |
| Splitwise API      | —                | Free (dev)                         |

---

## What Was Removed vs Original Stack

| Removed                         | Reason                                                                               | Replacement                                               |
| ------------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------- |
| `langchain` (monolith)          | Version conflicts with langgraph                                                     | `langchain-core` + `langchain-openai` only                |
| `langchain-nvidia-ai-endpoints` | Broken `ModelProfile` with core 0.2                                                  | Removed entirely                                          |
| `cryptography` (Fernet)         | Designed for simple API key encryption; Splitwise uses OAuth 1.0 — no key to encrypt | OAuth credentials live in `.env` only                     |
| `requests`                      | Sync only                                                                            | `httpx` (async) + `requests-oauthlib` (OAuth 1.0 signing) |
| `flake8`                        | Slower, less features                                                                | `ruff` (drop-in replacement, 10–100x faster)              |
| Heroku                          | Deprecated free tier                                                                 | Render / Railway                                          |
