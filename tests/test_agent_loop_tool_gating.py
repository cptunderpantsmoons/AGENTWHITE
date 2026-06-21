"""Focused tests for active-skill tool gating.

These tests wire only the prompt-building and gating paths from src.agent_loop;
they do not run the full streaming loop and do not need SQLAlchemy/pydantic_core.
Heavy dependencies are stubbed at module scope before importing agent_loop.
"""

import sys
import os
import types
import tempfile
from unittest.mock import MagicMock

# Pre-stub heavy dependencies before importing agent_loop.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_sqlalchemy = types.ModuleType("sqlalchemy")
_sqlalchemy.__path__ = []
_SQLA_MODS = {
    "sqlalchemy": _sqlalchemy,
    "sqlalchemy.engine": types.ModuleType("sqlalchemy.engine"),
    "sqlalchemy.ext": types.ModuleType("sqlalchemy.ext"),
    "sqlalchemy.ext.declarative": types.ModuleType("sqlalchemy.ext.declarative"),
    "sqlalchemy.ext.hybrid": types.ModuleType("sqlalchemy.ext.hybrid"),
    "sqlalchemy.orm": types.ModuleType("sqlalchemy.orm"),
    "sqlalchemy.sql": types.ModuleType("sqlalchemy.sql"),
    "sqlalchemy.sql.expression": types.ModuleType("sqlalchemy.sql.expression"),
    "sqlalchemy.types": types.ModuleType("sqlalchemy.types"),
}
for _mod_name, _mod in _SQLA_MODS.items():
    sys.modules[_mod_name] = _mod
    if "." in _mod_name:
        _parent, _, _child = _mod_name.rpartition(".")
        setattr(sys.modules[_parent], _child, _mod)

for _mod_name in ("core.database", "core.models", "src.database"):
    _m = types.ModuleType(_mod_name)
    _m.SessionLocal = MagicMock()
    _m.ModelEndpoint = MagicMock()
    _m.Base = type("Base", (), {})
    sys.modules[_mod_name] = _m

_agent_tools_stub = MagicMock()
_agent_tools_stub.MAX_AGENT_ROUNDS = 5
_agent_tools_stub.TOOL_TAGS = set()
_agent_tools_stub.FUNCTION_TOOL_SCHEMAS = []
sys.modules["src.agent_tools"] = _agent_tools_stub

_tool_index_stub = types.ModuleType("src.tool_index")
_tool_index_stub.ALWAYS_AVAILABLE = frozenset({"manage_memory", "ask_user", "update_plan"})
sys.modules["src.tool_index"] = _tool_index_stub

_user_time_stub = types.ModuleType("src.user_time")
_user_time_stub.current_datetime_context_message = lambda: None
sys.modules["src.user_time"] = _user_time_stub

_skills_stub = types.ModuleType("services.memory.skills")
_skills_stub.SkillsManager = MagicMock
sys.modules["services.memory.skills"] = _skills_stub

_integrations_stub = types.ModuleType("src.integrations")
_integrations_stub.get_integrations_prompt = lambda: ""
sys.modules["src.integrations"] = _integrations_stub

# Use a temp directory for the default data dir so tests never touch
# the real data directory.
import src.constants as _constants  # noqa: E402

_constants.DATA_DIR = tempfile.mkdtemp()

import src.agent_loop as agent_loop  # noqa: E402
from src.skill_dispatcher import ResolvedSkill  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_prompt_cache(monkeypatch):
    """Reset the module-level prompt cache before each test."""
    agent_loop._cached_base_prompt = None  # type: ignore[attr-defined]
    agent_loop._cached_base_prompt_key = None  # type: ignore[attr-defined]
    monkeypatch.setattr(agent_loop, "get_setting", lambda key, default=None: default, raising=False)


@pytest.fixture
def user_message():
    return {"role": "user", "content": "do the thing"}


def _collect(gen):
    import asyncio

    async def _run():
        return [c async for c in gen]

    return asyncio.run(_run())


def _system_text(messages):
    return "\n".join(m.get("content", "") or "" for m in messages if m.get("role") == "system")


class TestComputeGatedToolSet:
    """Unit tests for _compute_gated_tool_set."""

    def test_returns_none_when_no_relevant_tools(self):
        assert agent_loop._compute_gated_tool_set(None, [], None) is None

    def test_preserves_always_available_by_default(self, monkeypatch):
        monkeypatch.setattr(
            agent_loop, "blocked_tools_for_owner", lambda owner: set(), raising=False
        )
        result = agent_loop._compute_gated_tool_set(set(), [], None)
        assert result is not None
        assert sys.modules["src.tool_index"].ALWAYS_AVAILABLE <= result

    def test_required_tools_are_added(self):
        result = agent_loop._compute_gated_tool_set(
            {"bash"},
            [ResolvedSkill(name="s1", markdown="", tools_required=["web_search"])],
            None,
        )
        assert "bash" in result
        assert "web_search" in result

    def test_disabled_tools_are_removed(self):
        result = agent_loop._compute_gated_tool_set(
            {"bash", "web_search"},
            [ResolvedSkill(name="s1", markdown="", tools_disabled=["bash"])],
            None,
        )
        assert "web_search" in result
        assert "bash" not in result

    def test_disabled_wins_over_required(self):
        result = agent_loop._compute_gated_tool_set(
            set(),
            [
                ResolvedSkill(name="s1", markdown="", tools_required=["bash"]),
                ResolvedSkill(name="s2", markdown="", tools_disabled=["bash"]),
            ],
            None,
        )
        assert "bash" not in result

    def test_ask_user_cannot_be_disabled_by_non_safe_skill(self, monkeypatch, caplog):
        monkeypatch.setattr(
            sys.modules["src.tool_security"],
            "owner_is_admin_or_single_user",
            lambda owner: False,
            raising=False,
        )
        result = agent_loop._compute_gated_tool_set(
            set(),
            [ResolvedSkill(name="s1", markdown="", tools_disabled=["ask_user"])],
            "user@example.com",
        )
        assert result is not None
        assert "ask_user" in result
        assert any("safety-critical" in rec.message for rec in caplog.records)

    def test_ask_user_can_be_disabled_by_safe_admin_skill(self, monkeypatch):
        monkeypatch.setattr(
            sys.modules["src.tool_security"],
            "owner_is_admin_or_single_user",
            lambda owner: True,
            raising=False,
        )
        result = agent_loop._compute_gated_tool_set(
            set(),
            [ResolvedSkill(name="s1", markdown="", tools_disabled=["ask_user"], safe=True)],
            "admin@example.com",
        )
        assert result is not None
        assert "ask_user" not in result

    def test_required_tools_outside_privilege_set_are_dropped(self, monkeypatch):
        monkeypatch.setattr(
            agent_loop, "blocked_tools_for_owner", lambda owner: {"bash"}, raising=False
        )
        result = agent_loop._compute_gated_tool_set(
            set(),
            [ResolvedSkill(name="s1", markdown="", tools_required=["bash", "web_search"])],
            "user@example.com",
        )
        assert "bash" not in result
        assert "web_search" in result

    def test_always_available_preserved_unless_explicitly_disabled(self):
        result = agent_loop._compute_gated_tool_set(
            {"bash"},
            [ResolvedSkill(name="s1", markdown="", tools_disabled=["manage_memory"])],
            None,
        )
        assert "bash" in result
        assert "manage_memory" not in result
        assert "ask_user" in result
        assert "update_plan" in result

    def test_always_available_filtered_by_owner_privilege(self, monkeypatch):
        monkeypatch.setattr(
            agent_loop, "blocked_tools_for_owner", lambda owner: {"manage_memory"}, raising=False
        )
        result = agent_loop._compute_gated_tool_set(
            set(),
            [],
            "user@example.com",
        )
        assert "manage_memory" not in result
        assert "ask_user" in result
        assert "update_plan" in result


class TestToolGatingInPrompt:
    """Gated tool sets are reflected in the system prompt."""

    def test_disabled_tool_excluded_from_prompt(self, user_message):
        gated = agent_loop._compute_gated_tool_set(
            {"bash", "web_search"},
            [ResolvedSkill(name="s1", markdown="", tools_disabled=["bash"])],
            None,
        )
        merged, _ = agent_loop._build_system_prompt(
            [user_message],
            model="m",
            active_document=None,
            mcp_mgr=None,
            relevant_tools=gated,
            compact=True,
            suppress_local_context=True,
        )
        system = _system_text(merged)
        assert "bash" not in system
        assert "web_search" in system

    def test_disabled_bash_in_prompt(self, user_message):
        gated = {"bash"}
        merged, _ = agent_loop._build_system_prompt(
            [user_message],
            model="m",
            active_document=None,
            mcp_mgr=None,
            relevant_tools=gated,
            compact=True,
            suppress_local_context=True,
            disabled_tools={"bash"},
        )
        system = _system_text(merged)
        assert "bash" not in system


class TestStreamAgentLoopToolGating:
    """stream_agent_loop computes the gated tool set before prompt building."""

    def test_required_tool_added_by_active_skill(self, monkeypatch, user_message):
        captured = {}

        class FakeDispatcher:
            def __init__(self, *args, **kwargs):
                pass

            def resolve_active_skills(self, *args, **kwargs):
                return [ResolvedSkill(name="search-skill", markdown="", tools_required=["web_search"])]

        async def fake_stream(_candidates, messages, **kwargs):
            captured["tools"] = kwargs.get("tools")
            captured["messages"] = messages
            yield 'data: {"delta": "ok"}\n\n'
            yield "data: [DONE]\n\n"

        monkeypatch.setattr(agent_loop, "SkillDispatcher", FakeDispatcher, raising=False)
        monkeypatch.setattr(agent_loop, "blocked_tools_for_owner", lambda owner: set(), raising=False)
        monkeypatch.setattr(agent_loop, "get_mcp_manager", lambda: None, raising=False)
        monkeypatch.setattr(agent_loop, "estimate_tokens", lambda *a, **k: 10, raising=False)
        monkeypatch.setattr(agent_loop, "strip_tool_blocks", lambda text, skip_fenced=False: text, raising=False)
        monkeypatch.setattr(agent_loop, "parse_tool_blocks", lambda text, skip_fenced=False: [], raising=False)
        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream, raising=False)

        chunks = _collect(
            agent_loop.stream_agent_loop(
                "http://x/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"bash"},
            )
        )

        assert chunks, "fake stream was not consumed"
        assert "tools" in captured, "stream_llm_with_fallback was not called"
        # Empty schemas are expected due to stubbing; validate via the system prompt instead.
        system_text = "\n".join(
            m.get("content", "") or ""
            for m in captured.get("messages", [])
            if m.get("role") == "system"
        )
        assert "web_search" in system_text
