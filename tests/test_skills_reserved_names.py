"""Reserved-sentinel skill name rejection (Task 8, security requirement #4).

Skill names double as agent slash commands (``/<skill-name>``), as on-disk
directory names under ``data/skills/``, and as owner-attribution keys in
usage sidecars. A skill named ``internal-tool`` would let a user-authored
skill masquerade as the in-process tool loopback user (which the auth layer
treats as admin); ``api`` collides with the bearer-token owner attribution
sentinel; ``admin`` would shadow the privileged default admin account in
owner-keyed lookups; ``demo``/``system`` round out the synthetic-owner set
the rest of the codebase already special-cases.

These tests pin the invariant: POST /api/skills/add and PUT /api/skills/{id}
(rename path) must reject any of the five reserved sentinels with HTTP 400.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.datastructures import State

from routes.skills_routes import (
    RESERVED_SKILL_NAMES,
    SkillAddRequest,
    SkillUpdateRequest,
    setup_skills_routes,
)
from services.memory.skill_format import slugify
from services.memory.skills import SkillsManager


def _write_skill_md(skills_root: Path, *, name: str, owner: str) -> Path:
    category = "general"
    skill_dir = skills_root / slugify(category, fallback="general") / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = [
        f"name: {name}",
        f"description: {name}",
        "version: 1.0.0",
        f"category: {category}",
        "tags: []",
        "status: published",
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
        whenever

        # Procedure
        - run {name}
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


def test_reserved_skill_names_set_is_complete():
    """The reserved set must include exactly the five sentinels the Task 8
    brief names: internal-tool, api, demo, system, admin."""
    assert RESERVED_SKILL_NAMES == frozenset({
        "internal-tool", "api", "demo", "system", "admin",
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("reserved", sorted(RESERVED_SKILL_NAMES))
async def test_add_skill_rejects_reserved_sentinel_name(tmp_path, reserved):
    """POST /api/skills/add with name=<reserved> returns HTTP 400 before the
    skill reaches SkillsManager. A collision with a synthetic-owner sentinel
    would let a user-authored skill masquerade as the in-process tool
    loopback (admin-equivalent) or shadow the admin account."""
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    with pytest.raises(HTTPException) as exc:
        await add(
            _request("alice"),
            SkillAddRequest(name=reserved, description="bad"),
        )
    assert exc.value.status_code == 400
    assert "reserved" in str(exc.value.detail).lower()
    # Sanity: nothing was persisted.
    assert sm.load_all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reserved", sorted(RESERVED_SKILL_NAMES))
async def test_add_skill_rejects_reserved_sentinel_case_insensitive(tmp_path, reserved):
    """A user who sends ``name="System"`` or ``name="INTERNAL-TOOL"`` must
    also be rejected — slugify lowercases but the route check must run
    before the slugify step so a mixed-case variant of a sentinel can't
    slip through."""
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    with pytest.raises(HTTPException) as exc:
        await add(
            _request("alice"),
            SkillAddRequest(name=reserved.upper(), description="bad"),
        )
    assert exc.value.status_code == 400
    assert sm.load_all() == []


@pytest.mark.asyncio
async def test_update_skill_rejects_rename_into_reserved_sentinel(tmp_path):
    """PUT /api/skills/{skill_id} with body.name=<reserved> must return HTTP
    400. The PUT path allows renaming (SkillsManager.update_skill moves the
    directory), so a rename into a sentinel name would create the same
    collision as the add path."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)
    _write_skill_md(skills_root, name="ordinary-skill", owner="alice")

    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    update = _route_handler(router, "/api/skills/{skill_id}", "PUT")

    with pytest.raises(HTTPException) as exc:
        await update(
            _request("alice"),
            "ordinary-skill",
            SkillUpdateRequest(name="internal-tool"),
        )
    assert exc.value.status_code == 400
    assert "reserved" in str(exc.value.detail).lower()
    # Sanity: the original skill is unchanged on disk.
    loaded = next(s for s in sm.load(owner="alice") if s["name"] == "ordinary-skill")
    assert loaded["name"] == "ordinary-skill"


@pytest.mark.asyncio
async def test_add_skill_accepts_non_reserved_name(tmp_path):
    """Sanity: a normal name that does NOT collide with a sentinel is still
    accepted. This guards against an over-broad check that rejects every
    name."""
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    result = await add(
        _request("alice"),
        SkillAddRequest(name="deploy-helper", description="ok"),
    )
    assert result["ok"] is True
    assert result["skill"]["name"] == "deploy-helper"


@pytest.mark.asyncio
async def test_add_skill_rejects_admin_specifically(tmp_path):
    """``admin`` is reserved because the auth layer treats it as the
    privileged default account name; a skill named ``admin`` would shadow
    it in owner-keyed lookups (e.g. usage sidecar keys, owner-filtered
    skill listings). Pin this case explicitly so the set is not silently
    narrowed later."""
    sm = SkillsManager(str(tmp_path))
    router = setup_skills_routes(sm)
    add = _route_handler(router, "/api/skills/add", "POST")

    with pytest.raises(HTTPException) as exc:
        await add(
            _request("alice"),
            SkillAddRequest(name="admin", description="impersonator"),
        )
    assert exc.value.status_code == 400
    assert "admin" in str(exc.value.detail).lower()
    assert sm.load_all() == []
