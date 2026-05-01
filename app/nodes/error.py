from app.schemas import AgentState

_HELP_TEXT = (
    "I didn't understand that. Here's what I can do:\n\n"
    "**Expenses**\n"
    "- Add: \"Add $20 for lunch with Alice\" (optionally \"in [group name]\")\n"
    "- List recent: \"What are my recent expenses?\"\n"
    "- View one: \"Show details of expense 12345\"\n"
    "- Update: \"Change expense 12345 amount to $30\"\n"
    "- Delete: \"Delete expense 12345\"\n\n"
    "**Balances & Groups**\n"
    "- Balances: \"What do I owe John?\"\n"
    "- All groups: \"Show all my groups\"\n"
    "- Group details: \"Show details of group Roommates\"\n\n"
    "**Other**\n"
    "- Comments: \"Show comments on expense 12345\"\n"
    "- Currencies: \"What currencies are supported?\""
)


class ErrorHandlerNode:
    """Single-responsibility node: produce a clean error or help message."""

    def __call__(self, state: AgentState) -> AgentState:
        error = state.get("error")
        if error:
            response = f"Something went wrong: {error}"
        elif state.get("intent") == "unknown":
            response = _HELP_TEXT
        else:
            response = "I couldn't complete that request. Please try again."
        return {**state, "response": response}
