"""Static regressions for slash autocomplete command-group expansion."""

from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent
_AC = (_REPO / "static" / "js" / "slashAutocomplete.js").read_text(encoding="utf-8")


def test_exact_parent_command_expands_subcommands_before_top_level_row_cap():
    assert "function _exactCommandGroupItems" in _AC
    assert "entry.token.toLowerCase().startsWith(prefix)" in _AC
    assert "items = groupItems.slice(0, MAX_VISIBLE);" in _AC


def test_setup_group_has_room_for_chatgpt_subscription_suggestion():
    assert "const MAX_VISIBLE = 14;" in _AC


def test_skills_merged_after_built_ins_so_builtins_win_on_collision():
    assert "function _mergeSkills(" in _AC
    assert "_mergeSkills(_flatten(), skillEntries)" in _AC


def test_cursor_position_hides_autocomplete_past_first_space():
    assert "textarea.selectionStart" in _AC
    assert "const firstSpace = v.indexOf(' ')" in _AC
    assert "cursor > firstSpace" in _AC


def test_newline_hides_autocomplete():
    assert "v.includes('\\n')" in _AC
