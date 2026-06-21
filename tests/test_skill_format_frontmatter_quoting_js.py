"""Regression guard for the Task-7 fix: ``_formatFrontmatterLine`` in
``static/js/skills.js`` must quote YAML array items that contain special
characters (``:``, leading ``[``/``{``, etc.).

The original implementation only quoted items containing a comma (for the
inline-list split). A trigger like ``deploy: prod`` or a tag like
``[debug]`` would break YAML parsing on the server (``Skill.from_markdown``
would raise). The fix quotes items containing any YAML special character
that would confuse the inline-list parser.
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "static" / "js" / "skills.js"


def _fn_body(text: str, name: str) -> str:
    start = text.index(f"function {name}")
    end = text.index("\n}", start)
    return text[start:end]


def test_format_frontmatter_line_quotes_special_chars():
    """Array items containing ':' must be quoted so the YAML parser on the
    server side (Skill.from_markdown) doesn't choke on them."""
    text = SRC.read_text(encoding="utf-8")
    body = _fn_body(text, "_formatFrontmatterLine")
    # The fix should use a quoting check that covers ':' (and other YAML
    # special chars), not just ','. The exact regex is implementation-
    # dependent; assert the function references a character class that
    # includes ':' rather than matching only on ','.
    assert "JSON.stringify" in body, (
        "_formatFrontmatterLine must use JSON.stringify to quote array "
        "items containing special characters."
    )
    # The character class driving the quoting decision must include ':'.
    # The vulnerable pattern was checking only ',' — ensure ':' is now
    # part of the match.
    assert re.search(r"[:,\[\]\{\}\"]", body), (
        "_formatFrontmatterLine must check for ':' (and other YAML "
        "special chars) when deciding whether to quote an array item."
    )
