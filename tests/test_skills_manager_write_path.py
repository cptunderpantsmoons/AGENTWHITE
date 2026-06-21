"""Tests for the SkillsManager write path with the extended frontmatter schema.

These tests load the modules under test directly with importlib to avoid pulling
in the heavy `services` and `core` package graphs that `conftest.py` and
cross-module imports would otherwise require.
"""

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

project_root = Path(__file__).parent.parent
services_pkg = project_root / "services"
memory_pkg = services_pkg / "memory"
core_pkg = project_root / "core"

# Stub out the parent packages so relative/absolute imports resolve without
# triggering the full service graph.
sys.modules["services"] = types.ModuleType("services")
sys.modules["services.memory"] = types.ModuleType("services.memory")
sys.modules["core"] = types.ModuleType("core")

# Load the standalone skill_format module into the fake package.
skill_format_path = memory_pkg / "skill_format.py"
skill_format_spec = importlib.util.spec_from_file_location(
    "services.memory.skill_format", skill_format_path
)
skill_format = importlib.util.module_from_spec(skill_format_spec)
sys.modules["services.memory.skill_format"] = skill_format
skill_format_spec.loader.exec_module(skill_format)

# Load the standalone atomic_io module into the fake core package.
atomic_io_path = core_pkg / "atomic_io.py"
atomic_io_spec = importlib.util.spec_from_file_location(
    "core.atomic_io", atomic_io_path
)
atomic_io = importlib.util.module_from_spec(atomic_io_spec)
sys.modules["core.atomic_io"] = atomic_io
atomic_io_spec.loader.exec_module(atomic_io)

# Now load skills.py with its relative import satisfied.
skills_path = memory_pkg / "skills.py"
skills_spec = importlib.util.spec_from_file_location(
    "services.memory.skills", skills_path
)
skills = importlib.util.module_from_spec(skills_spec)
sys.modules["services.memory.skills"] = skills
skills_spec.loader.exec_module(skills)

SkillsManager = skills.SkillsManager
Skill = skill_format.Skill


def _manager() -> SkillsManager:
    tmpdir = tempfile.mkdtemp(prefix="skills_test_")
    return SkillsManager(tmpdir)


def test_add_skill_writes_new_frontmatter_fields():
    mgr = _manager()
    d = mgr.add_skill(
        title="Test skill",
        description="A test skill.",
        category="dev",
        triggers=["trigger one", "trigger two"],
        examples=["example one"],
        tools_required=["Bash"],
        tools_disabled=["WebSearch"],
        priority=7,
        pinned=True,
        temperature=0.3,
        max_tokens=1024,
        inject_mode="directive",
    )

    assert d["name"].startswith("test-skill")
    assert d["triggers"] == ["trigger one", "trigger two"]
    assert d["examples"] == ["example one"]
    assert d["tools_required"] == ["Bash"]
    assert d["tools_disabled"] == ["WebSearch"]
    assert d["priority"] == 7
    assert d["pinned"] is True
    assert d["temperature"] == 0.3
    assert d["max_tokens"] == 1024
    assert d["inject_mode"] == "directive"

    # Verify on-disk representation
    text = mgr.read_skill_md(d["name"])
    assert text is not None
    assert "triggers: [trigger one, trigger two]" in text
    assert "tools_required: [Bash]" in text
    assert "priority: 7" in text
    assert "pinned: true" in text
    assert "inject_mode: directive" in text
    assert "temperature: 0.3" in text
    assert "max_tokens: 1024" in text


def test_add_skill_rejects_invalid_inject_mode():
    mgr = _manager()
    try:
        mgr.add_skill(
            title="Bad inject mode",
            inject_mode="bogus",
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Invalid inject_mode" in str(e)
        assert "bogus" in str(e)


def test_update_skill_persists_new_fields():
    mgr = _manager()
    d = mgr.add_skill(title="Updatable", description="Before update.")
    name = d["name"]

    ok = mgr.update_skill(
        name,
        {
            "priority": 5,
            "pinned": True,
            "temperature": 0.1,
            "max_tokens": 2048,
            "inject_mode": "directive",
            "triggers": ["new trigger"],
            "tools_required": ["Read"],
            "tools_disabled": ["Bash"],
        },
    )
    assert ok is True

    updated = mgr.load_all()[0]
    assert updated["priority"] == 5
    assert updated["pinned"] is True
    assert updated["temperature"] == 0.1
    assert updated["max_tokens"] == 2048
    assert updated["inject_mode"] == "directive"
    assert updated["triggers"] == ["new trigger"]
    assert updated["tools_required"] == ["Read"]
    assert updated["tools_disabled"] == ["Bash"]

    text = mgr.read_skill_md(name)
    assert text is not None
    assert "priority: 5" in text
    assert "inject_mode: directive" in text


def test_update_skill_rejects_invalid_inject_mode():
    mgr = _manager()
    d = mgr.add_skill(title="Updatable", description="Before update.")
    name = d["name"]

    try:
        mgr.update_skill(name, {"inject_mode": "invalid"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Invalid inject_mode" in str(e)

    # Ensure the file was not modified
    text = mgr.read_skill_md(name)
    assert text is not None
    assert "inject_mode: invalid" not in text


def test_update_skill_preserves_explicit_default_scalar_values():
    """A file that already declares default scalars must keep them on rewrite."""
    mgr = _manager()
    name = "explicit-defaults"
    skill_dir = Path(mgr._skill_file("general", name)).parent
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    original = """\
---
name: explicit-defaults
description: Skill with explicit default values.
priority: 0
pinned: false
inject_mode: procedure
status: draft
---

## Procedure

1. Do nothing
"""
    skill_path.write_text(original, encoding="utf-8")

    # Update an unrelated field so the whole file is rewritten.
    ok = mgr.update_skill(name, {"description": "Updated description."})
    assert ok is True

    text = mgr.read_skill_md(name)
    assert text is not None
    assert "priority: 0" in text
    assert "pinned: false" in text
    assert "inject_mode: procedure" in text
    assert "Updated description." in text

    # Re-read through Skill parser
    sk = Skill.from_markdown(text)
    assert sk.priority == 0
    assert sk.pinned is False
    assert sk.inject_mode == "procedure"

    md2 = sk.to_markdown()
    assert "priority: 0" in md2
    assert "pinned: false" in md2
    assert "inject_mode: procedure" in md2


def test_add_skill_elides_default_scalar_values():
    """New skills created from scratch should not emit priority:0/pinned:false/inject_mode:procedure."""
    mgr = _manager()
    d = mgr.add_skill(
        title="Defaults",
        description="Skill with explicit default values.",
        priority=0,
        pinned=False,
        inject_mode="procedure",
    )
    name = d["name"]

    text = mgr.read_skill_md(name)
    assert text is not None
    assert "priority" not in text
    assert "pinned" not in text
    assert "inject_mode" not in text


def test_max_tokens_zero_round_trips_through_manager():
    mgr = _manager()
    d = mgr.add_skill(
        title="Zero tokens",
        description="Distinction from None.",
        max_tokens=0,
    )
    name = d["name"]

    text = mgr.read_skill_md(name)
    assert text is not None
    assert "max_tokens: 0" in text

    sk = Skill.from_markdown(text)
    assert sk.max_tokens == 0
