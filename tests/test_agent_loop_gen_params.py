"""Focused tests for active-skill generation-parameter overrides.

Active skills may declare ``temperature`` and ``max_tokens`` overrides in
their SKILL.md frontmatter. The dispatcher parses and validates them, then
``stream_agent_loop`` must actually apply them to the LLM call for the
current turn — falling back to the session defaults when no override is
present.

These tests wire only the prompt-building and streaming paths from
``src.agent_loop``; they do not run the full streaming loop and do not need
SQLAlchemy/pydantic_core. Heavy dependencies are stubbed at module scope
before importing agent_loop, with guards so the stub only applies when the
real module has not been pre-imported (preventing cross-file contamination).
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
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _mod
        if "." in _mod_name:
            _parent, _, _child = _mod_name.rpartition(".")
            if _parent in sys.modules:
                setattr(sys.modules[_parent], _child, _mod)

for _mod_name in ("core.database", "core.models", "src.database"):
    if _mod_name not in sys.modules:
        _m = types.ModuleType(_mod_name)
        _m.SessionLocal = MagicMock()
        _m.ModelEndpoint = MagicMock()
        _m.Base = type("Base", (), {})
        sys.modules[_mod_name] = _m

if "src.agent_tools" not in sys.modules:
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

if "src.tool_index" not in sys.modules:
    _tool_index_stub = types.ModuleType("src.tool_index")
    _tool_index_stub.ALWAYS_AVAILABLE = frozenset({"manage_memory", "ask_user", "update_plan"})
    sys.modules["src.tool_index"] = _tool_index_stub

if "src.user_time" not in sys.modules:
    _user_time_stub = types.ModuleType("src.user_time")
    _user_time_stub.current_datetime_context_message = lambda: None
    sys.modules["src.user_time"] = _user_time_stub

if "services.memory.skills" not in sys.modules:
    _skills_stub = types.ModuleType("services.memory.skills")
    _skills_stub.SkillsManager = MagicMock
    sys.modules["services.memory.skills"] = _skills_stub

if "src.integrations" not in sys.modules:
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


def _patch_loop_common(monkeypatch, dispatcher_skills):
    """Patch the agent loop's external dependencies for an isolated stream run."""
    class FakeDispatcher:
        def __init__(self, *args, **kwargs):
            pass

        def resolve_active_skills(self, *args, **kwargs):
            return list(dispatcher_skills)

    monkeypatch.setattr(agent_loop, "SkillDispatcher", FakeDispatcher, raising=False)
    monkeypatch.setattr(agent_loop, "blocked_tools_for_owner", lambda owner: set(), raising=False)
    monkeypatch.setattr(agent_loop, "get_mcp_manager", lambda: None, raising=False)
    monkeypatch.setattr(agent_loop, "estimate_tokens", lambda *a, **k: 10, raising=False)
    monkeypatch.setattr(agent_loop, "strip_tool_blocks", lambda text, skip_fenced=False: text, raising=False)
    monkeypatch.setattr(agent_loop, "parse_tool_blocks", lambda text, skip_fenced=False: [], raising=False)


class TestComputeSkillGenOverrides:
    """Unit tests for the _compute_skill_gen_overrides helper."""

    def test_no_skills_returns_none_for_both(self):
        t, m = agent_loop._compute_skill_gen_overrides([])
        assert t is None
        assert m is None
        t, m = agent_loop._compute_skill_gen_overrides(None)
        assert t is None
        assert m is None

    def test_single_skill_temperature_override(self):
        skills = [ResolvedSkill(name="s1", markdown="", temperature=0.2)]
        t, m = agent_loop._compute_skill_gen_overrides(skills)
        assert t == 0.2
        assert m is None

    def test_single_skill_max_tokens_override(self):
        skills = [ResolvedSkill(name="s1", markdown="", max_tokens=1024)]
        t, m = agent_loop._compute_skill_gen_overrides(skills)
        assert t is None
        assert m == 1024

    def test_highest_priority_temperature_wins(self):
        """When multiple skills declare temperature, the first (highest priority) wins."""
        skills = [
            ResolvedSkill(name="s1", markdown="", temperature=0.2),
            ResolvedSkill(name="s2", markdown="", temperature=0.9),
        ]
        t, m = agent_loop._compute_skill_gen_overrides(skills)
        assert t == 0.2
        assert m is None

    def test_highest_priority_max_tokens_wins(self):
        skills = [
            ResolvedSkill(name="s1", markdown="", max_tokens=512),
            ResolvedSkill(name="s2", markdown="", max_tokens=2048),
        ]
        t, m = agent_loop._compute_skill_gen_overrides(skills)
        assert t is None
        assert m == 512

    def test_temperature_and_max_tokens_from_different_skills(self):
        """Temperature from one skill, max_tokens from another — both apply."""
        skills = [
            ResolvedSkill(name="s1", markdown="", temperature=0.2),
            ResolvedSkill(name="s2", markdown="", max_tokens=1024),
        ]
        t, m = agent_loop._compute_skill_gen_overrides(skills)
        assert t == 0.2
        assert m == 1024

    def test_skills_with_none_values_are_skipped(self):
        """A skill with temperature=None does not block a later skill's override."""
        skills = [
            ResolvedSkill(name="s1", markdown="", temperature=None, max_tokens=None),
            ResolvedSkill(name="s2", markdown="", temperature=0.5, max_tokens=2048),
        ]
        t, m = agent_loop._compute_skill_gen_overrides(skills)
        assert t == 0.5
        assert m == 2048


class TestStreamAgentLoopGenOverrides:
    """stream_agent_loop applies skill temperature/max_tokens overrides to the LLM call."""

    def test_skill_temperature_override_passed_to_stream(self, monkeypatch, user_message):
        """A skill declaring temperature=0.2 produces a 0.2-temperature LLM call."""
        captured = {}

        skills = [ResolvedSkill(name="precise-skill", markdown="", temperature=0.2)]

        async def fake_stream(_candidates, messages, **kwargs):
            captured["temperature"] = kwargs.get("temperature")
            captured["max_tokens"] = kwargs.get("max_tokens")
            captured["messages"] = messages
            yield 'data: {"delta": "ok"}\n\n'
            yield "data: [DONE]\n\n"

        _patch_loop_common(monkeypatch, skills)
        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream, raising=False)

        chunks = _collect(
            agent_loop.stream_agent_loop(
                "http://x/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"bash"},
                # Session defaults — must be overridden by the skill.
                temperature=0.7,
                max_tokens=4096,
            )
        )

        assert chunks, "fake stream was not consumed"
        assert "temperature" in captured, "stream_llm_with_fallback was not called"
        assert captured["temperature"] == 0.2, (
            f"Expected skill override temperature=0.2, got {captured['temperature']!r}"
        )
        # max_tokens has no skill override, so the session default must apply.
        assert captured["max_tokens"] == 4096

    def test_skill_max_tokens_override_passed_to_stream(self, monkeypatch, user_message):
        """A skill declaring max_tokens=512 produces a 512-token LLM call."""
        captured = {}

        skills = [ResolvedSkill(name="short-skill", markdown="", max_tokens=512)]

        async def fake_stream(_candidates, messages, **kwargs):
            captured["temperature"] = kwargs.get("temperature")
            captured["max_tokens"] = kwargs.get("max_tokens")
            captured["messages"] = messages
            yield 'data: {"delta": "ok"}\n\n'
            yield "data: [DONE]\n\n"

        _patch_loop_common(monkeypatch, skills)
        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream, raising=False)

        chunks = _collect(
            agent_loop.stream_agent_loop(
                "http://x/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"bash"},
                temperature=0.7,
                max_tokens=4096,
            )
        )

        assert chunks, "fake stream was not consumed"
        assert "max_tokens" in captured, "stream_llm_with_fallback was not called"
        assert captured["max_tokens"] == 512, (
            f"Expected skill override max_tokens=512, got {captured['max_tokens']!r}"
        )
        # temperature has no skill override, so the session default must apply.
        assert captured["temperature"] == 0.7

    def test_no_skill_uses_session_defaults(self, monkeypatch, user_message):
        """When no active skill declares temperature/max_tokens, session defaults apply."""
        captured = {}

        # No skills resolved — dispatcher returns empty list.
        skills: list = []

        async def fake_stream(_candidates, messages, **kwargs):
            captured["temperature"] = kwargs.get("temperature")
            captured["max_tokens"] = kwargs.get("max_tokens")
            captured["messages"] = messages
            yield 'data: {"delta": "ok"}\n\n'
            yield "data: [DONE]\n\n"

        _patch_loop_common(monkeypatch, skills)
        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream, raising=False)

        chunks = _collect(
            agent_loop.stream_agent_loop(
                "http://x/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"bash"},
                temperature=0.5,
                max_tokens=2048,
            )
        )

        assert chunks, "fake stream was not consumed"
        assert "temperature" in captured, "stream_llm_with_fallback was not called"
        assert captured["temperature"] == 0.5, (
            f"Expected session default temperature=0.5, got {captured['temperature']!r}"
        )
        assert captured["max_tokens"] == 2048, (
            f"Expected session default max_tokens=2048, got {captured['max_tokens']!r}"
        )

    def test_skill_temperature_lower_than_default(self, monkeypatch, user_message):
        """A skill with temperature=0.2 produces a LOWER temperature call than the default.

        This is the headline assertion from the fix brief: a skill with
        temperature=0.2 must produce a lower-temperature call than the
        session default (0.7 here).
        """
        captured = {}

        skills = [ResolvedSkill(name="precise-skill", markdown="", temperature=0.2)]

        async def fake_stream(_candidates, messages, **kwargs):
            captured["temperature"] = kwargs.get("temperature")
            captured["max_tokens"] = kwargs.get("max_tokens")
            yield 'data: {"delta": "ok"}\n\n'
            yield "data: [DONE]\n\n"

        _patch_loop_common(monkeypatch, skills)
        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream, raising=False)

        _collect(
            agent_loop.stream_agent_loop(
                "http://x/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"bash"},
                temperature=0.7,
                max_tokens=4096,
            )
        )

        assert captured["temperature"] is not None
        assert captured["temperature"] < 0.7, (
            f"Skill temperature {captured['temperature']} should be lower than "
            f"the session default 0.7"
        )
        assert captured["temperature"] == 0.2

    def test_override_does_not_persist_to_session(self, monkeypatch, user_message):
        """Skill overrides apply only for the current turn; they don't mutate the caller's args.

        We can't directly observe session state from here, but we CAN verify
        that calling stream_agent_loop with a skill override twice in a row
        produces the same override both times (i.e. the first call didn't
        mutate some module-level default that the second call would inherit).
        """
        skills = [ResolvedSkill(name="precise-skill", markdown="", temperature=0.2)]

        async def fake_stream(_candidates, messages, **kwargs):
            yield 'data: {"delta": "ok"}\n\n'
            yield "data: [DONE]\n\n"

        _patch_loop_common(monkeypatch, skills)
        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", fake_stream, raising=False)

        # Call 1: skill overrides temperature to 0.2 (session default 0.7).
        captured1 = {}
        original_fake = fake_stream

        async def capturing_stream_1(_candidates, messages, **kwargs):
            captured1["temperature"] = kwargs.get("temperature")
            async for chunk in original_fake(_candidates, messages, **kwargs):
                yield chunk

        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", capturing_stream_1, raising=False)
        _collect(
            agent_loop.stream_agent_loop(
                "http://x/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"bash"},
                temperature=0.7,
                max_tokens=4096,
            )
        )
        assert captured1["temperature"] == 0.2

        # Call 2: same skill set — must produce the SAME override, proving
        # no module-level mutation occurred.
        captured2 = {}

        async def capturing_stream_2(_candidates, messages, **kwargs):
            captured2["temperature"] = kwargs.get("temperature")
            async for chunk in original_fake(_candidates, messages, **kwargs):
                yield chunk

        monkeypatch.setattr(agent_loop, "stream_llm_with_fallback", capturing_stream_2, raising=False)
        _collect(
            agent_loop.stream_agent_loop(
                "http://x/v1",
                "m",
                [user_message],
                max_rounds=1,
                relevant_tools={"bash"},
                temperature=0.7,
                max_tokens=4096,
            )
        )
        assert captured2["temperature"] == 0.2, (
            "Second call must produce the same override — the first call must not "
            "have mutated any module-level state. "
            f"Got temperature={captured2['temperature']!r}"
        )
