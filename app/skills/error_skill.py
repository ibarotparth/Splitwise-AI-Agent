"""Help / error message rendering."""
from app.schemas import AgentState

_HELP = (
    "I didn't understand that. Here's what I can do:\n\n"
    "**Expenses**\n"
    "- Add: \"Add $20 for lunch with Alice\" (I'll ask about group + split if needed)\n"
    "- List all: \"Show my recent expenses\"\n"
    "- List for group: \"Show recent expenses of 548 Maple Ave\"\n"
    "- Details: \"Show details of expense 12345\"\n"
    "- Update: \"Change expense 12345 amount to $30\"\n"
    "- Delete: \"Delete expense 12345\"\n\n"
    "**Balances & Groups**\n"
    "- Balances: \"What do I owe John?\"\n"
    "- Groups: \"Show all my groups\" or \"Show details of group Roommates\"\n\n"
    "**Other**\n"
    "- Comments: \"Show comments on expense 12345\"\n"
    "- Currencies: \"What currencies are supported?\""
)


class ErrorSkill:
    def __call__(self, state: AgentState) -> AgentState:
        error = state.get("error")
        if error:
            response = f"Something went wrong: {error}"
        elif state.get("intent") == "unknown":
            response = _HELP
        else:
            response = "I couldn't complete that request. Please try again."
        return {**state, "response": response}
