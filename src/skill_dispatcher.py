"""Server-side skill dispatcher for Active Skills.

Decides which skills are active for a single turn. The dispatcher is
stateless: construct a new instance per turn if desired, or reuse one with no
mutable skill state.

All skill markdown text is treated as untrusted, user-editable payload. The
dispatcher does not build prompts; downstream callers are responsible for
placing the returned ``markdown`` in a user-role message.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from services.memory.skills import SkillsManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedSkill:
    """A skill selected for activation this turn."""

    name: str
    markdown: str
    tools_required: List[str] = field(default_factory=list)
    tools_disabled: List[str] = field(default_factory=list)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    inject_mode: str = "procedure"
    reason: str = "relevance"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "markdown": self.markdown,
            "tools_required": list(self.tools_required),
            "tools_disabled": list(self.tools_disabled),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "inject_mode": self.inject_mode,
            "reason": self.reason,
        }


class SkillDispatcher:
    """Resolve which skills apply to the current turn.

    Resolution order (earlier wins on name collisions):
      1. Explicit slash invocation (``/<skill-name>``).
      2. Session-pinned skill names.
      3. Project-pinned skills (frontmatter ``pinned: true``).
      4. Trigger pattern matches.
      5. Semantic/relevance fallback.

    The dispatcher is stateless and tool-gating-agnostic: it returns the
    ``tools_required`` and ``tools_disabled`` declared by the skill without
    enforcing them.
    """

    def __init__(
        self,
        skills_manager: Optional[SkillsManager] = None,
        project_skills_manager: Optional[SkillsManager] = None,
        max_active: int = 3,
        min_confidence: float = 0.0,
    ):
        self.global_manager = skills_manager
        self.project_manager = project_skills_manager
        self.max_active = max(1, int(max_active))
        self.min_confidence = float(min_confidence)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_active_skills(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        workspace: Optional[str] = None,
        owner: Optional[str] = None,
        pinned_names: Optional[List[str]] = None,
    ) -> List[ResolvedSkill]:
        """Return the active skills for this turn, capped at ``max_active``."""
        message = (user_message or "").strip()
        by_name = self._load_skills(owner, workspace)
        if not by_name:
            return []

        results: List[ResolvedSkill] = []
        seen: Set[str] = set()

        # Stage 1: explicit slash invocation.
        slash_name = self._parse_slash_name(message)
        if slash_name is not None:
            skill = by_name.get(slash_name)
            if skill is None:
                # Unknown slash skill: fall through to regular chat.
                return []
            self._add_result(skill, "slash", results, seen)

        # Stage 2: session-pinned skills.
        pinned_session = [by_name[n] for n in (pinned_names or []) if n in by_name]
        self._add_stage(pinned_session, "pinned", results, seen)

        # Stage 3: project-pinned skills (frontmatter pinned flag).
        project_pinned = [s for s in by_name.values() if s.get("pinned")]
        self._add_stage(project_pinned, "pinned", results, seen)

        # Stage 4: trigger pattern matches.
        trigger_hits = [s for s in by_name.values() if self._match_triggers(message, s)]
        self._add_stage(trigger_hits, "trigger", results, seen)

        # Stage 5: relevance fallback for any remaining slots.
        self._add_relevance_fallback(message, by_name, results, seen)

        return results

    # ------------------------------------------------------------------
    # Skill loading
    # ------------------------------------------------------------------

    def _load_skills(
        self, owner: Optional[str], workspace: Optional[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Load global skills and, with a workspace, project-local skills.

        Project-local skills override global skills with the same name.
        """
        global_skills: Dict[str, Dict[str, Any]] = {}
        if self.global_manager is not None:
            try:
                for skill in self._manager_load(self.global_manager, owner):
                    name = skill.get("name")
                    if isinstance(name, str) and name:
                        skill = dict(skill)
                        skill["_dispatcher_source"] = self.global_manager
                        global_skills[name] = skill
            except Exception:
                logger.exception("Failed to load global skills")

        project_skills: Dict[str, Dict[str, Any]] = {}
        if workspace and self.project_manager is not None:
            try:
                for skill in self._manager_load(self.project_manager, owner):
                    name = skill.get("name")
                    if isinstance(name, str) and name:
                        skill = dict(skill)
                        skill["_dispatcher_source"] = self.project_manager
                        project_skills[name] = skill
            except Exception:
                logger.exception("Failed to load project-local skills")

        # Local overrides global.
        merged = dict(global_skills)
        merged.update(project_skills)
        return merged

    @staticmethod
    def _manager_load(manager: Any, owner: Optional[str]) -> List[Dict[str, Any]]:
        """Call ``load(owner)`` when owner is given, else ``load_all``."""
        if owner is not None and hasattr(manager, "load"):
            return list(manager.load(owner))
        if hasattr(manager, "load_all"):
            return list(manager.load_all())
        if hasattr(manager, "load"):
            return list(manager.load())
        return []

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    def _add_stage(
        self,
        candidates: List[Dict[str, Any]],
        reason: str,
        results: List[ResolvedSkill],
        seen: Set[str],
    ) -> None:
        for skill in self._sort_by_priority(candidates):
            if len(results) >= self.max_active:
                break
            self._add_result(skill, reason, results, seen)

    def _add_result(
        self,
        skill: Dict[str, Any],
        reason: str,
        results: List[ResolvedSkill],
        seen: Set[str],
    ) -> None:
        name = skill.get("name")
        if not isinstance(name, str) or not name or name in seen:
            return
        results.append(self._resolve(skill, reason))
        seen.add(name)

    def _resolve(self, skill: Dict[str, Any], reason: str) -> ResolvedSkill:
        return ResolvedSkill(
            name=skill["name"],
            markdown=self._read_markdown(skill),
            tools_required=list(skill.get("tools_required") or []),
            tools_disabled=list(skill.get("tools_disabled") or []),
            temperature=skill.get("temperature"),
            max_tokens=skill.get("max_tokens"),
            inject_mode=str(skill.get("inject_mode") or "procedure"),
            reason=reason,
        )

    def _read_markdown(self, skill: Dict[str, Any]) -> str:
        """Return the full SKILL.md text for a loaded skill.

        Prefers reading from the skill's ``path``; falls back to the source
        manager's ``read_skill_md`` method when no usable path is available.
        """
        path = skill.get("path")
        if path and os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return f.read()
            except Exception:
                logger.warning("Failed to read skill markdown from %s", path)

        manager = skill.get("_dispatcher_source") or self.global_manager
        if manager is not None and hasattr(manager, "read_skill_md"):
            try:
                md = manager.read_skill_md(skill["name"], skill.get("owner"))
                if md is not None:
                    return md
            except Exception:
                logger.warning("Failed to read skill markdown via manager")
        return ""

    @staticmethod
    def _sort_by_priority(skills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            skills,
            key=lambda s: (-int(s.get("priority") or 0), str(s.get("name") or "")),
        )

    @staticmethod
    def _parse_slash_name(message: str) -> Optional[str]:
        if not message.startswith("/"):
            return None
        token = message[1:].split(None, 1)[0].strip()
        return token or None

    @staticmethod
    def _match_triggers(message: str, skill: Dict[str, Any]) -> bool:
        for trigger in skill.get("triggers") or []:
            if not trigger:
                continue
            trigger_str = str(trigger)
            try:
                if re.search(trigger_str, message, re.IGNORECASE):
                    return True
            except re.error:
                if trigger_str.lower() in message.lower():
                    return True
        return False

    def _add_relevance_fallback(
        self,
        message: str,
        by_name: Dict[str, Dict[str, Any]],
        results: List[ResolvedSkill],
        seen: Set[str],
    ) -> None:
        remaining = self.max_active - len(results)
        if remaining <= 0:
            return
        manager = self.global_manager
        if manager is None or not hasattr(manager, "get_relevant_skills"):
            return
        try:
            relevant = manager.get_relevant_skills(
                message,
                skills=list(by_name.values()),
                max_items=remaining,
                threshold=0.3,
                min_confidence=self.min_confidence,
            )
            self._add_stage(list(relevant), "relevance", results, seen)
        except Exception:
            logger.exception("Relevance fallback failed")
