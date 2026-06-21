"""Extend SKILL.md frontmatter with active-skill metadata.

Covers the new optional fields declared in the Active Skills schema:
triggers, examples, tools_required, tools_disabled, priority, pinned,
temperature, max_tokens, and inject_mode.
"""

import importlib.util
import sys
from pathlib import Path

_skill_format_path = Path(__file__).parent.parent / "services" / "memory" / "skill_format.py"
_spec = importlib.util.spec_from_file_location("skill_format", _skill_format_path)
_skill_format = importlib.util.module_from_spec(_spec)
sys.modules["skill_format"] = _skill_format
_spec.loader.exec_module(_skill_format)

Skill = _skill_format.Skill


_NEW_FIELDS_YAML = """\
---
name: active-demo
version: 1.0.0
description: Demonstrates the active-skill schema.
category: dev
tags: [git, github]
triggers: [open pr, create pull request]
examples: [open a PR from my branch, create pull request]
tools_required: [Bash, Read]
tools_disabled: [WebSearch]
priority: 5
pinned: true
inject_mode: directive
temperature: 0.2
max_tokens: 4096
status: published
confidence: 0.95
source: learned
owner: carbonagent
created: 2026-06-21
---

## When to Use

When you need a PR opened.

## Procedure

1. Push the branch
2. Open the PR
"""


def test_new_fields_parse_and_round_trip():
    sk = Skill.from_markdown(_NEW_FIELDS_YAML)

    assert sk.name == "active-demo"
    assert sk.triggers == ["open pr", "create pull request"]
    assert sk.examples == ["open a PR from my branch", "create pull request"]
    assert sk.tools_required == ["Bash", "Read"]
    assert sk.tools_disabled == ["WebSearch"]
    assert sk.priority == 5
    assert sk.pinned is True
    assert sk.temperature == 0.2
    assert sk.max_tokens == 4096
    assert sk.inject_mode == "directive"

    md = sk.to_markdown()
    assert "triggers: [open pr, create pull request]" in md
    assert "inject_mode: directive" in md
    assert "pinned: true" in md
    assert "priority: 5" in md

    # Full round-trip preserves every new field.
    sk2 = Skill.from_markdown(md)
    assert sk2.triggers == sk.triggers
    assert sk2.examples == sk.examples
    assert sk2.tools_required == sk.tools_required
    assert sk2.tools_disabled == sk.tools_disabled
    assert sk2.priority == sk.priority
    assert sk2.pinned == sk.pinned
    assert sk2.temperature == sk.temperature
    assert sk2.max_tokens == sk.max_tokens
    assert sk2.inject_mode == sk.inject_mode


def test_new_fields_round_trip_without_reordering():
    """The frontmatter block should keep the key order from the source."""
    sk = Skill.from_markdown(_NEW_FIELDS_YAML)
    md = sk.to_markdown()
    fm_start = md.index("---\n") + 4
    fm_end = md.index("\n---", fm_start)
    emitted = md[fm_start:fm_end]
    source_keys = [
        "name", "version", "description", "category", "tags",
        "triggers", "examples", "tools_required", "tools_disabled",
        "priority", "pinned", "inject_mode", "temperature", "max_tokens",
        "status", "confidence", "source", "owner", "created",
    ]
    expected = "\n".join(
        line for line in _NEW_FIELDS_YAML.split("\n---\n")[0].splitlines()[1:]
        if line.split(":")[0] in source_keys
    )
    assert emitted == expected, f"Frontmatter reordered:\n{emitted}"


def test_invalid_inject_mode_warns_and_defaults(caplog):
    yaml = _NEW_FIELDS_YAML.replace("inject_mode: directive", "inject_mode: bogus")
    with caplog.at_level("WARNING"):
        sk = Skill.from_markdown(yaml)
    assert sk.inject_mode == "procedure"
    assert any("inject_mode" in rec.message for rec in caplog.records)


def test_missing_new_fields_use_defaults():
    yaml = """\
---
name: passive-demo
description: A minimal skill.
category: general
status: draft
---

## When to Use

When nothing special is needed.
"""
    sk = Skill.from_markdown(yaml)
    assert sk.triggers == []
    assert sk.examples == []
    assert sk.tools_required == []
    assert sk.tools_disabled == []
    assert sk.priority == 0
    assert sk.pinned is False
    assert sk.temperature is None
    assert sk.max_tokens is None
    assert sk.inject_mode == "procedure"


def test_to_dict_includes_new_fields():
    sk = Skill.from_markdown(_NEW_FIELDS_YAML)
    d = sk.to_dict()
    assert d["triggers"] == sk.triggers
    assert d["examples"] == sk.examples
    assert d["tools_required"] == sk.tools_required
    assert d["tools_disabled"] == sk.tools_disabled
    assert d["priority"] == sk.priority
    assert d["pinned"] == sk.pinned
    assert d["temperature"] == sk.temperature
    assert d["max_tokens"] == sk.max_tokens
    assert d["inject_mode"] == sk.inject_mode


def test_max_tokens_zero_preserved():
    yaml = _NEW_FIELDS_YAML.replace("max_tokens: 4096", "max_tokens: 0")
    sk = Skill.from_markdown(yaml)
    assert sk.max_tokens == 0

    md = sk.to_markdown()
    assert "max_tokens: 0" in md

    sk2 = Skill.from_markdown(md)
    assert sk2.max_tokens == 0


def test_explicit_default_scalar_values_round_trip():
    yaml = """\
---
name: explicit-defaults
description: Defaults written explicitly.
priority: 0
pinned: false
inject_mode: procedure
status: draft
---

## Procedure

1. Do nothing
"""
    sk = Skill.from_markdown(yaml)
    assert sk.priority == 0
    assert sk.pinned is False
    assert sk.inject_mode == "procedure"

    md = sk.to_markdown()
    assert "priority: 0" in md
    assert "pinned: false" in md
    assert "inject_mode: procedure" in md

    sk2 = Skill.from_markdown(md)
    assert sk2.priority == 0
    assert sk2.pinned is False
    assert sk2.inject_mode == "procedure"


def test_new_skill_elides_default_scalar_values():
    """Skills created from scratch should not emit priority:0/pinned:false/inject_mode:procedure."""
    sk = Skill(name="fresh", description="A brand new skill.")
    fm = sk.to_frontmatter()
    assert "priority" not in fm
    assert "pinned" not in fm
    assert "inject_mode" not in fm
    assert "safe" not in fm


def test_safe_field_parses_and_round_trips():
    yaml = _NEW_FIELDS_YAML.replace("inject_mode: directive", "safe: true\ninject_mode: directive")
    sk = Skill.from_markdown(yaml)
    assert sk.safe is True

    md = sk.to_markdown()
    assert "safe: true" in md

    sk2 = Skill.from_markdown(md)
    assert sk2.safe is True


def test_safe_defaults_to_false():
    sk = Skill.from_markdown(_NEW_FIELDS_YAML)
    assert sk.safe is False


def test_to_dict_includes_safe():
    sk = Skill.from_markdown(_NEW_FIELDS_YAML.replace("inject_mode: directive", "safe: true\ninject_mode: directive"))
    d = sk.to_dict()
    assert d["safe"] is True
