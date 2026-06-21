"""Tests for the ``src/session_skill_state.py`` back-compat shim.

Task 6 (Persist Session Skill Pins) replaced the interim in-memory store
with the JSON-backed :mod:`src.session_skill_pins` store. The public
helpers here continue to delegate to it, so callers in
``routes/skills_routes.py`` and ``src/agent_loop.py`` keep working.

The semantics changed from "single active skill" (replacement) to "an
ordered set of pins" (additive) so that a slash invocation of a different
skill does NOT permanently replace a pinned skill (Task 6 Quality Gate #4).
"""

from __future__ import annotations

import pytest

from src import session_skill_state, session_skill_pins


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Pin the store at a per-test ``data/`` directory so tests don't
    leak state into each other (or into the real ``data/``)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(data_dir))
    session_skill_pins.default_store.cache_clear()
    yield
    session_skill_pins.default_store.cache_clear()


@pytest.fixture(autouse=True)
def _cleanup():
    session_skill_state.clear_active_skill("sess-a")
    session_skill_state.clear_active_skill("sess-b")
    yield
    session_skill_state.clear_active_skill("sess-a")
    session_skill_state.clear_active_skill("sess-b")


def test_set_and_get_active_skill():
    assert session_skill_state.get_active_skills("sess-a") == []
    session_skill_state.set_active_skill("sess-a", "planning")
    assert session_skill_state.get_active_skills("sess-a") == ["planning"]


def test_set_active_skill_is_additive_not_replacing():
    """Task 6 Quality Gate #4: a slash invocation of a different skill
    must not permanently replace a pinned skill. The interim store used
    single-skill replacement; the persisted store keeps both pins."""
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_state.set_active_skill("sess-a", "coding")
    assert set(session_skill_state.get_active_skills("sess-a")) == {
        "planning",
        "coding",
    }


def test_active_skills_is_isolated_per_session():
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_state.set_active_skill("sess-b", "coding")
    assert session_skill_state.get_active_skills("sess-a") == ["planning"]
    assert session_skill_state.get_active_skills("sess-b") == ["coding"]


def test_clear_active_skill():
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_state.set_active_skill("sess-a", "coding")
    session_skill_state.clear_active_skill("sess-a")
    assert session_skill_state.get_active_skills("sess-a") == []


def test_clear_active_skill_does_not_affect_other_sessions():
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_state.set_active_skill("sess-b", "coding")
    session_skill_state.clear_active_skill("sess-a")
    assert session_skill_state.get_active_skills("sess-a") == []
    assert session_skill_state.get_active_skills("sess-b") == ["coding"]


def test_none_session_id_is_no_op():
    # Passing a missing session id should not crash and should not store anything.
    session_skill_state.set_active_skill(None, "planning")
    assert session_skill_state.get_active_skills(None) == []


def test_state_persists_across_cache_resets():
    """Quality Gate #2: refreshing (re-reading the store) preserves pins."""
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_pins.default_store.cache_clear()
    assert session_skill_state.get_active_skills("sess-a") == ["planning"]
