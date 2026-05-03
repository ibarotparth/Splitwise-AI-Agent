"""
Graph factory — wires together intent classifier → router → error handler.

Two-model strategy:
  - classifier_llm  (cheap)   → intent classification + small extractions
  - extractor_llm   (smarter) → expense creation, updates
"""
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from app.schemas import AgentState
from app.security import Settings
from app.tools.splitwise import SplitwiseClient, SplitwiseClientInterface

from app.skills.intent_classifier_skill import IntentClassifierSkill
from app.skills.error_skill import ErrorSkill
from app.skills.expense_create_skill import ExpenseCreateSkill
from app.skills.expense_query_skill import ExpenseQuerySkill
from app.skills.expense_modify_skill import ExpenseModifySkill
from app.skills.balance_skill import BalanceSkill
from app.skills.group_skill import GroupSkill
from app.skills.currency_skill import CurrencySkill
from app.nodes.router import SkillRouter


_KNOWN_INTENTS = {
    "create_expense",
    "get_expenses",
    "get_group_expenses",
    "get_expense_details",
    "update_expense",
    "delete_expense",
    "get_balance",
    "get_groups",
    "get_group_details",
    "get_comments",
    "get_currencies",
}


def _route(state: AgentState) -> str:
    if state.get("intent") in _KNOWN_INTENTS:
        return "router"
    return "error_node"


def build_graph(settings: Settings):
    classifier_llm = ChatOpenAI(
        model=settings.classifier_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    extractor_llm = ChatOpenAI(
        model=settings.extractor_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    client: SplitwiseClientInterface = SplitwiseClient(settings)

    intent_classifier = IntentClassifierSkill(classifier_llm)
    error_skill = ErrorSkill()
    router = SkillRouter(
        [
            ExpenseCreateSkill(extractor_llm, client),
            ExpenseQuerySkill(classifier_llm, client),
            ExpenseModifySkill(extractor_llm, client),
            BalanceSkill(client),
            GroupSkill(classifier_llm, client),
            CurrencySkill(client),
        ]
    )

    builder: StateGraph = StateGraph(AgentState)
    builder.add_node("intent_classifier", intent_classifier)
    builder.add_node("router", router)
    builder.add_node("error_node", error_skill)

    builder.set_entry_point("intent_classifier")
    builder.add_conditional_edges(
        "intent_classifier",
        _route,
        {"router": "router", "error_node": "error_node"},
    )
    builder.add_edge("router", END)
    builder.add_edge("error_node", END)

    return builder.compile()
