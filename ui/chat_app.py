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

    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    }
    section[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 { color: #ffffff !important; }
    section[data-testid="stSidebar"] hr { border-color: #334155 !important; }
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
    .widget-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #1cc29f;
        border-radius: 8px;
        padding: 16px;
        margin-top: 8px;
        margin-bottom: 8px;
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
            ("Smart add", "Add $20 for lunch with Alice"),
            ("Group split", "Add $156 in 548 Maple Ave with all members"),
            ("Custom split", "Add $100 dinner with Bob and Alice"),
            ("List recent", "Show my recent expenses"),
            ("List by group", "Show recent expenses of 548 Maple Ave"),
            ("View details", "Show details of expense 12345"),
            ("Update", "Change expense 12345 amount to $30"),
            ("Delete", "Delete expense 12345"),
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
            ("List groups", "Show all my groups"),
            ("Group details", "Show details of group Roommates"),
        ],
    },
    {
        "category": "💬 Other",
        "items": [
            ("Comments", "Show comments on expense 12345"),
            ("Currencies", "What currencies does Splitwise support?"),
        ],
    },
]


def _quick_send(prompt: str) -> None:
    st.session_state["pending_prompt"] = prompt


with st.sidebar:
    st.markdown("## 💸 Splitwise AI")
    st.markdown('<span class="badge">smart multi-turn flow</span>', unsafe_allow_html=True)
    st.markdown("Your intelligent expense companion for **Splitwise**.")

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
        st.session_state.pending_state = None
        st.session_state.awaiting = None
        st.rerun()

    st.caption("Built with FastAPI · LangGraph · Streamlit\n\nBackend: `localhost:8000`")

# ── Main chat ────────────────────────────────────────────────────────────────

st.markdown("# 💸 Splitwise AI Agent")
st.caption("Manage Splitwise via natural conversation.")

# Session state
if "history" not in st.session_state:
    st.session_state.history: list[dict] = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None
if "pending_state" not in st.session_state:
    st.session_state.pending_state = None
if "awaiting" not in st.session_state:
    st.session_state.awaiting = None

# Render chat history
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


def _post_to_backend(payload: dict) -> dict:
    try:
        resp = requests.post(API_URL, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {
            "reply": "⚠️ Cannot reach the backend. Is `uvicorn app.main:app --reload` running?",
            "awaiting_input": None,
            "pending": None,
        }
    except Exception as exc:
        return {"reply": f"⚠️ Error: {exc}", "awaiting_input": None, "pending": None}


def _send_message(prompt: str) -> None:
    """User typed a free-text message."""
    st.session_state.history.append({"role": "user", "content": prompt})
    payload = {
        "message": prompt,
        "history": [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.history[:-1]
        ],
        "pending": st.session_state.pending_state,
    }
    _process_response(_post_to_backend(payload))


def _send_widget_response(
    selection: list[str],
    numeric_inputs: dict[str, float] | None = None,
    summary_text: str | None = None,
) -> None:
    """User responded via a widget — send selection + cached pending state."""
    if summary_text:
        st.session_state.history.append({"role": "user", "content": summary_text})
    payload = {
        "message": None,
        "history": [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.history
        ],
        "pending": st.session_state.pending_state,
        "selection": selection,
        "numeric_inputs": numeric_inputs,
    }
    _process_response(_post_to_backend(payload))


def _process_response(response: dict) -> None:
    reply = response.get("reply", "")
    st.session_state.history.append({"role": "assistant", "content": reply})
    st.session_state.pending_state = response.get("pending")
    st.session_state.awaiting = response.get("awaiting_input")
    st.rerun()


def _cancel_flow() -> None:
    """Bail out of any in-progress multi-turn flow (UI-side, no backend call)."""
    st.session_state.history.append(
        {"role": "assistant", "content": "❌ Cancelled — nothing was added to Splitwise."}
    )
    st.session_state.pending_state = None
    st.session_state.awaiting = None
    st.rerun()


# Handle a queued sidebar quick-action
if st.session_state.pending_prompt:
    queued = st.session_state.pending_prompt
    st.session_state.pending_prompt = None
    _send_message(queued)


# ── Render the awaiting-input widget if any ──────────────────────────────────

awaiting = st.session_state.awaiting

if awaiting:
    with st.container():
        st.markdown('<div class="widget-card">', unsafe_allow_html=True)

        widget_type = awaiting["type"]
        options = awaiting.get("options", [])

        if widget_type in ("group_choice", "split_type", "confirmation"):
            # Single-select radio with inline captions (no duplicate list below)
            labels = [opt["label"] for opt in options]
            captions = [opt.get("sublabel") or "" for opt in options]
            ids = [opt["id"] for opt in options]
            default_idx = next((i for i, opt in enumerate(options) if opt.get("selected")), 0)

            picked_label = st.radio(
                label="Choose:",
                options=labels,
                captions=captions,
                index=default_idx,
                key=f"radio_{widget_type}",
                label_visibility="collapsed",
            )
            picked_idx = labels.index(picked_label)
            picked_id = ids[picked_idx]

            cta = "Confirm" if widget_type == "confirmation" else "Continue"
            col_continue, col_cancel = st.columns([3, 1])
            with col_continue:
                if st.button(
                    cta, key=f"submit_{widget_type}", type="primary", use_container_width=True
                ):
                    _send_widget_response(
                        selection=[picked_id],
                        summary_text=f"_(selected: {picked_label})_",
                    )
            with col_cancel:
                if st.button(
                    "Cancel", key=f"cancel_{widget_type}", use_container_width=True
                ):
                    _cancel_flow()

        elif widget_type == "participant_choice":
            # Multi-select checkboxes
            picked_ids: list[str] = []
            picked_labels: list[str] = []
            for opt in options:
                checked = st.checkbox(
                    opt["label"],
                    value=opt.get("selected", False),
                    key=f"chk_{widget_type}_{opt['id']}",
                )
                if checked:
                    picked_ids.append(opt["id"])
                    picked_labels.append(opt["label"])

            col_continue, col_cancel = st.columns([3, 1])
            with col_continue:
                if st.button(
                    "Continue", key=f"submit_{widget_type}", type="primary",
                    use_container_width=True,
                ):
                    if not picked_ids:
                        st.warning("Please pick at least one person.")
                    else:
                        _send_widget_response(
                            selection=picked_ids,
                            summary_text=f"_(selected: {', '.join(picked_labels)})_",
                        )
            with col_cancel:
                if st.button(
                    "Cancel", key=f"cancel_{widget_type}", use_container_width=True
                ):
                    _cancel_flow()

        elif widget_type == "split_details":
            # Per-person numeric input
            total_target = awaiting.get("numeric_total")
            inputs: dict[str, float] = {}
            cols = st.columns(2)
            for i, opt in enumerate(options):
                with cols[i % 2]:
                    inputs[opt["id"]] = st.number_input(
                        opt["label"],
                        min_value=0.0,
                        value=0.0,
                        step=0.01,
                        key=f"num_{widget_type}_{opt['id']}",
                    )
            current_total = sum(inputs.values())

            # Validate: target-based (exact/percent) needs to match within 0.01;
            # shares (no target) just needs to be > 0.
            if total_target is not None:
                delta = current_total - total_target
                is_valid = abs(delta) < 0.01
                color = "#15803d" if is_valid else "#c2410c"
                hint = (
                    "✅ matches target"
                    if is_valid
                    else f"⚠️ off by {delta:+.2f}"
                )
                st.markdown(
                    f"<div style='font-size:13px;margin-top:4px'>"
                    f"Total: <b style='color:{color}'>{current_total:.2f}</b> "
                    f"/ target {total_target:.2f} &nbsp; "
                    f"<span style='color:{color}'>{hint}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                is_valid = current_total > 0
                color = "#15803d" if is_valid else "#c2410c"
                hint = "✅ ready" if is_valid else "⚠️ enter at least one share"
                st.markdown(
                    f"<div style='font-size:13px;margin-top:4px'>"
                    f"Total shares: <b style='color:{color}'>{current_total:.2f}</b> "
                    f"&nbsp; <span style='color:{color}'>{hint}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            col_continue, col_cancel = st.columns([3, 1])
            with col_continue:
                if st.button(
                    "Continue",
                    key=f"submit_{widget_type}",
                    type="primary",
                    disabled=not is_valid,
                    use_container_width=True,
                ):
                    summary = ", ".join(
                        f"{opt['label']}: {inputs[opt['id']]:.2f}" for opt in options
                    )
                    _send_widget_response(
                        selection=list(inputs.keys()),
                        numeric_inputs=inputs,
                        summary_text=f"_(set: {summary})_",
                    )
            with col_cancel:
                if st.button(
                    "Cancel", key=f"cancel_{widget_type}", use_container_width=True
                ):
                    _cancel_flow()

        st.markdown("</div>", unsafe_allow_html=True)


# ── Free-text input (always available) ───────────────────────────────────────

if prompt := st.chat_input("Ask me anything about your Splitwise account…"):
    _send_message(prompt)
