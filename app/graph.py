from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from app.schemas import AgentState
from app.security import Settings
from app.tools.splitwise import SplitwiseClient, SplitwiseClientInterface
from app.nodes.intent import IntentClassifierNode
from app.nodes.expense import ExpenseExecutorNode
from app.nodes.error import ErrorHandlerNode


_KNOWN_INTENTS = {
    "create_expense",
    "get_expenses",
    "get_expense_details",
    "update_expense",
    "delete_expense",
    "get_balance",
    "get_groups",
    "get_group_details",
    "get_comments",
    "get_currencies",
}


def _route_intent(state: AgentState) -> str:
    if state.get("intent") in _KNOWN_INTENTS:
        return "expense_node"
    return "error_node"


def build_graph(settings: Settings):
    """
    Factory function — wires concrete dependencies into the graph.
    Accepts Settings so callers control configuration (testable, DIP-compliant).
    """
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    client: SplitwiseClientInterface = SplitwiseClient(settings)

    intent_node = IntentClassifierNode(llm)
    expense_node = ExpenseExecutorNode(llm, client)
    error_node = ErrorHandlerNode()

    builder: StateGraph = StateGraph(AgentState)
    builder.add_node("intent_classifier", intent_node)
    builder.add_node("expense_node", expense_node)
    builder.add_node("error_node", error_node)

    builder.set_entry_point("intent_classifier")
    builder.add_conditional_edges(
        "intent_classifier",
        _route_intent,
        {"expense_node": "expense_node", "error_node": "error_node"},
    )
    builder.add_edge("expense_node", END)
    builder.add_edge("error_node", END)

    return builder.compile()
