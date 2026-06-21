"""Regression guard for the Task-7 fix: ``_validateActiveSkillForm`` in
``static/js/skills.js`` MUST fail closed when the tool registry is empty.

The original implementation skipped the unknown-tool check when
``_toolRegistry.size === 0``. A ``fetch`` failure to ``/api/skills/tool-registry``
falls back to an empty Set, so that branch silently let invalid tool names
through. The fix treats an empty registry as "no known tools" and rejects
any non-empty ``tools_required`` / ``tools_disabled`` list — empty lists
remain valid (no gating).

skills.js pulls in browser globals (DOM), so it can't be imported under
node; this guards the fix at the source level so it can't be silently
reverted. Pattern mirrors ``test_skill_edit_no_collapse_on_outside_click_js``.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static" / "js" / "skills.js"


def _fn_body(text: str, name: str) -> str:
    """Return the body of a top-level function declaration by name."""
    start = text.index(f"function {name}")
    # Find the closing '}' at column 0 (top-level functions are formatted
    # with the closing brace at column 0 in skills.js).
    end = text.index("\n}", start)
    return text[start:end]


def test_validate_active_skill_form_does_not_skip_empty_registry():
    """The validator must NOT short-circuit when the registry is empty.

    The vulnerable pattern is ``if (_toolRegistry && _toolRegistry.size)``
    followed by the unknown-tool check — that branch is skipped when the
    set exists but has size 0 (the fetch-failure fallback). The fix
    removes the ``.size`` guard so an empty registry still rejects unknown
    tool names.
    """
    text = SRC.read_text(encoding="utf-8")
    body = _fn_body(text, "_validateActiveSkillForm")
    assert "_toolRegistry.size" not in body, (
        "_validateActiveSkillForm must not gate the unknown-tool check on "
        "_toolRegistry.size — that lets a fetch-failure (empty registry) "
        "skip validation and admit unknown tool names. Treat an empty "
        "registry as 'no known tools' and reject any non-empty list."
    )


def test_validate_active_skill_form_rejects_unknown_when_registry_empty():
    """The validator must reject unknown tool names even when the registry
    has zero entries. The check should run whenever ``_toolRegistry`` is
    truthy (it's always a Set after _loadToolRegistry, possibly empty)."""
    text = SRC.read_text(encoding="utf-8")
    body = _fn_body(text, "_validateActiveSkillForm")
    # The unknown-tool check must run when _toolRegistry is non-null
    # (regardless of size). Match the new guard shape.
    assert re.search(r"if\s*\(\s*_toolRegistry\s*\)\s*\{", body), (
        "_validateActiveSkillForm should guard the unknown-tool check on "
        "`_toolRegistry` being non-null (not on .size > 0) so an empty "
        "registry still rejects unknown names."
    )


def test_load_tool_registry_falls_back_to_empty_set():
    """_loadToolRegistry must fall back to an empty Set on fetch failure
    so the validator's empty-registry path rejects unknown names."""
    text = SRC.read_text(encoding="utf-8")
    body = _fn_body(text, "_loadToolRegistry")
    assert "new Set()" in body, (
        "_loadToolRegistry must initialize _toolRegistry to an empty Set "
        "on fetch failure (the fail-closed fallback)."
    )
