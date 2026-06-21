"""Static + focused unit tests for the slash command dispatcher.

The pure helpers (_resolveCommand, _resolveSubcommand, _fuzzyMatch,
_asHandled, _handleSkillInvocation) are extracted from static/js/slashCommands.js
and driven through node --input-type=module so we are testing the actual source
rather than a copy. Tests skip when node is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parent.parent
_JS = _REPO / "static" / "js" / "slashCommands.js"
_HAS_NODE = shutil.which("node") is not None
pytestmark = pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")


def _extract_function(source: str, name: str) -> str:
    """Brace-balanced extraction of a function definition by name."""
    prefixes = (f"async function {name}(", f"function {name}(")
    start = -1
    for prefix in prefixes:
        start = source.find(prefix)
        if start != -1:
            break
    if start == -1:
        raise ValueError(f"Function {name!r} not found")
    # Find the end of the parameter list (handles destructured params).
    paren_idx = source.find("(", start)
    depth = 0
    paren_end = -1
    for i in range(paren_idx, len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                paren_end = i
                break
    if paren_end == -1:
        raise ValueError(f"No closing parenthesis for {name!r}")
    # Walk from the function body opening brace to the matching close.
    brace_idx = source.find("{", paren_end)
    if brace_idx == -1:
        raise ValueError(f"No opening brace for {name!r}")
    depth = 0
    for i in range(brace_idx, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise ValueError(f"Could not find matching brace for {name!r}")


def _node_eval(source: str):
    result = subprocess.run(
        ["node", "--input-type=module", "-e", source],
        cwd=str(_REPO),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


_SOURCE = _JS.read_text(encoding="utf-8")


def test_source_has_dedicated_skill_handler():
    assert "async function _handleSkillInvocation(" in _SOURCE
    assert "/api/skills/invoke" in _SOURCE
    assert "_handleSkillInvocation(rawCmd, args.join(' ').trim(), ctx" in _SOURCE


def test_source_dispatcher_coerces_handler_results():
    assert "function _asHandled(result)" in _SOURCE
    assert "_asHandled(await cmdDef.handler" in _SOURCE
    assert "_asHandled(await subDef.handler" in _SOURCE
    assert "_asHandled(await _handleSkillInvocation" in _SOURCE


def test_source_skill_handler_branch_messages():
    assert "'Unknown skill: /'" in _SOURCE
    assert "'Access denied'" in _SOURCE
    assert "'Skill invocation failed: '" in _SOURCE


def test_source_autocomplete_has_cursor_guard():
    ac = (_REPO / "static" / "js" / "slashAutocomplete.js").read_text(encoding="utf-8")
    assert "textarea.selectionStart" in ac
    assert "firstSpace" in ac
    assert "skills-catalog-changed" in ac


def test_source_skills_dispatches_catalog_change():
    skills = (_REPO / "static" / "js" / "skills.js").read_text(encoding="utf-8")
    assert "new CustomEvent('skills-catalog-changed'" in skills


def test_resolve_command_and_subcommand_helpers():
    ctx = {
        "COMMANDS": {
            "chats": {
                "alias": ["chat", "session"],
                "subs": {
                    "new": {"alias": ["create", "mkdir"]},
                    "list": {},
                },
            },
            "help": {"alias": ["?"]},
        },
        "LEGACY_ALIASES": {
            "new": {"parent": "chats", "sub": "new"},
            "mkdir": {"parent": "chats", "sub": "new"},
        },
        "helpers": _extract_function(_SOURCE, "_buildAliasMap")
        + "\n"
        + _extract_function(_SOURCE, "_resolveCommand")
        + "\n"
        + _extract_function(_SOURCE, "_resolveSubcommand"),
    }
    js = (
        """
    const COMMANDS = %__COMMANDS__%;
    const LEGACY_ALIASES = %__LEGACY_ALIASES__%;
    %__helpers__%
    const _ALIAS_MAP = _buildAliasMap();
    console.log(JSON.stringify({
      help: _resolveCommand('help'),
      question: _resolveCommand('?'),
      chat: _resolveCommand('chat'),
      chats: _resolveCommand('chats'),
      missing: _resolveCommand('nope'),
      newSub: _resolveSubcommand(COMMANDS.chats, 'new'),
      createSub: _resolveSubcommand(COMMANDS.chats, 'create'),
      listSub: _resolveSubcommand(COMMANDS.chats, 'list'),
      missingSub: _resolveSubcommand(COMMANDS.chats, 'nope'),
    }));
    """.replace("%__COMMANDS__%", json.dumps(ctx["COMMANDS"], ensure_ascii=False))
        .replace("%__LEGACY_ALIASES__%", json.dumps(ctx["LEGACY_ALIASES"], ensure_ascii=False))
        .replace("%__helpers__%", ctx["helpers"])
    )
    result = _node_eval(js)
    assert result["help"] == "help"
    assert result["question"] == "help"
    assert result["chat"] == "chats"
    assert result["chats"] == "chats"
    assert result["missing"] is None
    assert result["newSub"] == "new"
    assert result["createSub"] == "new"
    assert result["listSub"] == "list"
    assert result["missingSub"] is None


def test_fuzzy_match_suggests_close_commands():
    ctx = {
        "COMMANDS": {
            "help": {"alias": ["?", "commands"]},
            "hello": {},
            "chats": {"alias": ["chat"]},
        },
        "LEGACY_ALIASES": {"new": {"parent": "chats", "sub": "new"}},
        "helpers": _extract_function(_SOURCE, "_levenshtein")
        + "\n"
        + _extract_function(_SOURCE, "_buildAliasMap")
        + "\n"
        + _extract_function(_SOURCE, "_fuzzyMatch"),
    }
    js = (
        """
    const COMMANDS = %__COMMANDS__%;
    const LEGACY_ALIASES = %__LEGACY_ALIASES__%;
    %__helpers__%
    const _ALIAS_MAP = _buildAliasMap();
    console.log(JSON.stringify({
      hep: _fuzzyMatch('hep'),
      halp: _fuzzyMatch('halp'),
      ne: _fuzzyMatch('ne'),
      xyz: _fuzzyMatch('xyz'),
    }));
    """.replace("%__COMMANDS__%", json.dumps(ctx["COMMANDS"], ensure_ascii=False))
        .replace("%__LEGACY_ALIASES__%", json.dumps(ctx["LEGACY_ALIASES"], ensure_ascii=False))
        .replace("%__helpers__%", ctx["helpers"])
    )
    result = _node_eval(js)
    assert "help" in result["hep"]
    assert "help" in result["halp"]
    assert "new" in result["ne"]
    assert result["xyz"] == []


def test_asHandled_coerces_to_boolean():
    js = (
        _extract_function(_SOURCE, "_asHandled")
        + """
    console.log(JSON.stringify({
      trueVal: _asHandled(true),
      truthyVal: _asHandled(1),
      undefinedVal: _asHandled(undefined),
      nullVal: _asHandled(null),
      falseVal: _asHandled(false),
    }));
    """
    )
    result = _node_eval(js)
    assert result["trueVal"] is True
    assert result["truthyVal"] is True
    assert result["undefinedVal"] is True
    assert result["nullVal"] is True
    assert result["falseVal"] is False


def test_handle_skill_invocation_success_sends_stripped_request():
    fn = _extract_function(_SOURCE, "_handleSkillInvocation")
    js = """
    const API_BASE = '';
    let sendArg = null;
    const _sendMessageFn = (text) => { sendArg = text; };
    let shown = false;
    const showUser = () => { shown = true; };
    let replyText = null;
    function slashReply(text) { replyText = text; }
    globalThis.fetch = () => Promise.resolve({
      status: 200,
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    %__fn__%
    const ctx = { sid: 's1', esc: (x) => x };
    _handleSkillInvocation('demo', 'do the thing', ctx, { showUser }).then(handled => {
      console.log(JSON.stringify({ handled, shown, sendArg, replyText }));
    });
    """.replace("%__fn__%", fn)
    result = _node_eval(js)
    assert result["handled"] is True
    assert result["shown"] is True
    assert result["sendArg"] == "do the thing"
    assert result["replyText"] is None


def test_handle_skill_invocation_404_falls_through_without_user_bubble():
    fn = _extract_function(_SOURCE, "_handleSkillInvocation")
    js = """
    const API_BASE = '';
    let shown = false;
    const showUser = () => { shown = true; };
    let replyText = null;
    function slashReply(text) { replyText = text; }
    globalThis.fetch = () => Promise.resolve({ status: 404, ok: false });
    %__fn__%
    const ctx = { sid: 's1', esc: (x) => x };
    _handleSkillInvocation('unknown', 'hi', ctx, { showUser }).then(handled => {
      console.log(JSON.stringify({ handled, shown, replyText }));
    });
    """.replace("%__fn__%", fn)
    result = _node_eval(js)
    assert result["handled"] is False
    assert result["shown"] is False
    assert "Unknown skill" in result["replyText"]


def test_handle_skill_invocation_403_shows_access_denied():
    fn = _extract_function(_SOURCE, "_handleSkillInvocation")
    js = """
    const API_BASE = '';
    let shown = false;
    const showUser = () => { shown = true; };
    let replyText = null;
    function slashReply(text) { replyText = text; }
    globalThis.fetch = () => Promise.resolve({ status: 403, ok: false });
    %__fn__%
    const ctx = { sid: 's1', esc: (x) => x };
    _handleSkillInvocation('private', 'hi', ctx, { showUser }).then(handled => {
      console.log(JSON.stringify({ handled, shown, replyText }));
    });
    """.replace("%__fn__%", fn)
    result = _node_eval(js)
    assert result["handled"] is True
    assert result["shown"] is True
    assert result["replyText"] == "Access denied"


def test_handle_skill_invocation_network_error_is_not_silent():
    fn = _extract_function(_SOURCE, "_handleSkillInvocation")
    js = """
    const API_BASE = '';
    let shown = false;
    const showUser = () => { shown = true; };
    let replyText = null;
    function slashReply(text) { replyText = text; }
    globalThis.fetch = () => Promise.reject(new Error('Network down'));
    %__fn__%
    const ctx = { sid: 's1', esc: (x) => x };
    _handleSkillInvocation('demo', 'hi', ctx, { showUser }).then(handled => {
      console.log(JSON.stringify({ handled, shown, replyText }));
    });
    """.replace("%__fn__%", fn)
    result = _node_eval(js)
    assert result["handled"] is True
    assert result["shown"] is True
    assert "Network down" in result["replyText"]
