"""Regression guard for the Task-7 fix: ``_wirePinButtons`` in
``static/js/skills.js`` had a redundant ``_pinWired = true`` assignment
in its early-return branch.

The original early-return branch:
    if (!container || container._pinWired) {
        if (container) container._pinWired = true;  // redundant
        return;
    }
    container._pinWired = true;

The inner assignment is dead code: the branch only fires when
``!container`` (so ``container`` is null) OR when ``container._pinWired``
is already true (so setting it again is a no-op). The fix removes the
redundant inner assignment for clarity.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static" / "js" / "skills.js"


def _fn_body(text: str, name: str) -> str:
    start = text.index(f"function {name}")
    end = text.index("\n}", start)
    return text[start:end]


def test_wire_pin_buttons_has_no_redundant_pinwired_assignment():
    """The early-return branch must not redundantly set _pinWired = true."""
    text = SRC.read_text(encoding="utf-8")
    body = _fn_body(text, "_wirePinButtons")
    # The vulnerable pattern: an inner `if (container) container._pinWired`
    # assignment inside the outer `if (!container || container._pinWired)`
    # early-return branch. After the fix, the inner assignment should be
    # gone — the outer `container._pinWired = true` after the early return
    # is the only place that flips the flag.
    assert "if (container) container._pinWired = true" not in body, (
        "_wirePinButtons has a redundant `if (container) container._pinWired "
        "= true` assignment in its early-return branch. The branch only "
        "fires when container is null OR _pinWired is already true, so the "
        "inner assignment is dead code."
    )
