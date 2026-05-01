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
    description="LangGraph-powered conversational expense management",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [{"role": m.role, "content": m.content} for m in request.history]
    messages.append({"role": "user", "content": request.message})

    try:
        state = await _graph.ainvoke(
            {
                "messages": messages,
                "intent": None,
                "expense_data": None,
                "response": None,
                "error": None,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    reply = state.get("response") or state.get("error") or "Sorry, I couldn't process that."
    return ChatResponse(reply=reply)
