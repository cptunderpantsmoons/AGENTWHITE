"""Tests for server-side slash skill invocation (POST /api/skills/invoke)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.datastructures import State

from services.memory.skill_format import slugify
from services.memory.skills import SkillsManager
from routes.skills_routes import setup_skills_routes, SkillInvokeRequest
from src import session_skill_pins, session_skill_state


def _write_skill_md(skills_root: Path, *, name: str, owner: str, **fields) -> Path:
    """Drop a SKILL.md on disk with the given frontmatter fields."""
    category = fields.get("category", "general")
    skill_dir = skills_root / slugify(category, fallback="general") / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    triggers = fields.get("triggers", [])
    tools_required = fields.get("tools_required", [])
    tools_disabled = fields.get("tools_disabled", [])

    fmLines = [
        f"name: {name}",
        f"description: {fields.get('description', name)}",
        "version: 1.0.0",
        f"category: {category}",
        "tags: []",
        f"status: {fields.get('status', 'published')}",
        "confidence: 0.8",
        "source: user",
        f"owner: {owner}",
        "created: 2026-01-01T00:00:00Z",
    ]
    if triggers:
        fmLines.append(f"triggers: {triggers}")
    if tools_required:
        fmLines.append(f"tools_required: {tools_required}")
    if tools_disabled:
        fmLines.append(f"tools_disabled: {tools_disabled}")

    md = textwrap.dedent("""\
        ---
        {frontmatter}
        ---

        # When to use
        whenever

        # Procedure
        - run {name}
        """).format(frontmatter="\n".join(fmLines), name=name)

    path = skill_dir / "SKILL.md"
    path.write_text(md, encoding="utf-8")
    return path


def _request(user: str | None = "alice") -> Request:
    class DummyApp:
        state = State()
    scope = {
        "type": "http",
        "app": DummyApp(),
        "state": {"current_user": user} if user is not None else {},
    }
    return Request(scope=scope)


@pytest.fixture(autouse=True)
def _clear_session_state(tmp_path, monkeypatch):
    """Keep session-skill state isolated between tests.

    Task 6 made the pin store JSON-backed, so we point
    ``ODYSSEUS_DATA_DIR`` at a per-test ``data/`` directory and reset the
    process-wide singleton so each test starts from an empty file.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(data_dir))
    session_skill_pins.default_store.cache_clear()
    for sid in ("sess-active", "sess-404", "sess-403", "sess-project", "sess-anon", "sess-auth"):
        session_skill_state.clear_active_skill(sid)
    yield
    for sid in ("sess-active", "sess-404", "sess-403", "sess-project", "sess-anon", "sess-auth"):
        session_skill_state.clear_active_skill(sid)
    session_skill_pins.default_store.cache_clear()


@pytest.mark.asyncio
async def test_invoke_skill_returns_metadata_without_pinning(tmp_path):
    """Slash invocation is ephemeral — it takes precedence over pins for the
    single turn it was invoked on, then it is gone. The /invoke endpoint must
    NOT persist the slash-invoked skill as a pin (Task 6 brief requirement #5:
    "single-turn invocation … for that turn only")."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    _write_skill_md(
        skills_root,
        name="demo-skill",
        owner="alice",
        triggers=["demo", "show demo"],
        tools_required=["bash"],
        tools_disabled=["ask_user"],
    )

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = next(
        route.endpoint for route in router.routes
        if route.path == "/api/skills/invoke" and "POST" in route.methods
    )

    body = SkillInvokeRequest(name="demo-skill", args="do it", session_id="sess-active")
    result = await handler(_request("alice"), body)

    assert result["ok"] is True
    skill = result["skill"]
    assert skill["name"] == "demo-skill"
    assert "# Procedure" in skill["markdown"]
    assert skill["triggers"] == ["demo", "show demo"]
    assert skill["tools_required"] == ["bash"]
    # ask_user is a safety tool and must be stripped even if declared disabled.
    assert skill["tools_disabled"] == []
    # Slash invocation is ephemeral — it must NOT persist as a pin.
    assert session_skill_state.get_active_skills("sess-active") == []
    assert session_skill_pins.list_pinned_skills("sess-active") == []


@pytest.mark.asyncio
async def test_invoke_unknown_skill_returns_404(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = next(
        route.endpoint for route in router.routes
        if route.path == "/api/skills/invoke" and "POST" in route.methods
    )

    body = SkillInvokeRequest(name="missing-skill", args="", session_id="sess-404")
    with pytest.raises(HTTPException) as exc_info:
        await handler(_request("alice"), body)
    assert exc_info.value.status_code == 404
    assert session_skill_state.get_active_skills("sess-404") == []


@pytest.mark.asyncio
async def test_invoke_other_owner_skill_returns_403(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="private-skill", owner="bob")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = next(
        route.endpoint for route in router.routes
        if route.path == "/api/skills/invoke" and "POST" in route.methods
    )

    body = SkillInvokeRequest(name="private-skill", args="", session_id="sess-403")
    with pytest.raises(HTTPException) as exc_info:
        await handler(_request("alice"), body)
    assert exc_info.value.status_code == 403
    assert session_skill_state.get_active_skills("sess-403") == []


@pytest.mark.asyncio
async def test_invoke_project_local_skill_resolves_and_records_use(tmp_path):
    global_root = tmp_path / "global"
    global_root.mkdir(parents=True, exist_ok=True)
    global_sm = SkillsManager(str(global_root))

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(
        project_root / "skills",
        name="local-skill",
        owner="alice",
        triggers=["local"],
        tools_required=["Read"],
    )
    project_sm = SkillsManager(str(project_root))

    router = setup_skills_routes(global_sm, project_sm)
    handler = next(
        route.endpoint for route in router.routes
        if route.path == "/api/skills/invoke" and "POST" in route.methods
    )

    body = SkillInvokeRequest(name="local-skill", args="do it", session_id="sess-project")
    result = await handler(_request("alice"), body)

    assert result["ok"] is True
    assert result["skill"]["name"] == "local-skill"
    assert result["skill"]["triggers"] == ["local"]
    assert result["skill"]["tools_required"] == ["Read"]
    # Slash invocation is ephemeral — it does NOT pin the skill.
    assert session_skill_state.get_active_skills("sess-project") == []

    project_entries = project_sm.load_all()
    assert len(project_entries) == 1
    assert project_entries[0]["uses"] == 1


@pytest.mark.asyncio
async def test_invoke_owned_skill_when_auth_disabled(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="demo-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = next(
        route.endpoint for route in router.routes
        if route.path == "/api/skills/invoke" and "POST" in route.methods
    )

    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "_auth_disabled", lambda: True)

    body = SkillInvokeRequest(name="demo-skill", args="", session_id="sess-anon")
    result = await handler(_request(None), body)
    assert result["ok"] is True
    assert result["skill"]["name"] == "demo-skill"
    # Slash invocation is ephemeral — it does NOT pin the skill.
    assert session_skill_state.get_active_skills("sess-anon") == []


@pytest.mark.asyncio
async def test_invoke_requires_auth_when_enabled(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="demo-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = next(
        route.endpoint for route in router.routes
        if route.path == "/api/skills/invoke" and "POST" in route.methods
    )

    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "_auth_disabled", lambda: False)

    body = SkillInvokeRequest(name="demo-skill", args="", session_id="sess-auth")
    with pytest.raises(HTTPException) as exc_info:
        await handler(_request(None), body)
    assert exc_info.value.status_code == 401
