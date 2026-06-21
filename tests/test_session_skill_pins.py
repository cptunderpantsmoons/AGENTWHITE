"""Tests for the persisted session skill pin store.

Task 6 replaces the interim in-memory ``src/session_skill_state.py`` store
with a JSON-backed pin store keyed by session id. These tests cover the
quality gates from the task brief:

* Pinning in one session does not affect another session.
* Refreshing the page (re-loading the store) preserves pins.
* Unpinning removes the pin immediately.
* A slash invocation of a different skill does not permanently replace a
  pinned skill (the slash skill is additive, not replacing).
* The dispatcher resolves pins before trigger matching and relevance
  fallback (covered by the dispatcher's own test suite — here we only test
  the pin store itself).
"""

from __future__ import annotations

import json
import os

import pytest

from src import session_skill_pins
from src.session_skill_pins import (
    SessionSkillPins,
    clear_session_pins,
    list_pinned_skills,
    pin_skill,
    unpin_skill,
)


@pytest.fixture
def _data_dir(tmp_path, monkeypatch):
    """Point the pin store at a per-test ``data/`` directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("ODYSSEUS_DATA_DIR", str(data_dir))
    # ``SessionSkillPins`` caches the path at construction time, so reset
    # the singleton so it picks up the new env var on next access.
    session_skill_pins.default_store.cache_clear()
    yield data_dir
    session_skill_pins.default_store.cache_clear()


def _pins_file(data_dir) -> str:
    return os.path.join(str(data_dir), "session_skills.json")


# --------------------------------------------------------------------------
# pin_skill / list_pinned_skills
# --------------------------------------------------------------------------


class TestPinSkill:
    def test_pin_adds_skill_to_session(self, _data_dir):
        pin_skill("sess-a", "planning")
        assert list_pinned_skills("sess-a") == ["planning"]

    def test_pin_is_idempotent(self, _data_dir):
        pin_skill("sess-a", "planning")
        pin_skill("sess-a", "planning")
        assert list_pinned_skills("sess-a") == ["planning"]

    def test_pin_does_not_replace_existing_pin(self, _data_dir):
        """A slash invocation of a different skill must not permanently
        replace a pinned skill (Quality Gate #4)."""
        pin_skill("sess-a", "planning")
        pin_skill("sess-a", "coding")
        assert set(list_pinned_skills("sess-a")) == {"planning", "coding"}

    def test_pin_preserves_insertion_order(self, _data_dir):
        pin_skill("sess-a", "first")
        pin_skill("sess-a", "second")
        pin_skill("sess-a", "third")
        assert list_pinned_skills("sess-a") == ["first", "second", "third"]

    def test_pin_none_session_is_noop(self, _data_dir):
        pin_skill(None, "planning")
        pin_skill("", "planning")
        assert list_pinned_skills(None) == []
        assert list_pinned_skills("") == []

    def test_pin_none_or_empty_name_is_noop(self, _data_dir):
        pin_skill("sess-a", None)
        pin_skill("sess-a", "")
        pin_skill("sess-a", "  ")
        assert list_pinned_skills("sess-a") == []


# --------------------------------------------------------------------------
# Cross-session isolation
# --------------------------------------------------------------------------


class TestSessionIsolation:
    def test_pin_in_one_session_does_not_affect_another(self, _data_dir):
        pin_skill("sess-a", "planning")
        pin_skill("sess-b", "coding")
        assert list_pinned_skills("sess-a") == ["planning"]
        assert list_pinned_skills("sess-b") == ["coding"]

    def test_unpin_in_one_session_does_not_affect_another(self, _data_dir):
        pin_skill("sess-a", "planning")
        pin_skill("sess-b", "planning")
        unpin_skill("sess-a", "planning")
        assert list_pinned_skills("sess-a") == []
        assert list_pinned_skills("sess-b") == ["planning"]


# --------------------------------------------------------------------------
# unpin_skill
# --------------------------------------------------------------------------


class TestUnpinSkill:
    def test_unpin_removes_skill_immediately(self, _data_dir):
        pin_skill("sess-a", "planning")
        pin_skill("sess-a", "coding")
        unpin_skill("sess-a", "planning")
        assert list_pinned_skills("sess-a") == ["coding"]

    def test_unpin_unknown_skill_is_noop(self, _data_dir):
        pin_skill("sess-a", "planning")
        unpin_skill("sess-a", "missing")
        assert list_pinned_skills("sess-a") == ["planning"]

    def test_unpin_unknown_session_is_noop(self, _data_dir):
        unpin_skill("missing-session", "planning")
        assert list_pinned_skills("missing-session") == []

    def test_unpin_none_session_is_noop(self, _data_dir):
        unpin_skill(None, "planning")
        unpin_skill("", "planning")


# --------------------------------------------------------------------------
# clear_session_pins
# --------------------------------------------------------------------------


class TestClearSessionPins:
    def test_clear_removes_all_pins_for_session(self, _data_dir):
        pin_skill("sess-a", "planning")
        pin_skill("sess-a", "coding")
        clear_session_pins("sess-a")
        assert list_pinned_skills("sess-a") == []

    def test_clear_does_not_affect_other_sessions(self, _data_dir):
        pin_skill("sess-a", "planning")
        pin_skill("sess-b", "coding")
        clear_session_pins("sess-a")
        assert list_pinned_skills("sess-a") == []
        assert list_pinned_skills("sess-b") == ["coding"]

    def test_clear_unknown_session_is_noop(self, _data_dir):
        clear_session_pins("missing")
        clear_session_pins(None)
        clear_session_pins("")


# --------------------------------------------------------------------------
# Persistence (refresh preserves pins)
# --------------------------------------------------------------------------


class TestPersistence:
    def test_pin_persists_to_disk(self, _data_dir):
        pin_skill("sess-a", "planning")
        assert os.path.exists(_pins_file(_data_dir))
        data = json.loads(open(_pins_file(_data_dir), encoding="utf-8").read())
        assert data["sess-a"] == ["planning"]

    def test_refresh_preserves_pins(self, _data_dir):
        """Quality Gate #2: refreshing the page (re-loading the store)
        preserves pins."""
        pin_skill("sess-a", "planning")
        pin_skill("sess-a", "coding")

        # Drop the in-memory cache so the next call re-reads from disk.
        session_skill_pins.default_store.cache_clear()

        assert set(list_pinned_skills("sess-a")) == {"planning", "coding"}

    def test_new_instance_reads_existing_file(self, _data_dir):
        """A fresh ``SessionSkillPins`` instance reads the same on-disk
        file, simulating a server restart."""
        pin_skill("sess-a", "planning")
        fresh = SessionSkillPins(_pins_file(_data_dir))
        assert fresh.list_pinned_skills("sess-a") == ["planning"]

    def test_corrupt_file_is_recovered(self, _data_dir):
        """A corrupt JSON file must not crash the dispatcher; the store
        starts empty and re-writes on the next pin."""
        with open(_pins_file(_data_dir), "w", encoding="utf-8") as f:
            f.write("{not valid json")
        session_skill_pins.default_store.cache_clear()
        assert list_pinned_skills("sess-a") == []
        # Writing again must succeed and produce a valid file.
        pin_skill("sess-a", "planning")
        data = json.loads(open(_pins_file(_data_dir), encoding="utf-8").read())
        assert data["sess-a"] == ["planning"]


# --------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_pins_from_two_threads_are_all_persisted(self, _data_dir):
        """The store is process-shared; concurrent pins must not lose data."""
        import threading

        def _pin(name: str):
            pin_skill("sess-shared", name)

        threads = [threading.Thread(target=_pin, args=(f"skill-{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        pinned = set(list_pinned_skills("sess-shared"))
        assert pinned == {f"skill-{i}" for i in range(20)}
