"""
MCP server exposing Operator-Use multi-agent orchestration.

Operator-Use (https://github.com/CursorTouch/Operator-Use.git) is a
personal-assistant framework with built-in browser and desktop
sub-agents.  This server wraps it as a single high-level tool so the
agent can delegate complex multi-step tasks.

The server creates a lightweight Operator Agent, sends the user's task
as a HumanMessage, and returns the agent's text response.
"""

import asyncio
import os
import uuid

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from mcp_servers._common import truncate

server = Server("operator_use")

_agent = None
_initialized = False


def _ensure_init():
    """Lazy-init the Operator-Use agent with an LLM wired from application env."""
    global _agent, _initialized
    if _initialized:
        return

    from operator_use.agent.service import Agent
    from operator_use.providers.litellm import ChatLiteLLM

    model = os.getenv("OPERATOR_USE_MODEL") or os.getenv("DEFAULT_MODEL") or "gpt-4o"
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or None

    llm = ChatLiteLLM(
        model=model,
        api_key=api_key or None,
        base_url=base_url,
        timeout=600.0,
        max_retries=2,
    )

    _agent = Agent(
        llm=llm,
        max_iterations=30,
        log_to_console=False,
        log_to_file=False,
    )
    _initialized = True


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="operator_run_task",
            description=(
                "Delegate a task to the Operator-Use multi-agent orchestrator. "
                "The operator can use browser automation, desktop automation, or simple reasoning "
                "depending on what the task requires.  Good for: "
                "'check my email and calendar and tell me if I have any conflicts', "
                "'go to example.com, extract the pricing table, and paste it into a document', "
                "'open the calculator app and compute 234 * 567'. "
                "The operator runs its own internal agent loop and returns a clean summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language instruction for the operator",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["auto", "browser", "computer"],
                        "description": (
                            "Preferred execution mode. auto = let the operator decide; "
                            "browser = force browser-based; computer = force desktop-based."
                        ),
                        "default": "auto",
                    },
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "operator_run_task":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    enabled = os.getenv("OPERATOR_USE_ENABLED", "true").lower()
    if enabled in ("false", "0", "no"):
        return [TextContent(type="text", text="Operator-Use is disabled (OPERATOR_USE_ENABLED=false).")]

    query = arguments.get("query", "").strip()
    if not query:
        return [TextContent(type="text", text="Error: query is required")]

    mode = arguments.get("mode", "auto").lower()

    try:
        _ensure_init()
    except Exception as e:
        return [TextContent(type="text", text=f"Operator-Use failed to initialise: {type(e).__name__}: {e}")]

    if _agent is None:
        return [TextContent(type="text", text="Operator-Use agent is not available.")]

    # Configure mode (enable/disable browser/computer use)
    if mode == "browser":
        _agent.enable_browser_use()
        _agent.disable_computer_use()
    elif mode == "computer":
        _agent.disable_browser_use()
        _agent.enable_computer_use()
    else:
        _agent.enable_browser_use()
        _agent.enable_computer_use()

    from operator_use.messages import HumanMessage

    # Build a deterministic session id so the operator doesn't create
    # a new persistent session every time.
    _app_id = os.getenv("WL_APP_NAME", "app").lower().replace(" ", "-")
    session_id = f"{_app_id}:{uuid.uuid4().hex[:16]}"
    message = HumanMessage(content=query)

    try:
        result = await _agent.run(message=message, session_id=session_id)
    except Exception as e:
        return [TextContent(type="text", text=f"Operator-Use task failed: {type(e).__name__}: {e}")]

    content = getattr(result, "content", None) or str(result)
    if content:
        return [TextContent(type="text", text=truncate(content))]
    return [TextContent(type="text", text="(no response)")]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
