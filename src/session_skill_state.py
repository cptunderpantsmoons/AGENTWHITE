"""Back-compat shim for the interim in-memory active-skill store.

Task 6 (Persist Session Skill Pins) replaced the module-level dict with a
JSON-backed pin store at :mod:`src.session_skill_pins`. The public helpers
here remain so callers (``routes/skills_routes.py`` and
``src/agent_loop.py``) do not need to change — they delegate to the
persistent store.

Semantics change vs. the interim store:

* ``set_active_skill`` is now *additive*: a slash invocation of a different
  skill no longer permanently replaces a pinned skill (Task 6 Quality
  Gate #4). Both skills remain pinned until the user unpins them.
* State persists to ``data/session_skills.json`` so it survives server
  restarts and browser refreshes (Task 6 Quality Gate #2).
* Pinning in one session does not affect another (Task 6 Quality Gate #1).
"""

from __future__ import annotations

from typing import List, Optional

from src.session_skill_pins import (
    clear_session_pins as _clear_session_pins,
    list_pinned_skills as _list_pinned_skills,
    pin_skill as _pin_skill,
)


def set_active_skill(session_id: Optional[str], name: str) -> None:
    """Pin ``name`` to ``session_id`` (additive — does not replace).

    A ``None`` or empty ``session_id`` (or ``name``) is a no-op, matching
    the original interim-store contract.
    """
    _pin_skill(session_id, name)


def get_active_skills(session_id: Optional[str]) -> List[str]:
    """Return the pinned skill names for ``session_id`` in insertion order."""
    return _list_pinned_skills(session_id)


def clear_active_skill(session_id: Optional[str]) -> None:
    """Remove every pin for ``session_id``."""
    _clear_session_pins(session_id)
