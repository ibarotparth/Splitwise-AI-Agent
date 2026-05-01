# Requirements: Splitwise AI Agent

## Project Overview

A conversational expense management app that wraps the Splitwise API in a LangGraph-powered AI agent. Users interact via natural language — the agent parses intent, calls the appropriate Splitwise tools, handles validation/retries, and replies in plain English.

---

## Functional Requirements

### Phase 1 — MVP Stabilization (Weeks 1–3)

#### Expense Operations

- Create an expense from a natural language command (e.g. "Add $45 for lunch with Mike and Sarah")
  - Parse: amount, description, participants, optional date
  - Confirm parsed values before submitting (human-in-the-loop stub)
- Retrieve recent expenses for the authenticated user
- Query current balances with one or more friends

#### AI Agent (LangGraph)

- Replace previous LangChain agent with a LangGraph `StateGraph`
- Define nodes: `intent_classifier → tool_selector → tool_executor → response_formatter`
- Support multi-turn conversation with follow-up question handling
- Graceful error node: catches API failures and bad parses, retries once, then surfaces a readable message

#### Authentication & Security

- Splitwise authentication via OAuth 1.0 (HMAC-SHA1)
  - OAuth credentials (`CONSUMER_KEY`, `CONSUMER_SECRET`, `ACCESS_TOKEN`, `ACCESS_TOKEN_SECRET`) loaded from `.env`
  - All requests to Splitwise API signed using `requests-oauthlib` with HMAC-SHA1
  - OAuth endpoints: Request Token — `https://secure.splitwise.com/oauth/request_token`, Access Token — `https://secure.splitwise.com/oauth/access_token`
- Proxy all Splitwise calls through FastAPI backend — frontend never touches the Splitwise API directly
- OAuth credentials never logged, never stored in the database

#### Chat Interface

- Streamlit-based chat UI with message history
- Loading indicator while agent is processing
- Error messages surfaced inline (not stack traces)

---

### Phase 2 — Agentic Features (Weeks 4–7)

#### Memory

- Persist conversation state across turns using LangGraph's checkpointer (SQLite backend initially)
- Agent remembers previously mentioned people and groups within a session

#### Multi-Agent Graph

- Expense agent: creation, retrieval, balance queries
- Analytics agent: summarize spending by category, by person, over a date range
- Agents are separate graph nodes; a router node dispatches based on intent

#### Human-in-the-Loop

- Before submitting any write operation (expense creation, settlement), pause the graph and ask for user confirmation
- User can correct details in natural language before re-running the node

#### Group Management

- List groups the user belongs to
- Add or remove members from a group
- Assign expenses to a specific group

#### Validation & Retry

- Structured output validation on LLM tool calls (Pydantic models)
- Auto-retry once on schema mismatch before raising to error node

---

### Phase 3 — Production & Scale (Weeks 8–12)

#### Infrastructure

- Dockerized services: FastAPI backend + Streamlit frontend as separate containers
- Deploy to Render or Railway (free tier sufficient for MVP scale)
- Swap SQLite → PostgreSQL for persistence

#### Extended Features

- Multi-currency support (display in user's preferred currency, convert via exchange rate API)
- LLM provider: OpenAI only (model switchable via env var, e.g. gpt-4o-mini → gpt-4o)
- Reminder agent: scheduled nudges for unsettled balances (via cron or APScheduler)

#### Security Hardening

- Rate limiting on FastAPI routes (slowapi)
- Input sanitisation before passing to LLM
- API key rotation support

#### Observability

- Log token usage per request (OpenAI)
- Cost tracking dashboard (simple Streamlit page)
- Basic health-check endpoint for deployment monitoring

---

## Non-Functional Requirements

| Concern          | Requirement                                                      |
| ---------------- | ---------------------------------------------------------------- |
| Response latency | Agent response < 5s for simple queries on GPT-4o-mini            |
| Security         | No API keys in logs, git, or client-side JS                      |
| Reliability      | Retry logic on transient Splitwise / OpenAI errors               |
| Maintainability  | Each LangGraph node is a pure function, independently testable   |
| Portability      | Runs locally with `docker compose up`; no vendor lock-in for LLM |

---

## Out of Scope (for now)

- Voice input
- Native mobile app
- Integration with non-Splitwise platforms (Venmo, PayPal)
- Real-time push notifications

---

## API Dependencies

| API                         | Purpose                       | Auth                   | Cost                                          |
| --------------------------- | ----------------------------- | ---------------------- | --------------------------------------------- |
| Splitwise REST API          | Expense CRUD, balance queries | API key (free for dev) | Free                                          |
| OpenAI API                  | LLM inference                 | API key                | Pay-per-use (~$0.15/1M tokens on gpt-4o-mini) |
| Exchange Rate API (Phase 3) | Currency conversion           | API key (free tier)    | Free                                          |
