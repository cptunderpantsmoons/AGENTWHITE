"""
MCP server exposing Web-Use browser automation.

Web-Use (https://github.com/CursorTouch/Web-Use.git) is a CDP-powered
browser agent.  This server wraps it as a single high-level tool so the
agent can say things like "log into SharePoint and download the Q4
report" and let Web-Use handle the actual clicking, typing, and
navigation.

NOTE: Web-Use installs into a top-level ``src`` package namespace,
which clashes with the application's own ``src/`` directory.  The fix is
at the very top of this file: we temporarily re-order ``sys.path`` so
that site-packages wins over the repo root while we import Web-Use
modules.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from mcp_servers._common import truncate

server = Server("web_use")

# Lazy-initialized agent instance (type is imported lazily)
_agent: Any | None = None
_initialized: bool = False
_package_ok: bool = True

# Screenshot directory (created on first use)
_SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "data" / "web_use_screenshots"


def _ensure_init() -> Any:
    """Lazy-init the Web-Use agent with an LLM wired from application env."""
    global _agent, _initialized, _package_ok
    if _initialized:
        assert _agent is not None
        return _agent

    # ── sys.path hygiene ───────────────────────────────────────────────
    # Strip repo-root entries (they shadow Web-Use's ``src`` package).
    _repo_root = Path(__file__).resolve().parent.parent
    _cwd = str(Path.cwd())
    original_path = list(sys.path)
    sys.path = [p for p in sys.path if p and p not in ("", ".", _cwd)]
    sys.path = [p for p in sys.path if not p.startswith(str(_repo_root)) or "site-packages" in p]

    try:
        from src.agent import Agent  # type: ignore[import-untyped]
        from src.providers.litellm import ChatLiteLLM  # type: ignore[import-untyped]
    except ImportError as exc:
        # Restore path before returning
        sys.path = original_path
        _package_ok = False
        raise RuntimeError(f"Web-Use is not installed ({exc}). Install: pip install 'git+https://github.com/CursorTouch/Web-Use.git@main'")

    # Restore normal import path for application modules
    sys.path.insert(0, str(_repo_root))

    # Determine provider / model / key from env (same vars the application already uses)
    provider = (os.getenv("WEB_USE_PROVIDER") or os.getenv("LLM_PROVIDER") or "openai").lower()
    model = os.getenv("WEB_USE_MODEL") or os.getenv("DEFAULT_MODEL") or "gpt-4o"
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or None

    # LiteLLM normalises the provider prefix automatically, but being
    # explicit avoids ambiguity when multiple keys are present.
    if provider == "anthropic" and not model.startswith("claude"):
        model = "claude-sonnet-4-6"
        api_key = os.getenv("ANTHROPIC_API_KEY") or api_key
    elif provider == "openai" and not model.startswith("gpt"):
        model = "gpt-4o"
        api_key = os.getenv("OPENAI_API_KEY") or api_key

    llm = ChatLiteLLM(
        model=model,
        api_key=api_key or None,
        base_url=base_url,
        timeout=600.0,
        max_retries=2,
    )

    _agent = Agent(
        llm=llm,
        max_steps=30,
        log_to_console=False,          # keep MCP stdio clean
        log_to_file=False,
    )
    _initialized = True
    return _agent


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="web_use_run",
            description=(
                "Run a natural-language browser automation task using Web-Use. "
                "Examples: 'open SharePoint, navigate to Finance folder, download Q4.xlsx', "
                "'go to outlook.com and check unread emails', "
                "'sign into the admin portal and create a new user'. "
                "The agent controls a real Chromium browser via CDP and returns a text summary."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language instruction for the browser task",
                    },
                    "url": {
                        "type": "string",
                        "description": "Optional starting URL (e.g. https://sharepoint.com)",
                    },
                    "screenshot": {
                        "type": "boolean",
                        "description": "Capture a full-page screenshot when the task finishes",
                        "default": False,
                    },
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "web_use_run":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    enabled = os.getenv("WEB_USE_ENABLED", "true").lower()
    if enabled in ("false", "0", "no"):
        return [TextContent(type="text", text="Web-Use is disabled (WEB_USE_ENABLED=false).")]

    query = arguments.get("query", "").strip()
    if not query:
        return [TextContent(type="text", text="Error: query is required")]

    start_url = arguments.get("url", "").strip()
    screenshot = arguments.get("screenshot", False)

    # Prepend URL to the instruction when given
    task = query
    if start_url:
        task = f"Start at {start_url}. {task}"

    try:
        agent = _ensure_init()
    except Exception as e:
        return [TextContent(type="text", text=f"Web-Use failed to initialise: {type(e).__name__}: {e}")]

    try:
        result = await agent.ainvoke(task)
    except Exception as e:
        return [TextContent(type="text", text=f"Web-Use task failed: {type(e).__name__}: {e}")]

    # Build response text
    lines: list[str] = []
    if result.is_done and result.content:
        lines.append(result.content)
    elif result.error:
        lines.append(f"Error: {result.error}")
    else:
        lines.append("(no response)")

    # Screenshot handling
    if screenshot and result.is_done:
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        shot_path = _SCREENSHOT_DIR / f"{uuid.uuid4().hex[:12]}.png"
        try:
            bs = getattr(agent.browser, "_browser_state", None)
            if bs and getattr(bs, "current_tab", None):
                page = bs.current_tab.page
                await page.screenshot(path=str(shot_path), full_page=True)
                lines.append(f"\nScreenshot saved: {shot_path}")
        except Exception as e:
            lines.append(f"\nScreenshot request failed: {e}")

    return [TextContent(type="text", text=truncate("\n".join(lines)))]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(run())
