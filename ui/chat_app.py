import requests
import streamlit as st

API_URL = "http://localhost:8000/chat"

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Splitwise AI Agent",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styling ──────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    .main .block-container { padding-top: 2rem; max-width: 900px; }

    /* Sidebar: dark theme so white text reads well */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    }
    section[data-testid="stSidebar"] * {
        color: #e2e8f0 !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: #334155 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
        color: #ffffff !important;
        font-weight: 600;
    }
    section[data-testid="stSidebar"] button {
        background-color: #334155 !important;
        color: #f1f5f9 !important;
        border: 1px solid #475569 !important;
    }
    section[data-testid="stSidebar"] button:hover {
        background-color: #475569 !important;
        border-color: #64748b !important;
    }

    .feature-card {
        background: #1e293b;
        border-radius: 8px;
        padding: 12px 14px;
        margin-bottom: 10px;
        border-left: 4px solid #1cc29f;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
    }
    .feature-card-title {
        font-weight: 600;
        color: #f1f5f9 !important;
        margin-bottom: 4px;
        font-size: 14px;
    }
    .feature-card-example {
        font-size: 12px;
        color: #94a3b8 !important;
        font-style: italic;
    }
    .badge {
        display: inline-block;
        background: #064e3b;
        color: #6ee7b7 !important;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 11px;
        font-weight: 600;
        margin-bottom: 8px;
    }
    .quick-action button {
        width: 100%;
        text-align: left !important;
        margin-bottom: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ──────────────────────────────────────────────────────────────────

FEATURES = [
    {
        "category": "💰 Expenses",
        "items": [
            ("Add an expense", "Add $20 for lunch with Alice"),
            ("Add to a group", "Add $50 for groceries with Bob in Roommates"),
            ("List recent expenses", "Show my recent expenses"),
            ("View expense details", "Show details of expense 12345"),
            ("Update an expense", "Change expense 12345 amount to $30"),
            ("Delete an expense", "Delete expense 12345"),
        ],
    },
    {
        "category": "⚖️ Balances",
        "items": [
            ("Check balances", "What do I owe John?"),
            ("All balances", "Show all my balances"),
        ],
    },
    {
        "category": "👥 Groups",
        "items": [
            ("List all groups", "Show all my groups"),
            ("Group details", "Show details of group Roommates"),
        ],
    },
    {
        "category": "💬 Other",
        "items": [
            ("Expense comments", "Show comments on expense 12345"),
            ("Supported currencies", "What currencies does Splitwise support?"),
        ],
    },
]


def _quick_send(prompt: str) -> None:
    st.session_state["pending_prompt"] = prompt


with st.sidebar:
    st.markdown("## 💸 Splitwise AI")
    st.markdown('<span class="badge">10 features</span>', unsafe_allow_html=True)
    st.markdown(
        "Your conversational expense assistant — powered by **LangGraph + OpenAI**, "
        "talking to Splitwise via OAuth 1.0."
    )

    st.divider()
    st.markdown("### ✨ What I can do")

    for section in FEATURES:
        with st.expander(section["category"], expanded=(section["category"] == "💰 Expenses")):
            for title, example in section["items"]:
                st.markdown(
                    f'<div class="feature-card">'
                    f'<div class="feature-card-title">{title}</div>'
                    f'<div class="feature-card-example">"{example}"</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if st.button(f"Try: {title}", key=f"try_{title}", use_container_width=True):
                    _quick_send(example)

    st.divider()

    if st.button("🗑️ Clear chat history", use_container_width=True):
        st.session_state.history = []
        st.rerun()

    st.caption(
        "Built with FastAPI · LangGraph · Streamlit\n\n"
        "Backend: `localhost:8000`"
    )

# ── Main chat ────────────────────────────────────────────────────────────────

st.markdown("# 💸 Splitwise AI Agent")
st.caption(
    "Manage your Splitwise expenses through natural conversation. "
    "Try one of the examples in the sidebar or type your own message below."
)

if "history" not in st.session_state:
    st.session_state.history: list[dict] = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None

# Render chat history
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


def _call_backend(message: str) -> str:
    payload = {
        "message": message,
        "history": [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.history[:-1]
        ],
    }
    try:
        resp = requests.post(API_URL, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["reply"]
    except requests.exceptions.ConnectionError:
        return (
            "⚠️ Cannot reach the backend. "
            "Make sure `uvicorn app.main:app --reload` is running."
        )
    except Exception as exc:
        return f"⚠️ Error: {exc}"


def _handle_user_message(prompt: str) -> None:
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            reply = _call_backend(prompt)
        st.markdown(reply)

    st.session_state.history.append({"role": "assistant", "content": reply})


# Handle a queued sidebar quick-action
if st.session_state.pending_prompt:
    queued = st.session_state.pending_prompt
    st.session_state.pending_prompt = None
    _handle_user_message(queued)

# Chat input
if prompt := st.chat_input("Ask me anything about your Splitwise account…"):
    _handle_user_message(prompt)
