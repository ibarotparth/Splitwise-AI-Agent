import logging

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from app.schemas import ChatRequest, ChatResponse
from app.security import Settings
from app.graph import build_graph

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

load_dotenv()

_settings = Settings.from_env()
_graph = build_graph(_settings)

app = FastAPI(
    title="Splitwise AI Agent",
    description="Skill-based LangGraph agent with multi-turn flows",
    version="0.2.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [{"role": m.role, "content": m.content} for m in request.history]
    if request.message:
        messages.append({"role": "user", "content": request.message})

    initial_state: dict = {
        "messages": messages,
        "intent": None,
        "response": None,
        "error": None,
        "awaiting_input": None,
        "pending": request.pending,
        "selection": request.selection,
        "numeric_inputs": request.numeric_inputs,
    }

    try:
        state = await _graph.ainvoke(initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    reply = state.get("response") or state.get("error") or "Sorry, I couldn't process that."
    return ChatResponse(
        reply=reply,
        awaiting_input=state.get("awaiting_input"),
        pending=state.get("pending"),
    )
