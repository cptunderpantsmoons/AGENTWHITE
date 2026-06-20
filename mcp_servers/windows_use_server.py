"""
MCP server exposing Windows-Use desktop automation.

Windows-Use (https://github.com/CursorTouch/Windows-Use.git) controls
Windows desktop applications via UI Automation.  Because it depends on
``pywin32`` and the Windows UIA framework, it is only functional on
Windows hosts.  On Linux/macOS the server exposes a single tool that
returns a clear platform-not-supported message.
"""

import asyncio
import os
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from mcp_servers._common import truncate

server = Server("windows_use")

_IS_WINDOWS = sys.platform == "win32"
_agent = None
_initialized = False


def _ensure_init():
    """Lazy-init the Windows-Use agent (Windows only)."""
    global _agent, _initialized
    if _initialized or not _IS_WINDOWS:
        return

    try:
        import windows_use
        from windows_use.agent import Agent
        from windows_use.providers.litellm import ChatLiteLLM
    except ImportError as exc:
        raise RuntimeError(f"Windows-Use is not installed: {exc}")

    model = os.getenv("WINDOWS_USE_MODEL") or os.getenv("DEFAULT_MODEL") or "gpt-4o"
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or None

    llm = ChatLiteLLM(
        model=model,
        api_key=api_key or None,
        base_url=base_url,
        timeout=600.0,
        max_retries=2,
    )

    _agent = Agent(llm=llm, max_steps=30, log_to_console=False, log_to_file=False)
    _initialized = True


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="windows_use_run",
            description=(
                "Run a natural-language Windows desktop automation task using Windows-Use. "
                "Examples: 'open Outlook desktop app and reply to the latest email from Jane', "
                "'open File Explorer and navigate to Downloads', "
                "'open Notepad and type Hello World'. "
                "Only available on Windows hosts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language instruction for the desktop task",
                    },
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "windows_use_run":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    enabled = os.getenv("WINDOWS_USE_ENABLED", "true").lower()
    if enabled in ("false", "0", "no"):
        return [TextContent(type="text", text="Windows-Use is disabled (WINDOWS_USE_ENABLED=false).")]

    if not _IS_WINDOWS:
        return [
            TextContent(
                type="text",
                text=(
                    "Windows-Use is only available on Windows. "
                    f"Current platform: {sys.platform}."
                ),
            )
        ]

    query = arguments.get("query", "").strip()
    if not query:
        return [TextContent(type="text", text="Error: query is required")]

    try:
        _ensure_init()
    except Exception as e:
        return [TextContent(type="text", text=f"Windows-Use failed to initialise: {type(e).__name__}: {e}")]

    if _agent is None:
        return [TextContent(type="text", text="Windows-Use agent is not available.")]

    try:
        if hasattr(_agent, "ainvoke"):
            result = await _agent.ainvoke(query)
        else:
            result = await asyncio.to_thread(_agent.invoke, query)
    except Exception as e:
        return [TextContent(type="text", text=f"Windows-Use task failed: {type(e).__name__}: {e}")]

    if result.is_done and result.content:
        return [TextContent(type="text", text=truncate(result.content))]
    elif result.error:
        return [TextContent(type="text", text=f"Error: {result.error}")]
    return [TextContent(type="text", text="(no response)")]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
