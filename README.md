# Splitwise AI Agent

A conversational expense management app powered by a LangGraph AI agent. Talk to your Splitwise account in plain English — add expenses, check balances, and query your spending without touching the Splitwise UI.

```
"Add $45 for dinner with Mike and Sarah"
"What do I owe John?"
"Show my expenses from last week"
```

---

## What it does

- **Natural language expense management** — create, retrieve, and query expenses conversationally
- **LangGraph-powered agent** — stateful graph with intent classification, tool execution, validation, and retry logic
- **Secure API proxy** — your Splitwise key is encrypted at rest; all API calls go through the FastAPI backend
- **Multi-turn conversations** — the agent remembers context within a session
- **Human-in-the-loop confirmation** — write operations (Phase 2) pause for your approval before submitting

---

## Tech stack

| Layer            | Technology                                        |
| ---------------- | ------------------------------------------------- |
| Agent framework  | LangGraph + langchain-core + langchain-openai     |
| LLM              | OpenAI gpt-4o-mini (dev) / gpt-4o (prod)          |
| Backend          | FastAPI + Uvicorn                                 |
| Frontend         | Streamlit                                         |
| Persistence      | SQLite (Phase 1–2) → PostgreSQL (Phase 3)         |
| Auth (Splitwise) | OAuth 1.0 HMAC-SHA1 via requests-oauthlib         |
| App security     | python-jose (JWT)                                 |
| HTTP client      | httpx (async) + requests-oauthlib (OAuth signing) |

> Do NOT install `langchain` (monolith) or `langchain-nvidia-ai-endpoints` — they introduce conflicting `langchain-core` version pins that break LangGraph.

---

## Prerequisites

- macOS (Intel or Apple Silicon)
- Python 3.11+ via pyenv
- OpenAI API key — [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- Splitwise OAuth credentials (consumer key/secret + access token/secret) — [secure.splitwise.com/oauth_clients](https://secure.splitwise.com/oauth_clients)

---

## Quick start

### 1. Clone the repo

```bash
git clone https://github.com/yourusername/splitwise-ai-agent.git
cd splitwise-ai-agent
```

### 2. Create and activate virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

> Run `source venv/bin/activate` every time you open a new terminal window.

### 3. Install dependencies

```bash
pip install --upgrade pip

pip install fastapi uvicorn[standard] streamlit \
  langgraph langchain-core langchain-openai openai \
  httpx requests requests-oauthlib \
  pydantic python-jose[cryptography] \
  python-dotenv
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Generate the required keys:

```bash
# Fernet encryption key for Splitwise API key storage
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# JWT secret key
python -c "import secrets; print(secrets.token_hex(32))"
```

Edit `.env` and fill in all values:

```bash
# OpenAI
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini

# Splitwise OAuth 1.0 (HMAC-SHA1)
SPLITWISE_CONSUMER_KEY=your-consumer-key
SPLITWISE_CONSUMER_SECRET=your-consumer-secret
SPLITWISE_ACCESS_TOKEN=your-access-token
SPLITWISE_ACCESS_TOKEN_SECRET=your-access-token-secret
SPLITWISE_BASE_URL=https://secure.splitwise.com/api/v3.0

# App
APP_SECRET_KEY=your-jwt-secret-here
DATABASE_URL=sqlite:///./agent.db
```

### 5. Run the app

Open two terminal tabs, both with the venv activated:

```bash
# Tab 1 — FastAPI backend
uvicorn app.main:app --reload --port 8000

# Tab 2 — Streamlit frontend
streamlit run ui/chat_app.py --server.port 8501
```

- Backend API + auto-docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Chat interface: [http://localhost:8501](http://localhost:8501)

---

## Project structure

```
splitwise-ai-agent/
├── app/
│   ├── main.py              # FastAPI app, route definitions
│   ├── graph.py             # LangGraph StateGraph definition
│   ├── schemas.py           # Pydantic models for all I/O
│   ├── security.py          # Fernet encryption, JWT utils
│   ├── nodes/
│   │   ├── intent.py        # Intent classification node
│   │   ├── expense.py       # Expense tool executor node
│   │   ├── analytics.py     # Analytics agent node (Phase 2)
│   │   └── error.py         # Error handler + retry node
│   └── tools/
│       └── splitwise.py     # Splitwise API tool wrappers
├── ui/
│   └── chat_app.py          # Streamlit chat interface
├── tests/
│   ├── test_nodes.py        # Unit tests per graph node
│   └── test_tools.py        # Splitwise API mock tests
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── requirements.md          # Functional requirements by phase
└── tech-stack.md            # Technology decisions and rationale
```

---

## Agent architecture

```
User message
     │
     ▼
┌──────────────────┐
│ intent_classifier │  ← LLM call: expense / query / analytics / unknown
└────────┬─────────┘
         │
    ┌────▼──────────────────────┐
    │                           │
    ▼                           ▼
expense_node             analytics_node
(create / retrieve        (summarise /
 / balance)                by category)
    │                           │
    ▼                           │
confirm_node  ◄─────────────────┘
(human-in-the-loop — Phase 2)
    │
    ▼
response_formatter
    │
    ▼
  Reply
    │
    └──► error_node (on any exception, 1 auto-retry)
```

Key LangGraph concepts used:

- `StateGraph` with a typed `AgentState` (TypedDict)
- `SqliteSaver` checkpointer for persistent memory across turns
- `interrupt_before=["confirm_node"]` for human-in-the-loop pauses
- Conditional edges for intent-based routing

---

## Roadmap

### Phase 1 — MVP stabilization (Weeks 1–3)

- [x] Swap NVIDIA → OpenAI SDK
- [ ] Replace LangChain AgentExecutor with LangGraph StateGraph
- [ ] Expense creation, retrieval, balance query nodes
- [ ] Streamlit UI wired to FastAPI backend
- [ ] Encrypted Splitwise API key proxy
- [ ] Basic error handling and user feedback

### Phase 2 — Agentic features (Weeks 4–7)

- [ ] Persistent memory via LangGraph SqliteSaver checkpointer
- [ ] Multi-agent graph (expense + analytics agents)
- [ ] Human-in-the-loop confirmation on write operations
- [ ] Group management (list, add/remove members)
- [ ] Pydantic structured output validation + auto-retry

### Phase 3 — Production & scale (Weeks 8–12)

- [ ] Docker Compose setup (FastAPI + Streamlit containers)
- [ ] Deploy to Render or Railway
- [ ] PostgreSQL swap from SQLite
- [ ] Multi-currency support
- [ ] Rate limiting (slowapi) + input sanitisation
- [ ] OpenAI token usage + cost tracking dashboard

---

## Development

### Install dev tools

```bash
pip install black ruff mypy pytest pytest-asyncio
```

### Format and lint

```bash
black .
ruff check .
mypy app/
```

### Run tests

```bash
pytest tests/ -v
```

---

## Security notes

- Never commit `.env` to git — it is listed in `.gitignore`
- Splitwise authentication uses OAuth 1.0 with HMAC-SHA1 signing via `requests-oauthlib`; all four OAuth credentials live only in `.env` and are never stored in the database
- All Splitwise API calls are proxied through the FastAPI backend — the frontend has no direct API access
- Rotate `APP_SECRET_KEY` before any production deployment

---

## Cost estimate

| Component                   | Model            | Estimated cost          |
| --------------------------- | ---------------- | ----------------------- |
| Chat turns (personal use)   | gpt-4o-mini      | ~$0.01–0.05 / day       |
| Hosting (Phase 3)           | Render free tier | $0 (750 hrs/month)      |
| Splitwise API               | —                | Free (developer access) |
| Exchange Rate API (Phase 3) | Free tier        | $0                      |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m 'Add your feature'`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a pull request

---

## License

MIT License — see [LICENSE](LICENSE) for details.
