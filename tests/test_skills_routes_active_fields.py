"""Focused tests for the Task-7 editor fields and the tool-registry endpoint.

These cover the editor UI's backend contract:
* ``SkillAddRequest`` accepts the new active-skill fields and the
  ``/api/skills/add`` route forwards them to ``SkillsManager.add_skill``.
* ``SkillUpdateRequest`` accepts the new fields and the
  ``PUT /api/skills/{skill_id}`` route persists them via
  ``SkillsManager.update_skill``.
* Invalid ``inject_mode`` is rejected (round-trips to the manager's own
  ValueError → HTTPException).
* ``GET /api/skills/tool-registry`` returns a non-empty set that includes
  the core built-in tools (bash, read_file, etc.) so the editor's
  client-side validation has a real allowlist.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.datastructures import State

from routes.skills_routes import (
    SkillAddRequest,
    SkillUpdateRequest,
    setup_skills_routes,
)
from services.memory.skill_format import slugify
from services.memory.skills import SkillsManager


def _write_skill_md(skills_root: Path, *, name: str, owner: str, **fields) -> Path:
    category = fields.get("category", "general")
    skill_dir = skills_root / slugify(category, fallback="general") / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    fm_lines = [
        f"name: {name}",
        f"description: {fields.get('description', name)}",
        "version: 1.0.0",
        f"category: {category}",
        "tags: []",
        "status: draft",
        "confidence: 0.8",
        "source: user",
        f"owner: {owner}",
        "created: 2026-01-01T00:00:00Z",
    ]
    md = textwrap.dedent("""\
        ---
        {frontmatter}
        ---

        # When to use
        test

        # Procedure
        - step 1
        """).format(frontmatter="\n".join(fm_lines), name=name)

    path = skill_dir / "SKILL.md"
    path.write_text(md, encoding="utf-8")
    return path


def _request(user: str | None = "alice") -> Request:
    class DummyApp:
        state = State()

    return Request(scope={
        "type": "http",
        "method": "POST",
        "headers": [],
        "app": DummyApp(),
        "state": {"current_user": user} if user is not None else {},
    })


def _route_handler(router, path: str, method: str):
    return next(
        route.endpoint for route in router.routes
        if route.path == path and method in route.methods
    )


# --------------------------------------------------------------------------
# POST /api/skills/add — accepts the new active-skill fields
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_skill_persists_active_skill_fields(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    result = await add(
        _request("alice"),
        SkillAddRequest(
            name="deploy-helper",
            description="deploy helper",
            triggers=["deploy", "ship it"],
            examples=["deploy the service", "ship the new build"],
            tools_required=["bash", "read_file"],
            tools_disabled=["generate_image"],
            priority=5,
            pinned=True,
            temperature=0.2,
            max_tokens=2048,
            inject_mode="directive",
        ),
    )

    assert result["ok"] is True
    sk = result["skill"]
    assert sk["triggers"] == ["deploy", "ship it"]
    assert sk["examples"] == ["deploy the service", "ship the new build"]
    assert sk["tools_required"] == ["bash", "read_file"]
    assert sk["tools_disabled"] == ["generate_image"]
    assert sk["priority"] == 5
    assert sk["pinned"] is True
    assert sk["temperature"] == 0.2
    assert sk["max_tokens"] == 2048
    assert sk["inject_mode"] == "directive"

    # Re-load from disk and verify the fields round-trip through the
    # frontmatter parser (SkillsManager.load reads from SKILL.md).
    loaded = sm.load(owner="alice")
    match = next(s for s in loaded if s["name"] == "deploy-helper")
    assert match["triggers"] == ["deploy", "ship it"]
    assert match["tools_required"] == ["bash", "read_file"]
    assert match["priority"] == 5
    assert match["pinned"] is True
    assert match["temperature"] == 0.2
    assert match["max_tokens"] == 2048
    assert match["inject_mode"] == "directive"


@pytest.mark.asyncio
async def test_add_skill_rejects_invalid_inject_mode(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    # The pydantic model accepts arbitrary strings for inject_mode (it's
    # typed as str), but SkillsManager.add_skill raises ValueError on an
    # unknown value. The route propagates that as an HTTPException-shaped
    # ValueError — assert the rejection happens at the manager boundary.
    with pytest.raises(ValueError, match="Invalid inject_mode"):
        await add(
            _request("alice"),
            SkillAddRequest(
                name="bad-mode",
                description="bad",
                inject_mode="autopilot",
            ),
        )


# --------------------------------------------------------------------------
# PUT /api/skills/{skill_id} — round-trips the active-skill fields
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_skill_round_trips_active_skill_fields(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="editor-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    update = _route_handler(router, "/api/skills/{skill_id}", "PUT")

    result = await update(
        _request("alice"),
        "editor-skill",
        SkillUpdateRequest(
            triggers=["deploy now"],
            examples=["ship it"],
            tools_required=["bash"],
            tools_disabled=["manage_mcp"],
            priority=3,
            pinned=True,
            temperature=0.4,
            max_tokens=1024,
            inject_mode="directive",
        ),
    )
    assert result == {"ok": True}

    loaded = sm.load(owner="alice")
    match = next(s for s in loaded if s["name"] == "editor-skill")
    assert match["triggers"] == ["deploy now"]
    assert match["examples"] == ["ship it"]
    assert match["tools_required"] == ["bash"]
    assert match["tools_disabled"] == ["manage_mcp"]
    assert match["priority"] == 3
    assert match["pinned"] is True
    assert match["temperature"] == 0.4
    assert match["max_tokens"] == 1024
    assert match["inject_mode"] == "directive"


@pytest.mark.asyncio
async def test_update_skill_rejects_invalid_inject_mode(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="editor-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    update = _route_handler(router, "/api/skills/{skill_id}", "PUT")

    # update_skill raises ValueError inside SkillsManager.update_skill — the
    # route surfaces that as an uncaught ValueError (matching the existing
    # add_skill behaviour). The editor's client-side validation should also
    # block this before the request is sent.
    with pytest.raises(ValueError, match="Invalid inject_mode"):
        await update(
            _request("alice"),
            "editor-skill",
            SkillUpdateRequest(inject_mode="autopilot"),
        )


@pytest.mark.asyncio
async def test_update_skill_clears_optional_fields_with_none(tmp_path):
    """temperature and max_tokens are Optional[int] — setting them back to
    None must clear the field, not silently leave the prior value."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="clearable", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    update = _route_handler(router, "/api/skills/{skill_id}", "PUT")

    # First, set them.
    await update(
        _request("alice"),
        "clearable",
        SkillUpdateRequest(temperature=0.5, max_tokens=512),
    )
    loaded = next(s for s in sm.load(owner="alice") if s["name"] == "clearable")
    assert loaded["temperature"] == 0.5
    assert loaded["max_tokens"] == 512

    # Now clear them by sending explicit None. The route MUST treat the
    # explicit None as "clear this field" — using exclude_none=True drops
    # the None before it reaches SkillsManager, leaving the prior value
    # in place. exclude_unset=True (or an explicit sentinel) preserves the
    # explicit None so SkillsManager.update_skill writes None to disk.
    await update(
        _request("alice"),
        "clearable",
        SkillUpdateRequest(temperature=None, max_tokens=None),
    )
    loaded = next(s for s in sm.load(owner="alice") if s["name"] == "clearable")
    assert loaded["temperature"] is None
    assert loaded["max_tokens"] is None


# --------------------------------------------------------------------------
# Server-side tool-name validation backstop
# --------------------------------------------------------------------------

# A tool name that is genuinely unknown to the agent — guaranteed not to
# appear in known_tool_names() so we don't have to mock the registry.
_UNKNOWN_TOOL = "this_tool_does_not_exist_anywhere_xyzzy_42"


@pytest.mark.asyncio
async def test_update_skill_rejects_unknown_tool_required(tmp_path):
    """Server-side backstop: PUT with an unknown name in tools_required
    returns HTTP 400 even if the client-side validator was bypassed."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="gate-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    update = _route_handler(router, "/api/skills/{skill_id}", "PUT")

    with pytest.raises(HTTPException) as exc:
        await update(
            _request("alice"),
            "gate-skill",
            SkillUpdateRequest(tools_required=[_UNKNOWN_TOOL]),
        )
    assert exc.value.status_code == 400
    assert _UNKNOWN_TOOL in str(exc.value.detail)


@pytest.mark.asyncio
async def test_update_skill_rejects_unknown_tool_disabled(tmp_path):
    """Server-side backstop: PUT with an unknown name in tools_disabled
    returns HTTP 400."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="gate-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    update = _route_handler(router, "/api/skills/{skill_id}", "PUT")

    with pytest.raises(HTTPException) as exc:
        await update(
            _request("alice"),
            "gate-skill",
            SkillUpdateRequest(tools_disabled=[_UNKNOWN_TOOL]),
        )
    assert exc.value.status_code == 400
    assert _UNKNOWN_TOOL in str(exc.value.detail)


@pytest.mark.asyncio
async def test_update_skill_accepts_known_tool_names(tmp_path):
    """Sanity: PUT with known tool names does NOT raise."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="gate-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    update = _route_handler(router, "/api/skills/{skill_id}", "PUT")

    result = await update(
        _request("alice"),
        "gate-skill",
        SkillUpdateRequest(tools_required=["bash"], tools_disabled=["read_file"]),
    )
    assert result == {"ok": True}
    loaded = next(s for s in sm.load(owner="alice") if s["name"] == "gate-skill")
    assert loaded["tools_required"] == ["bash"]
    assert loaded["tools_disabled"] == ["read_file"]


@pytest.mark.asyncio
async def test_add_skill_rejects_unknown_tool_required(tmp_path):
    """Server-side backstop: POST /add with an unknown name in
    tools_required returns HTTP 400."""
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    with pytest.raises(HTTPException) as exc:
        await add(
            _request("alice"),
            SkillAddRequest(
                name="bad-tool",
                description="bad",
                tools_required=[_UNKNOWN_TOOL],
            ),
        )
    assert exc.value.status_code == 400
    assert _UNKNOWN_TOOL in str(exc.value.detail)


@pytest.mark.asyncio
async def test_add_skill_rejects_unknown_tool_disabled(tmp_path):
    """Server-side backstop: POST /add with an unknown name in
    tools_disabled returns HTTP 400."""
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    with pytest.raises(HTTPException) as exc:
        await add(
            _request("alice"),
            SkillAddRequest(
                name="bad-tool",
                description="bad",
                tools_disabled=[_UNKNOWN_TOOL],
            ),
        )
    assert exc.value.status_code == 400
    assert _UNKNOWN_TOOL in str(exc.value.detail)


# --------------------------------------------------------------------------
# GET /api/skills/tool-registry
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_registry_returns_known_tools(tmp_path):
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    list_tools = _route_handler(router, "/api/skills/tool-registry", "GET")

    result = await list_tools(_request("alice"))
    assert result["ok"] is True
    assert isinstance(result["tools"], list)
    assert result["count"] == len(result["tools"])
    # Core tools the editor expects to validate against.
    for expected in ("bash", "read_file", "python", "web_search", "web_fetch"):
        assert expected in result["tools"], f"missing core tool: {expected}"


@pytest.mark.asyncio
async def test_tool_registry_requires_auth_when_enabled(monkeypatch, tmp_path):
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    list_tools = _route_handler(router, "/api/skills/tool-registry", "GET")

    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "_auth_disabled", lambda: False)

    with pytest.raises(HTTPException) as exc:
        await list_tools(_request(None))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_tool_registry_anonymous_ok_when_auth_disabled(monkeypatch, tmp_path):
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    list_tools = _route_handler(router, "/api/skills/tool-registry", "GET")

    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "_auth_disabled", lambda: True)

    result = await list_tools(_request(None))
    assert result["ok"] is True
    assert "bash" in result["tools"]


# --------------------------------------------------------------------------
# POST /api/skills/{skill_id}/markdown — server-side tool-name backstop
# --------------------------------------------------------------------------


class _MarkdownRequest:
    """Minimal stand-in for a Starlette Request carrying a JSON body.

    The markdown route reads ``request.headers`` and calls
    ``await request.json()``; we mock both. The owner is injected via a
    monkeypatched ``get_current_user`` (see the test below).
    """

    def __init__(self, markdown: str):
        self._body = {"markdown": markdown}

    @property
    def headers(self):
        return {"content-type": "application/json"}

    async def json(self):
        return self._body


@pytest.mark.asyncio
async def test_save_skill_markdown_rejects_unknown_tool(monkeypatch, tmp_path):
    """Server-side backstop: POST /{skill_id}/markdown with a frontmatter
    tools_required list containing an unknown name must return HTTP 400
    before the skill is persisted."""
    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "get_current_user", lambda request: "alice")

    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="md-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    save_md = _route_handler(router, "/api/skills/{skill_id}/markdown", "POST")

    bad_md = textwrap.dedent("""\
        ---
        name: md-skill
        description: test
        tools_required: [bash, this_tool_does_not_exist_anywhere_xyzzy_42]
        ---

        # Procedure
        - step
        """)
    with pytest.raises(HTTPException) as exc:
        await save_md(_MarkdownRequest(bad_md), "md-skill")
    assert exc.value.status_code == 400
    assert "this_tool_does_not_exist_anywhere_xyzzy_42" in str(exc.value.detail)
    # Verify nothing was written: the skill on disk still has no
    # tools_required frontmatter key.
    loaded = next(s for s in sm.load(owner="alice") if s["name"] == "md-skill")
    assert loaded.get("tools_required") in (None, [])
