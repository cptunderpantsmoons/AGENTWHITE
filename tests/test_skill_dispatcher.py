"""Unit tests for src/skill_dispatcher.py.

Uses lightweight fake SkillsManager objects so the tests do not pull in the
heavy production dependency graph under services/.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional

import pytest

from src.skill_dispatcher import ResolvedSkill, SkillDispatcher


class FakeSkillsManager:
    """Minimal stand-in for services.memory.skills.SkillsManager."""

    def __init__(self, skills: Optional[List[Dict[str, Any]]] = None):
        self.skills = list(skills or [])

    def load(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        if owner is None:
            return list(self.skills)
        return [s for s in self.skills if s.get("owner") == owner]

    def load_all(self) -> List[Dict[str, Any]]:
        return list(self.skills)

    def get_relevant_skills(
        self,
        query: str,
        skills: Optional[List[Dict[str, Any]]] = None,
        threshold: float = 0.3,
        max_items: int = 5,
        min_confidence: float = 0.0,
    ) -> List[Dict[str, Any]]:
        target = (skills or self.skills)[:]
        q = (query or "").lower()
        q_words = [w for w in q.split() if len(w) > 1]
        scored: List[tuple[float, Dict[str, Any]]] = []
        for s in target:
            text = " ".join(
                [
                    str(s.get("name", "")),
                    str(s.get("description", "")),
                    str(s.get("when_to_use", "")),
                    " ".join(str(t) for t in (s.get("tags") or [])),
                    " ".join(str(p) for p in (s.get("procedure") or [])),
                    " ".join(str(t) for t in (s.get("triggers") or [])),
                ]
            ).lower()
            if not text.strip():
                continue
            if q in text:
                score = 1.0
            elif any(t.lower() in q for t in (s.get("triggers") or [])):
                score = 0.9
            elif q_words and any(w in text for w in q_words):
                score = 0.6
            else:
                continue
            if min_confidence and (s.get("confidence") or 0) < min_confidence:
                continue
            scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:max_items]]

    def read_skill_md(
        self, name: str, owner: Optional[str] = None
    ) -> Optional[str]:
        for s in self.skills:
            if s.get("name") == name and s.get("owner") == owner:
                return s.get("_markdown")
        return None


def _skill(
    name: str,
    description: str = "",
    *,
    triggers: Optional[List[str]] = None,
    pinned: bool = False,
    priority: int = 0,
    owner: Optional[str] = None,
    tools_required: Optional[List[str]] = None,
    tools_disabled: Optional[List[str]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    inject_mode: str = "procedure",
    **extra: Any,
) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "when_to_use": f"Use {name}",
        "triggers": list(triggers or []),
        "pinned": bool(pinned),
        "priority": int(priority),
        "owner": owner,
        "tools_required": list(tools_required or []),
        "tools_disabled": list(tools_disabled or []),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "inject_mode": inject_mode,
        "status": "published",
        "confidence": 0.8,
        "_markdown": f"# {name}\n\n{description}",
        **extra,
    }


class TestExactSlashMatching:
    def test_slash_returns_matching_skill(self):
        mgr = FakeSkillsManager([_skill("open-pr", "Open a PR")])
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/open-pr")
        assert len(results) == 1
        assert results[0].name == "open-pr"
        assert results[0].reason == "slash"
        assert "# open-pr" in results[0].markdown

    def test_unknown_slash_returns_empty_list(self):
        mgr = FakeSkillsManager([_skill("open-pr", "Open a PR")])
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/not-a-skill")
        assert results == []

    def test_slash_with_arguments_returns_skill(self):
        mgr = FakeSkillsManager([_skill("open-pr", "Open a PR")])
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/open-pr from branch feat-x")
        assert len(results) == 1
        assert results[0].name == "open-pr"


class TestTriggerMatching:
    def test_trigger_substring_matches(self):
        mgr = FakeSkillsManager(
            [_skill("refactor", "Refactor code", triggers=["refactor", "clean up"])]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("Please refactor this function")
        assert len(results) == 1
        assert results[0].name == "refactor"
        assert results[0].reason == "trigger"

    def test_trigger_regex_matches(self):
        mgr = FakeSkillsManager(
            [_skill("semver", "Version bump", triggers=[r"bump (major|minor|patch)"])]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("can you bump minor version")
        assert len(results) == 1
        assert results[0].name == "semver"

    def test_trigger_case_insensitive(self):
        mgr = FakeSkillsManager(
            [_skill("docker", "Docker helpers", triggers=["dockerize"])]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("Dockerize my app")
        assert len(results) == 1
        assert results[0].name == "docker"

    def test_trigger_skips_invalid_regex_safely(self):
        mgr = FakeSkillsManager(
            [_skill("test", "Test skill", triggers=["(invalid", "plain"])]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("plain text")
        assert len(results) == 1
        assert results[0].name == "test"

    def test_trigger_malicious_regex_does_not_hang(self):
        import time

        # Pattern with nested quantifiers that causes catastrophic backtracking
        # when there is no final ``b`` to match.
        mgr = FakeSkillsManager(
            [_skill("evil", "Evil skill", triggers=[r"(a+)+b"])]
        )
        dispatcher = SkillDispatcher(mgr)
        start = time.perf_counter()
        results = dispatcher.resolve_active_skills("a" * 3000)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5
        assert results == []


class TestPriorityAndCapping:
    def test_priority_tiebreaks_trigger_matches(self):
        mgr = FakeSkillsManager(
            [
                _skill("low", "Low priority", triggers=["help"], priority=0),
                _skill("high", "High priority", triggers=["help"], priority=10),
                _skill("medium", "Medium priority", triggers=["help"], priority=5),
            ]
        )
        dispatcher = SkillDispatcher(mgr, max_active=5)
        results = dispatcher.resolve_active_skills("I need help")
        assert [r.name for r in results] == ["high", "medium", "low"]

    def test_max_active_caps_results(self):
        mgr = FakeSkillsManager(
            [
                _skill("a", "Skill A", triggers=["run"]),
                _skill("b", "Skill B", triggers=["run"]),
                _skill("c", "Skill C", triggers=["run"]),
            ]
        )
        dispatcher = SkillDispatcher(mgr, max_active=2)
        results = dispatcher.resolve_active_skills("run tests")
        assert len(results) == 2
        assert {r.name for r in results} <= {"a", "b", "c"}

    def test_cap_default_is_three(self):
        mgr = FakeSkillsManager(
            [_skill(f"s{i}", f"Skill {i}", triggers=["go"]) for i in range(5)]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("go now")
        assert len(results) == 3


class TestPinnedSkills:
    def test_session_pinned_included(self):
        mgr = FakeSkillsManager(
            [
                _skill("alpha", "Alpha"),
                _skill("beta", "Beta"),
            ]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("hi", pinned_names=["beta"])
        assert any(r.name == "beta" and r.reason == "pinned" for r in results)

    def test_pinned_persists_across_mocked_turns(self):
        mgr = FakeSkillsManager([_skill("always", "Always use")])
        dispatcher = SkillDispatcher(mgr)
        for message in ("hi", "bye", "what is the weather"):
            results = dispatcher.resolve_active_skills(message, pinned_names=["always"])
            assert any(
                r.name == "always" and r.reason == "pinned" for r in results
            ), f"missing pinned skill for message {message!r}"

    def test_project_pinned_flag_included(self):
        project_mgr = FakeSkillsManager(
            [
                _skill("adhoc", "Adhoc"),
                _skill("always", "Always use", pinned=True),
            ]
        )
        dispatcher = SkillDispatcher(
            skills_manager=FakeSkillsManager([]),
            project_skills_manager=project_mgr,
        )
        results = dispatcher.resolve_active_skills(
            "generic message", workspace="/tmp/proj"
        )
        names = {r.name: r.reason for r in results}
        assert names.get("always") == "pinned"


class TestResolutionOrderAndDeduplication:
    def test_slash_wins_over_trigger_for_same_name(self):
        mgr = FakeSkillsManager(
            [_skill("deploy", "Deploy", triggers=["deploy"])]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/deploy")
        assert len(results) == 1
        assert results[0].reason == "slash"

    def test_no_skill_returned_twice(self):
        mgr = FakeSkillsManager(
            [
                _skill("deploy", "Deploy", triggers=["deploy"], pinned=True),
            ]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills(
            "/deploy", pinned_names=["deploy"]
        )
        assert len(results) == 1
        assert results[0].name == "deploy"

    def test_local_skill_overrides_global_by_name(self):
        global_mgr = FakeSkillsManager(
            [_skill("build", "Global build", _markdown="global")]
        )
        project_mgr = FakeSkillsManager(
            [_skill("build", "Project build", _markdown="project")]
        )
        dispatcher = SkillDispatcher(global_mgr, project_skills_manager=project_mgr)
        results = dispatcher.resolve_active_skills("/build", workspace="/tmp/proj")
        assert len(results) == 1
        assert results[0].markdown == "project"


class TestRelevanceFallback:
    def test_relevance_fills_remaining_slots(self):
        mgr = FakeSkillsManager(
            [
                _skill("python", "pythonic code"),
                _skill("java", "java code"),
            ]
        )
        dispatcher = SkillDispatcher(mgr, max_active=2)
        results = dispatcher.resolve_active_skills("need python help")
        assert results[-1].name == "python"
        assert results[-1].reason == "relevance"

    def test_relevance_fallback_ordering_is_unambiguous(self):
        """Ordering must come from dispatch priority, not accidental name sort."""

        class ScoredManager(FakeSkillsManager):
            def get_relevant_skills(self, query, skills=None, **kwargs):
                target = list(skills or self.skills)
                # Simulate a scorer that returns candidates by score, using a
                # deliberately non-alphabetical priority order.
                target.sort(key=lambda s: -s.get("priority", 0))
                return target[: kwargs.get("max_items", 5)]

        mgr = ScoredManager(
            [
                _skill("zeta", "Zeta docs", priority=3),
                _skill("alpha", "Alpha docs", priority=1),
                _skill("beta", "Beta docs", priority=2),
            ]
        )
        dispatcher = SkillDispatcher(mgr, max_active=3)
        results = dispatcher.resolve_active_skills("docs")
        # If ordering were driven by the secondary name sort, the result would
        # be alpha, beta, zeta.  The expected order proves priority is used.
        assert [r.name for r in results] == ["zeta", "beta", "alpha"]

    def test_relevance_not_used_when_slash_resolves(self):
        mgr = FakeSkillsManager(
            [
                _skill("python", "pythonic code"),
                _skill("deploy", "Deploy skill"),
            ]
        )
        dispatcher = SkillDispatcher(mgr, max_active=3)
        results = dispatcher.resolve_active_skills("/deploy")
        assert [r.name for r in results] == ["deploy"]


class TestToolAndModelOverrides:
    def test_resolved_skill_includes_tool_gates(self):
        mgr = FakeSkillsManager(
            [
                _skill(
                    "infra",
                    "Infrastructure",
                    tools_required=["bash", "docker"],
                    tools_disabled=["file_write", "ask_user"],
                    temperature=0.1,
                    max_tokens=2048,
                    inject_mode="directive",
                )
            ]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/infra")
        assert len(results) == 1
        res = results[0]
        assert res.tools_required == ["bash", "docker"]
        # The safety confirmation tool must never be disabled by a skill.
        assert res.tools_disabled == ["file_write"]
        assert res.temperature == 0.1
        assert res.max_tokens == 2048
        assert res.inject_mode == "directive"

    def test_resolved_skill_safe_flag_defaults_to_false(self):
        mgr = FakeSkillsManager([_skill("plain", "Plain skill")])
        dispatcher = SkillDispatcher(mgr)
        res = dispatcher.resolve_active_skills("/plain")[0]
        assert res.safe is False

    def test_resolved_skill_safe_flag_read_from_skill(self):
        mgr = FakeSkillsManager([_skill("safe", "Safe skill", safe=True)])
        dispatcher = SkillDispatcher(mgr)
        res = dispatcher.resolve_active_skills("/safe")[0]
        assert res.safe is True
        assert res.to_dict()["safe"] is True

    def test_max_tokens_zero_preserved_and_missing_is_none(self):
        mgr = FakeSkillsManager(
            [
                _skill("zero", "Zero token limit", max_tokens=0),
                _skill("missing", "No token limit"),
            ]
        )
        dispatcher = SkillDispatcher(mgr)
        zero = dispatcher.resolve_active_skills("/zero")[0]
        missing = dispatcher.resolve_active_skills("/missing")[0]
        assert zero.max_tokens == 0
        assert missing.max_tokens is None


class TestGracefulDegradation:
    def test_no_skills_manager_returns_empty(self):
        dispatcher = SkillDispatcher(None)
        assert dispatcher.resolve_active_skills("hello") == []

    def test_no_matching_skills_returns_empty(self):
        mgr = FakeSkillsManager([_skill("deploy", "Deploy")])
        dispatcher = SkillDispatcher(mgr)
        assert dispatcher.resolve_active_skills("banana") == []

    def test_load_failure_handled_gracefully(self):
        class BrokenManager:
            def load(self, owner: Optional[str] = None):
                raise RuntimeError("disk error")

            def get_relevant_skills(self, *args, **kwargs):
                raise RuntimeError("disk error")

        dispatcher = SkillDispatcher(BrokenManager())
        assert dispatcher.resolve_active_skills("hello") == []


class TestPathValidation:
    def test_path_traversal_outside_skills_root_is_blocked(self, tmp_path):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()

        secret_file = tmp_path / "secret.md"
        secret_file.write_text("secret content")

        skill = _skill("leaky", "Leaky skill", _markdown="# safe\n")
        skill["path"] = str(secret_file)

        class RootedManager(FakeSkillsManager):
            def __init__(self, skills_root, skills):
                super().__init__(skills)
                self.skills_root = str(skills_root)

        mgr = RootedManager(skills_root, [skill])
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/leaky")
        assert len(results) == 1
        assert results[0].markdown == "# safe\n"
        assert "secret content" not in results[0].markdown

    def test_path_inside_skills_root_is_allowed(self, tmp_path):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "general" / "disky"
        skill_dir.mkdir(parents=True)
        md_file = skill_dir / "SKILL.md"
        md_file.write_text("# from disk\n")

        skill = _skill("disky", "Disky skill", _markdown="# from manager\n")
        skill["path"] = str(md_file)

        class RootedManager(FakeSkillsManager):
            def __init__(self, skills_root, skills):
                super().__init__(skills)
                self.skills_root = str(skills_root)

        mgr = RootedManager(skills_root, [skill])
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/disky")
        assert len(results) == 1
        assert results[0].markdown == "# from disk\n"


class TestRegexTimeoutSafety:
    def test_regex_trigger_in_non_main_thread_does_not_crash(self):
        """SIGALRM cannot be installed in non-main threads; dispatcher must fall back."""
        # Use the catastrophic-backtracking pattern so the safe fallback (literal
        # substring matching) both avoids a crash and returns promptly.
        mgr = FakeSkillsManager(
            [_skill("evil", "Evil skill", triggers=[r"(a+)+b"])]
        )
        dispatcher = SkillDispatcher(mgr)
        results: List[ResolvedSkill] = []
        exception: Optional[BaseException] = None

        def _run() -> None:
            nonlocal results, exception
            try:
                results = dispatcher.resolve_active_skills("a" * 3000)
            except BaseException as exc:
                exception = exc

        thread = threading.Thread(target=_run)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "dispatcher hung in non-main thread"
        assert exception is None, f"dispatcher raised in non-main thread: {exception}"
        # The safe fallback does not run the unbounded regex, so the evil skill
        # is not activated.
        assert results == []


class TestProjectOnlyRelevanceFallback:
    def test_relevance_uses_project_manager_when_global_missing(self):
        project_mgr = FakeSkillsManager(
            [
                _skill("pytool", "Pythonic helper"),
                _skill("javatool", "Java helper"),
            ]
        )
        dispatcher = SkillDispatcher(
            skills_manager=None,
            project_skills_manager=project_mgr,
            max_active=2,
        )
        results = dispatcher.resolve_active_skills(
            "pythonic code", workspace="/tmp/proj"
        )
        assert len(results) == 1
        assert results[0].name == "pytool"
        assert results[0].reason == "relevance"


class TestProjectLoadingWithoutWorkspace:
    def test_project_skills_load_without_workspace(self):
        project_mgr = FakeSkillsManager(
            [_skill("localskill", "Project-local skill")]
        )
        dispatcher = SkillDispatcher(
            skills_manager=FakeSkillsManager([]),
            project_skills_manager=project_mgr,
        )
        results = dispatcher.resolve_active_skills("/localskill")
        assert len(results) == 1
        assert results[0].name == "localskill"
        assert results[0].reason == "slash"

    def test_resolved_skill_source_manager_points_to_project_manager(self):
        global_mgr = FakeSkillsManager([_skill("shared", "Global shared")])
        project_mgr = FakeSkillsManager([_skill("localonly", "Project only")])
        dispatcher = SkillDispatcher(global_mgr, project_skills_manager=project_mgr)

        global_result = dispatcher.resolve_active_skills("/shared")[0]
        assert global_result.source_manager is global_mgr

        project_result = dispatcher.resolve_active_skills("/localonly")[0]
        assert project_result.source_manager is project_mgr

    def test_resolved_skill_to_dict_omits_source_manager(self):
        project_mgr = FakeSkillsManager([_skill("localonly", "Project only")])
        dispatcher = SkillDispatcher(
            skills_manager=None,
            project_skills_manager=project_mgr,
        )
        result = dispatcher.resolve_active_skills("/localonly")[0]
        assert "source_manager" not in result.to_dict()


class TestAskUserStripping:
    def test_ask_user_removed_from_tools_disabled(self):
        mgr = FakeSkillsManager(
            [
                _skill(
                    "unsafe",
                    "Tries to disable safety tool",
                    tools_disabled=["bash", "ask_user", "file_write"],
                )
            ]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/unsafe")
        assert len(results) == 1
        assert results[0].tools_disabled == ["bash", "file_write"]

    def test_ask_user_preserved_for_safe_admin_skill(self, monkeypatch):
        """A safe skill owned by an admin keeps ask_user in tools_disabled."""
        import src.tool_security as ts

        monkeypatch.setattr(
            ts, "owner_is_admin_or_single_user", lambda owner: True, raising=False
        )
        mgr = FakeSkillsManager(
            [
                _skill(
                    "safe-skill",
                    "Safe skill",
                    tools_disabled=["bash", "ask_user", "file_write"],
                    safe=True,
                    owner="admin@x",
                )
            ]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/safe-skill", owner="admin@x")
        assert len(results) == 1
        # ask_user must survive the dispatcher because the skill is safe and
        # the owner is admin — the agent-loop gate is the single source of
        # truth for the actual disable decision.
        assert "ask_user" in results[0].tools_disabled
        assert "bash" in results[0].tools_disabled
        assert "file_write" in results[0].tools_disabled

    def test_ask_user_stripped_for_safe_skill_non_admin_owner(self, monkeypatch):
        """A safe skill owned by a non-admin still loses ask_user."""
        import src.tool_security as ts

        monkeypatch.setattr(
            ts, "owner_is_admin_or_single_user", lambda owner: False, raising=False
        )
        mgr = FakeSkillsManager(
            [
                _skill(
                    "safe-skill",
                    "Safe skill but non-admin owner",
                    tools_disabled=["bash", "ask_user"],
                    safe=True,
                    owner="user@x",
                )
            ]
        )
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/safe-skill", owner="user@x")
        assert len(results) == 1
        assert "ask_user" not in results[0].tools_disabled
        assert "bash" in results[0].tools_disabled


class TestRelativePathResolution:
    def test_relative_path_resolved_against_manager_root(self, tmp_path):
        skills_root = tmp_path / "skills"
        skill_dir = skills_root / "general" / "relative"
        skill_dir.mkdir(parents=True)
        md_file = skill_dir / "SKILL.md"
        md_file.write_text("# from relative path\n")

        skill = _skill("relative", "Relative skill", _markdown="# from manager\n")
        skill["path"] = "general/relative/SKILL.md"

        class RootedManager(FakeSkillsManager):
            def __init__(self, skills_root, skills):
                super().__init__(skills)
                self.skills_root = str(skills_root)

        mgr = RootedManager(skills_root, [skill])
        dispatcher = SkillDispatcher(mgr)
        results = dispatcher.resolve_active_skills("/relative")
        assert len(results) == 1
        assert results[0].markdown == "# from relative path\n"


class FixedOrderManager(FakeSkillsManager):
    """Fake manager that returns skills sorted by priority (descending)."""

    def get_relevant_skills(self, query, skills=None, **kwargs):
        target = list(skills or self.skills)
        target.sort(key=lambda s: -s.get("priority", 0))
        return target[: kwargs.get("max_items", 5)]


class TestProjectPinnedFilter:
    def test_global_pinned_not_in_project_pinned_stage(self):
        global_mgr = FakeSkillsManager(
            [_skill("global_pinned", "Global pinned", pinned=True)]
        )
        project_mgr = FakeSkillsManager(
            [_skill("project_pinned", "Project pinned", pinned=True)]
        )
        dispatcher = SkillDispatcher(global_mgr, project_skills_manager=project_mgr)
        results = dispatcher.resolve_active_skills(
            "generic message", workspace="/tmp/proj"
        )
        assert [r.name for r in results] == ["project_pinned"]
        assert results[0].reason == "pinned"

    def test_project_pinned_stage_empty_without_project_manager(self):
        global_mgr = FakeSkillsManager(
            [_skill("global_pinned", "Global pinned", pinned=True)]
        )
        dispatcher = SkillDispatcher(global_mgr)
        results = dispatcher.resolve_active_skills(
            "generic message", workspace="/tmp/proj"
        )
        assert not any(
            r.name == "global_pinned" and r.reason == "pinned" for r in results
        )


class TestRelevanceFallbackProjectFirst:
    def test_project_relevance_considered_before_global(self):
        global_mgr = FixedOrderManager(
            [_skill("global_high", "Global high", priority=100)]
        )
        project_mgr = FixedOrderManager(
            [_skill("project_low", "Project low", priority=1)]
        )
        dispatcher = SkillDispatcher(
            global_mgr, project_skills_manager=project_mgr, max_active=2
        )
        results = dispatcher.resolve_active_skills(
            "relevance query", workspace="/tmp/proj"
        )
        assert [r.name for r in results] == ["project_low", "global_high"]


class TestRelevanceFallbackSkillIsolation:
    def test_each_manager_receives_only_its_own_skills(self):
        class Recorder(FakeSkillsManager):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.received_skills = None

            def get_relevant_skills(self, query, skills=None, **kwargs):
                self.received_skills = list(skills or [])
                return super().get_relevant_skills(query, skills, **kwargs)

        global_skill = _skill(
            "shared", "Global shared", _markdown="global md", priority=10
        )
        project_skill = _skill(
            "shared", "Project shared", _markdown="project md", priority=5
        )
        global_recorder = Recorder([global_skill])
        project_recorder = Recorder([project_skill])

        dispatcher = SkillDispatcher(
            global_recorder,
            project_skills_manager=project_recorder,
            max_active=2,
        )
        results = dispatcher.resolve_active_skills(
            "shared query", workspace="/tmp/proj"
        )

        assert [s["name"] for s in global_recorder.received_skills] == ["shared"]
        assert global_recorder.received_skills[0]["_markdown"] == "global md"

        assert [s["name"] for s in project_recorder.received_skills] == ["shared"]
        assert project_recorder.received_skills[0]["_markdown"] == "project md"

        assert results[0].markdown == "project md"
