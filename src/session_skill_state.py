"""Interim in-memory storage for the active slash skill per session.

Task 3 (Active Skills) needs a minimal way to remember "the active slash
skill for this session" so that the agent loop can pass it to
``SkillDispatcher`` as a session-pinned skill. This module provides that
storage without building a full persistence layer.

⚠️  INTERIM — Task 6 will formalize session/project skill pins. When that
happens, replace the module-level dict with the persisted store and keep the
same public helpers so callers do not need to change.
"""

from __future__ import annotations

import threading
from typing import List, Optional

#: session_id -> active slash skill name. Interim; Task 6 replaces this.
_session_skills: dict[str, str] = {}
_lock = threading.Lock()


def set_active_skill(session_id: Optional[str], name: str) -> None:
    """Record ``name`` as the active slash skill for ``session_id``.

    A ``None`` or empty ``session_id`` is a no-op: slash invocation without a
    session cannot be remembered for a later turn.
    """
    if not session_id or not name:
        return
    with _lock:
        _session_skills[session_id] = name


def get_active_skills(session_id: Optional[str]) -> List[str]:
    """Return a list containing the active slash skill for ``session_id``.

    Returns an empty list when no session is given or nothing is active.
    The list shape matches ``SkillDispatcher.resolve_active_skills``'s
    ``pinned_names`` parameter.
    """
    if not session_id:
        return []
    with _lock:
        name = _session_skills.get(session_id)
    return [name] if name else []


def clear_active_skill(session_id: Optional[str]) -> None:
    """Remove any active slash skill for ``session_id``."""
    if not session_id:
        return
    with _lock:
        _session_skills.pop(session_id, None)
