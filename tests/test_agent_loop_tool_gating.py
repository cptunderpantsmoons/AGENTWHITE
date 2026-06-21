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
# Provide a minimal schema list so the agent loop's schema-filtering path
# (which keys off FUNCTION_TOOL_SCHEMAS) can be exercised end-to-end.
_agent_tools_stub.FUNCTION_TOOL_SCHEMAS = [
    {"function": {"name": "ask_user"}},
    {"function": {"name": "bash"}},
    {"function": {"name": "web_search"}},
]
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


class TestComputeSkillDisabled:
    """Unit tests for the _compute_skill_disabled helper.

    This helper is the single source of truth for what active skills may
    legitimately disable, and is shared by both the prompt gate
    (``_compute_gated_tool_set``) and the runtime gate
    (``stream_agent_loop``'s ``disabled_tools`` set, including guide_only
    mode). Safety-critical tools must be dropped here unless the declaring
    skill is safe AND the owner is admin/single-user.
    """

    def test_non_safe_skill_cannot_disable_ask_user(self, monkeypatch):
        monkeypatch.setattr(
            sys.modules["src.tool_security"],
            "owner_is_admin_or_single_user",
            lambda owner: False,
            raising=False,
        )
        result = agent_loop._compute_skill_disabled(
            [ResolvedSkill(name="s1", markdown="", tools_disabled=["ask_user", "bash"])],
            "user@example.com",
        )
        assert "ask_user" not in result
        assert "bash" in result

    def test_safe_admin_skill_can_disable_ask_user(self, monkeypatch):
        monkeypatch.setattr(
            sys.modules["src.tool_security"],
            "owner_is_admin_or_single_user",
            lambda owner: True,
            raising=False,
        )
        result = agent_loop._compute_skill_disabled(
            [ResolvedSkill(
                name="s1", markdown="", tools_disabled=["ask_user", "bash"], safe=True
            )],
            "admin@example.com",
        )
        assert "ask_user" in result
        assert "bash" in result

    def test_safe_skill_non_admin_owner_cannot_disable_ask_user(self, monkeypatch):
        monkeypatch.setattr(
            sys.modules["src.tool_security"],
            "owner_is_admin_or_single_user",
            lambda owner: False,
            raising=False,
        )
        result = agent_loop._compute_skill_disabled(
            [ResolvedSkill(
                name="s1", markdown="", tools_disabled=["ask_user"], safe=True
            )],
            "user@example.com",
        )
        assert "ask_user" not in result

    def test_no_skills_returns_empty_set(self):
        assert agent_loop._compute_skill_disabled([], None) == set()
        assert agent_loop._compute_skill_disabled(None, None) == set()


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


class TestStreamAgentLoopSafetyCriticalEndToEnd:
    """End-to-end: a non-safe skill cannot disable ask_user at runtime.

    A non-safe skill that declares ``tools_disabled: [ask_user]`` must NOT
    remove ``ask_user`` from the runtime disabled_tools set or the schemas
    sent to the LLM — the gating function preserves it.
    """

    def _run_loop(self, monkeypatch, user_message, skill, owner_is_admin):
        captured = {}

        class FakeDispatcher:
            def __init__(self, *args, **kwargs):
                pass

            def resolve_active_skills(self, *args, **kwargs):
                return [skill]

        async def fake_stream(_candidates, messages, **kwargs):
            captured["tools"] = kwargs.get("tools")
            captured["messages"] = messages
            yield 'data: {"delta": "ok"}\n\n'
            yield "data: [DONE]\n\n"

        monkeypatch.setattr(agent_loop, "SkillDispatcher", FakeDispatcher, raising=False)
        monkeypatch.setattr(agent_loop, "blocked_tools_for_owner", lambda owner: set(), raising=False)
        monkeypatch.setattr(
            sys.modules["src.tool_security"],
            "owner_is_admin_or_single_user",
            lambda owner: owner_is_admin,
            raising=False,
        )
        monkeypatch.setattr(agent_loop, "get_mcp_manager", lambda: None, raising=False)
        monkeypatch.setattr(agent_loop, "estimate_tokens", lambda *a, **k: 10, raising=False)
        monkeypatch.setattr(agent_loop, "strip_tool_blocks", lambda text, skip_fenced=False: text, raising=False)
        monkeypatch.setattr(agent_loop, "parse_tool_blocks", lambda text, skip_fenced=False: [], raising=False)
        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream, raising=False)

        chunks = _collect(
            agent_loop.stream_agent_loop(
                # Use a host that is in _API_HOSTS so the loop picks the native
                # schema-filtering path (otherwise schemas are dropped for
                # local-only MCP-style messages).
                "https://api.openai.com/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"ask_user", "bash"},
                owner="user@example.com",
            )
        )
        return captured, chunks

    def _schema_names(self, tools):
        names = set()
        for t in (tools or []):
            fn = t.get("function") or {}
            if fn.get("name"):
                names.add(fn["name"])
            elif t.get("name"):
                names.add(t["name"])
        return names

    def test_non_safe_skill_does_not_disable_ask_user_at_runtime(self, monkeypatch, user_message):
        """A non-safe skill declaring tools_disabled=[ask_user] preserves ask_user."""
        skill = ResolvedSkill(
            name="unsafe-skill",
            markdown="",
            tools_disabled=["ask_user"],
            safe=False,
        )
        captured, chunks = self._run_loop(monkeypatch, user_message, skill, owner_is_admin=False)

        assert chunks, "fake stream was not consumed"
        assert "tools" in captured, "stream_llm_with_fallback was not called"

        schemas = captured["tools"] or []
        names = self._schema_names(schemas)
        # ask_user must remain in the schemas — it was NOT added to disabled_tools.
        assert "ask_user" in names, (
            f"ask_user was stripped at runtime even though the skill is non-safe; "
            f"schemas={sorted(names)}"
        )

    def test_safe_admin_skill_disables_ask_user_end_to_end(self, monkeypatch, user_message):
        """A safe, admin-owned skill declaring tools_disabled=[ask_user] removes ask_user."""
        skill = ResolvedSkill(
            name="safe-skill",
            markdown="",
            tools_disabled=["ask_user"],
            safe=True,
        )
        captured, chunks = self._run_loop(monkeypatch, user_message, skill, owner_is_admin=True)

        assert chunks, "fake stream was not consumed"
        assert "tools" in captured, "stream_llm_with_fallback was not called"

        schemas = captured["tools"] or []
        names = self._schema_names(schemas)
        # ask_user must be filtered out — the safe+admin path legitimately
        # disables it end-to-end.
        assert "ask_user" not in names, (
            f"ask_user was NOT disabled end-to-end for safe+admin skill; "
            f"schemas={sorted(names)}"
        )
        # Sanity: bash (not in tools_disabled) survives.
        assert "bash" in names
