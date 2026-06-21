"""Tests for the new pin/unpin/list API endpoints.

These cover:
* ``POST /api/skills/pin``
* ``POST /api/skills/unpin``
* ``GET /api/skills/pins``

And the quality gates from the brief:
* Auth required when enabled.
* Pinning a skill not visible to the caller returns 404 (or 403 when the
  skill exists under another owner).
* Pinning in one session does not affect another.
* Unpinning removes the pin immediately.
* Refreshing (re-reading the store) preserves pins.
* Slash invocation of a different skill does not permanently replace a
  pinned skill.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.datastructures import State

from routes.skills_routes import (
    SkillInvokeRequest,
    SkillPinRequest,
    SkillUnpinRequest,
    setup_skills_routes,
)
from services.memory.skill_format import slugify
from services.memory.skills import SkillsManager
from src import session_skill_pins


def _write_skill_md(skills_root: Path, *, name: str, owner: str, **fields) -> Path:
    category = fields.get("category", "general")
    skill_dir = skills_root / slugify(category, fallback="general") / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    triggers = fields.get("triggers", [])

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


@pytest.fixture(autouse=True)
def _isolated_pin_store(tmp_path, monkeypatch):
    """Point the pin store at a per-test ``data/`` directory and clear any
    cached singleton between tests."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(data_dir))
    session_skill_pins.default_store.cache_clear()
    yield
    session_skill_pins.default_store.cache_clear()


# --------------------------------------------------------------------------
# POST /api/skills/pin
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pin_skill_returns_ok(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    result = await handler(
        _request("alice"),
        SkillPinRequest(name="planning", session_id="sess-a"),
    )

    assert result["ok"] is True
    assert result["name"] == "planning"
    assert result["session_id"] == "sess-a"
    assert result["pinned"] is True
    # Persisted to the store.
    assert session_skill_pins.list_pinned_skills("sess-a") == ["planning"]


@pytest.mark.asyncio
async def test_pin_unknown_skill_returns_404(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    with pytest.raises(HTTPException) as exc:
        await handler(
            _request("alice"),
            SkillPinRequest(name="missing", session_id="sess-a"),
        )
    assert exc.value.status_code == 404
    assert session_skill_pins.list_pinned_skills("sess-a") == []


@pytest.mark.asyncio
async def test_pin_other_owner_skill_returns_403(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="private-skill", owner="bob")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    with pytest.raises(HTTPException) as exc:
        await handler(
            _request("alice"),
            SkillPinRequest(name="private-skill", session_id="sess-a"),
        )
    assert exc.value.status_code == 403
    assert session_skill_pins.list_pinned_skills("sess-a") == []


@pytest.mark.asyncio
async def test_pin_requires_auth_when_enabled(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "_auth_disabled", lambda: False)

    with pytest.raises(HTTPException) as exc:
        await handler(
            _request(None),
            SkillPinRequest(name="planning", session_id="sess-a"),
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_pin_anonymous_ok_when_auth_disabled(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "_auth_disabled", lambda: True)

    result = await handler(
        _request(None),
        SkillPinRequest(name="planning", session_id="sess-anon"),
    )
    assert result["ok"] is True
    assert session_skill_pins.list_pinned_skills("sess-anon") == ["planning"]


@pytest.mark.asyncio
async def test_pin_is_idempotent(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    r1 = await handler(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))
    r2 = await handler(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))

    assert r1["added"] is True
    assert r2["added"] is False
    assert session_skill_pins.list_pinned_skills("sess-a") == ["planning"]


@pytest.mark.asyncio
async def test_pin_in_one_session_does_not_affect_another(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")
    _write_skill_md(skills_root, name="coding", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    await handler(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))
    await handler(_request("alice"), SkillPinRequest(name="coding", session_id="sess-b"))

    assert session_skill_pins.list_pinned_skills("sess-a") == ["planning"]
    assert session_skill_pins.list_pinned_skills("sess-b") == ["coding"]


@pytest.mark.asyncio
async def test_pin_supports_multiple_skills_in_one_session(tmp_path):
    """Slash invocation of a different skill must NOT permanently replace
    a pinned skill (Quality Gate #4)."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")
    _write_skill_md(skills_root, name="coding", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    handler = _route_handler(router, "/api/skills/pin", "POST")

    await handler(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))
    await handler(_request("alice"), SkillPinRequest(name="coding", session_id="sess-a"))

    assert set(session_skill_pins.list_pinned_skills("sess-a")) == {"planning", "coding"}


# --------------------------------------------------------------------------
# POST /api/skills/unpin
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unpin_removes_skill_immediately(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")
    _write_skill_md(skills_root, name="coding", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")
    unpin = _route_handler(router, "/api/skills/unpin", "POST")

    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))
    await pin(_request("alice"), SkillPinRequest(name="coding", session_id="sess-a"))

    result = await unpin(
        _request("alice"),
        SkillUnpinRequest(name="planning", session_id="sess-a"),
    )
    assert result["ok"] is True
    assert result["removed"] is True
    assert session_skill_pins.list_pinned_skills("sess-a") == ["coding"]


@pytest.mark.asyncio
async def test_unpin_unknown_skill_returns_ok_with_removed_false(tmp_path):
    """Unpinning a skill that isn't pinned is a no-op (idempotent). The
    skill must still be visible (404 if missing) so unpin can't be used
    as a cross-owner oracle."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")
    _write_skill_md(skills_root, name="other", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")
    unpin = _route_handler(router, "/api/skills/unpin", "POST")

    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))

    result = await unpin(
        _request("alice"),
        SkillUnpinRequest(name="other", session_id="sess-a"),
    )
    assert result["ok"] is True
    assert result["removed"] is False
    assert session_skill_pins.list_pinned_skills("sess-a") == ["planning"]


@pytest.mark.asyncio
async def test_unpin_missing_skill_returns_404(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    unpin = _route_handler(router, "/api/skills/unpin", "POST")

    with pytest.raises(HTTPException) as exc:
        await unpin(
            _request("alice"),
            SkillUnpinRequest(name="missing", session_id="sess-a"),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unpin_does_not_affect_other_sessions(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")
    unpin = _route_handler(router, "/api/skills/unpin", "POST")

    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))
    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-b"))

    await unpin(_request("alice"), SkillUnpinRequest(name="planning", session_id="sess-a"))

    assert session_skill_pins.list_pinned_skills("sess-a") == []
    assert session_skill_pins.list_pinned_skills("sess-b") == ["planning"]


# --------------------------------------------------------------------------
# GET /api/skills/pins
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_pins_returns_pinned_skills(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")
    _write_skill_md(skills_root, name="coding", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")
    list_pins = _route_handler(router, "/api/skills/pins", "GET")

    # No session_id given → empty.
    result = await list_pins(_request("alice"), session_id=None)
    assert result["pins"] == []

    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))
    await pin(_request("alice"), SkillPinRequest(name="coding", session_id="sess-a"))

    result = await list_pins(_request("alice"), session_id="sess-a")
    assert set(result["pins"]) == {"planning", "coding"}
    assert result["session_id"] == "sess-a"
    assert result["count"] == 2


@pytest.mark.asyncio
async def test_list_pins_is_isolated_per_session(tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")
    _write_skill_md(skills_root, name="coding", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")
    list_pins = _route_handler(router, "/api/skills/pins", "GET")

    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))
    await pin(_request("alice"), SkillPinRequest(name="coding", session_id="sess-b"))

    a = await list_pins(_request("alice"), session_id="sess-a")
    b = await list_pins(_request("alice"), session_id="sess-b")
    assert a["pins"] == ["planning"]
    assert b["pins"] == ["coding"]


@pytest.mark.asyncio
async def test_list_pins_requires_auth_when_enabled(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    list_pins = _route_handler(router, "/api/skills/pins", "GET")

    import routes.skills_routes as skills_routes_module
    monkeypatch.setattr(skills_routes_module, "_auth_disabled", lambda: False)

    with pytest.raises(HTTPException) as exc:
        await list_pins(_request(None), session_id="sess-a")
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------
# Refresh preserves pins (Quality Gate #2)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_preserves_pins(tmp_path):
    """Pinning then dropping the in-memory cache (simulating a refresh)
    must still return the pinned skill."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")
    list_pins = _route_handler(router, "/api/skills/pins", "GET")

    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))

    # Drop the in-memory cache so the next call re-reads from disk.
    session_skill_pins.default_store.cache_clear()

    result = await list_pins(_request("alice"), session_id="sess-a")
    assert result["pins"] == ["planning"]


# --------------------------------------------------------------------------
# Slash invocation does not permanently replace a pinned skill (Quality Gate #4)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_invocation_does_not_replace_pinned_skill(tmp_path):
    """If a user has ``planning`` pinned and then invokes ``/coding`` via
    slash for one turn, the ``planning`` pin must survive AND the
    slash-invoked ``coding`` skill must NOT be added to the pin list
    (Task 6 brief requirement #5: single-turn invocation, ephemeral)."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="planning", owner="alice")
    _write_skill_md(skills_root, name="coding", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")
    invoke = _route_handler(router, "/api/skills/invoke", "POST")

    # User pins ``planning``.
    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))

    # User invokes ``/coding`` for one turn.
    await invoke(
        _request("alice"),
        SkillInvokeRequest(name="coding", args="do it", session_id="sess-a"),
    )

    # ``planning`` must still be pinned (slash does not replace).
    pinned = set(session_skill_pins.list_pinned_skills("sess-a"))
    assert "planning" in pinned
    # The slash-invoked skill is ephemeral — it must NOT be persisted as a pin.
    assert "coding" not in pinned
    assert session_skill_pins.list_pinned_skills("sess-a") == ["planning"]


# --------------------------------------------------------------------------
# Dispatcher reads pins before trigger matching (Quality Gate #5)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_resolves_pinned_skill_without_trigger(tmp_path):
    """A pinned skill must be active even when the message has no trigger
    pattern that matches it (Quality Gate #5: dispatcher resolves pins
    before trigger matching)."""
    from src.skill_dispatcher import SkillDispatcher

    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(
        skills_root,
        name="planning",
        owner="alice",
        # No triggers — the only way this skill activates is via a pin
        # or slash invocation.
    )

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    pin = _route_handler(router, "/api/skills/pin", "POST")

    await pin(_request("alice"), SkillPinRequest(name="planning", session_id="sess-a"))

    # Re-read the pin list (as the dispatcher would) and resolve.
    pinned_names = session_skill_pins.list_pinned_skills("sess-a")
    dispatcher = SkillDispatcher(sm)
    results = dispatcher.resolve_active_skills(
        "what's the weather?",  # unrelated message — no trigger match
        owner="alice",
        pinned_names=pinned_names,
    )
    assert any(r.name == "planning" and r.reason == "pinned" for r in results)
