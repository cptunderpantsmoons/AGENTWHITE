"""Persisted pin store for session-active skills.

Task 6 (Persist Session Skill Pins) replaces the interim in-memory
``src/session_skill_state.py`` store with this JSON-backed persistence
layer. Pins are keyed by session id and survive across server restarts,
browser refreshes, and turn boundaries.

Quality gates covered here:

* Pinning in one session does not affect another session.
* Refreshing the page (re-loading the store) preserves pins.
* Unpinning removes the pin immediately.
* A slash invocation of a different skill does not permanently replace a
  pinned skill — pins are an ordered set, not a single value.

The on-disk format is ``data/session_skills.json``:

    {
      "sess-a": ["planning", "coding"],
      "sess-b": ["review"]
    }

Skill markdown remains an untrusted, user-editable payload — the pin store
only records skill *names*, which the dispatcher later resolves against
the (owner-filtered) skill catalog. Pinning a name that no skill matches
is a no-op at resolution time.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from functools import lru_cache
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_pins_file() -> str:
    """Resolve the on-disk path for ``session_skills.json``.

    Reads ``ODYSSEUS_DATA_DIR`` so the test suite (and any operator
    override) can point the store at an isolated directory.
    """
    data_dir = os.environ.get("ODYSSEUS_DATA_DIR") or os.path.join(
        os.getcwd(), "data"
    )
    return os.path.join(data_dir, "session_skills.json")


class SessionSkillPins:
    """JSON-backed pin store keyed by session id.

    The store is process-shared: a module-level singleton (see
    :func:`default_store`) is reused across requests so writes from one
    request are visible to the next. All mutations are serialized by an
    in-process lock; the on-disk file is written atomically.
    """

    def __init__(self, path: Optional[str] = None):
        self._path = path or _default_pins_file()
        self._lock = threading.Lock()
        self._cache: Optional[Dict[str, List[str]]] = None

    @property
    def path(self) -> str:
        return self._path

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------

    def _load(self) -> Dict[str, List[str]]:
        """Read the on-disk pin file, recovering from corruption.

        Returns an empty dict when the file is missing or unparseable.
        The cache is populated on first access so subsequent reads in the
        same process do not re-hit disk.
        """
        if self._cache is not None:
            return self._cache
        data: Dict[str, List[str]] = {}
        if os.path.exists(self._path):
            try:
                with open(self._path, encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    for sid, names in raw.items():
                        if not isinstance(sid, str) or not sid:
                            continue
                        if isinstance(names, list):
                            cleaned = [
                                str(n) for n in names
                                if isinstance(n, str) and n.strip()
                            ]
                            if cleaned:
                                data[sid] = cleaned
            except (OSError, ValueError) as exc:
                logger.warning(
                    "session_skills.json was corrupt (%s); starting empty", exc
                )
                data = {}
        self._cache = data
        return data

    def _save(self, data: Dict[str, List[str]]) -> None:
        """Atomically persist ``data`` to disk and refresh the cache."""
        try:
            from core.atomic_io import atomic_write_json
            atomic_write_json(self._path, data, indent=2)
        except Exception:
            # Fallback for environments where core.atomic_io is not yet
            # importable (e.g. test bootstrap). Truncate-and-replace is
            # acceptable for the sidecar; the lock still serializes
            # concurrent writes within this process.
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            tmp = f"{self._path}.tmp.{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self._path)
        self._cache = data

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pin_skill(self, session_id: Optional[str], name: Optional[str]) -> bool:
        """Add ``name`` to the pinned set for ``session_id``.

        Returns ``True`` when a new pin was added, ``False`` when it was
        already pinned (idempotent) or the inputs were invalid. Pins are
        appended in insertion order so the dispatcher can preserve the
        order in which the user pinned them.
        """
        sid = (session_id or "").strip()
        skill = (name or "").strip()
        if not sid or not skill:
            return False
        with self._lock:
            data = self._load()
            pins = data.get(sid, [])
            if skill in pins:
                return False
            pins.append(skill)
            data[sid] = pins
            self._save(data)
        return True

    def unpin_skill(self, session_id: Optional[str], name: Optional[str]) -> bool:
        """Remove ``name`` from the pinned set for ``session_id``.

        Returns ``True`` when a pin was removed, ``False`` otherwise.
        """
        sid = (session_id or "").strip()
        skill = (name or "").strip()
        if not sid or not skill:
            return False
        with self._lock:
            data = self._load()
            pins = data.get(sid)
            if not pins or skill not in pins:
                return False
            pins = [p for p in pins if p != skill]
            if pins:
                data[sid] = pins
            else:
                # Drop empty sessions so the file doesn't accumulate
                # no-op keys.
                data.pop(sid, None)
            self._save(data)
        return True

    def list_pinned_skills(self, session_id: Optional[str]) -> List[str]:
        """Return the pinned skill names for ``session_id`` in insertion order."""
        sid = (session_id or "").strip()
        if not sid:
            return []
        # Read under the lock so a concurrent write can't tear the list.
        with self._lock:
            data = self._load()
            return list(data.get(sid, []))

    def clear_session_pins(self, session_id: Optional[str]) -> int:
        """Remove all pins for ``session_id``. Returns the count removed."""
        sid = (session_id or "").strip()
        if not sid:
            return 0
        with self._lock:
            data = self._load()
            pins = data.pop(sid, [])
            if pins:
                self._save(data)
            return len(pins)


# --------------------------------------------------------------------------
# Module-level convenience API + singleton
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def default_store() -> SessionSkillPins:
    """Return the process-wide pin store.

    Cached so all callers share one in-process lock and one read-through
    cache. The cache is cleared by tests (and on env-var changes) via
    ``default_store.cache_clear()`` so a new ``ODYSSEUS_DATA_DIR`` is
    picked up on the next call.
    """
    return SessionSkillPins()


def pin_skill(session_id: Optional[str], name: Optional[str]) -> bool:
    return default_store().pin_skill(session_id, name)


def unpin_skill(session_id: Optional[str], name: Optional[str]) -> bool:
    return default_store().unpin_skill(session_id, name)


def list_pinned_skills(session_id: Optional[str]) -> List[str]:
    return default_store().list_pinned_skills(session_id)


def clear_session_pins(session_id: Optional[str]) -> int:
    return default_store().clear_session_pins(session_id)
