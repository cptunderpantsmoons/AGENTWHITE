"""Tests for src/session_skill_state.py."""

from __future__ import annotations

import pytest

from src import session_skill_state


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


def test_set_active_skill_replaces_previous():
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_state.set_active_skill("sess-a", "coding")
    assert session_skill_state.get_active_skills("sess-a") == ["coding"]


def test_active_skills_is_isolated_per_session():
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_state.set_active_skill("sess-b", "coding")
    assert session_skill_state.get_active_skills("sess-a") == ["planning"]
    assert session_skill_state.get_active_skills("sess-b") == ["coding"]


def test_clear_active_skill():
    session_skill_state.set_active_skill("sess-a", "planning")
    session_skill_state.clear_active_skill("sess-a")
    assert session_skill_state.get_active_skills("sess-a") == []


def test_none_session_id_is_no_op():
    # Passing a missing session id should not crash and should not store anything.
    session_skill_state.set_active_skill(None, "planning")
    assert session_skill_state.get_active_skills(None) == []
