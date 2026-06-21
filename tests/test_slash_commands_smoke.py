"""Smoke test: slashReply creates a DOM bubble and persists with source: slash.

Runs the real slashReply helper from static/js/slashCommands.js inside a
minimal fake DOM via node.
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
_SOURCE = _JS.read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    prefixes = (f"async function {name}(", f"function {name}(")
    start = -1
    for prefix in prefixes:
        start = source.find(prefix)
        if start != -1:
            break
    if start == -1:
        raise ValueError(f"Function {name!r} not found")
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
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        raise RuntimeError(f"node failed with rc {result.returncode}: {result.stderr[:500]}")
    return json.loads(result.stdout)


def test_slash_reply_creates_ai_bubble_and_persists_with_slash_source():
    slash_reply_fn = _extract_function(_SOURCE, "slashReply")
    footer_fn = _extract_function(_SOURCE, "_slashFooter")
    js = """
function makeEl(tag) {
  const el = {
    tag,
    children: [],
    _text: '',
    dataset: {},
    classList: { add(...c) { el.className = (el.className || '') + ' ' + c.join(' '); }, remove() {} },
    get textContent() { return el.children.length ? el.children.map(c => c.textContent).join('') : el._text; },
    set textContent(v) { el._text = String(v); },
    get innerHTML() { return el._text; },
    set innerHTML(v) { el._text = String(v); el.children = []; },
    appendChild(c) { el.children.push(c); return c; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    addEventListener() {},
    setAttribute(k, v) { el[k] = v; },
    style: {},
  };
  return el;
}
const chatHistory = makeEl('div');
chatHistory.id = 'chat-history';
globalThis.document = {
  getElementById(id) { return id === 'chat-history' ? chatHistory : null; },
  createElement(tag) { return makeEl(tag); },
  querySelectorAll() { return []; },
};
const persistCalls = [];
function _persistMsg(role, content, metadata) {
  persistCalls.push({ role, content, metadata });
}
const uiModule = {
  esc: (s) => String(s),
  scrollHistory() {},
  copyToClipboard() {},
};
const sessionModule = { getCurrentSessionId: () => 's1' };
globalThis.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
const chatRenderer = {
  copyMessageText(msgEl) { return msgEl.textContent; },
};
%__footer__%

%__slashReply__%

const result = slashReply('/help');
const body = result.el.children.find(c => c.className && c.className.includes('body'));
const role = result.el.children.find(c => c.className && c.className.includes('role'));
console.log(JSON.stringify({
  hasMsgAi: result.el.className.includes('msg-ai'),
  roleText: role ? role.textContent : null,
  bodyText: body ? body.textContent : null,
  persisted: persistCalls,
}));
""".replace("%__slashReply__%", slash_reply_fn).replace("%__footer__%", footer_fn)
    result = _node_eval(js)
    assert result["hasMsgAi"] is True
    assert result["roleText"] == "Odysseus"
    assert result["bodyText"] == "/help"
    assert len(result["persisted"]) == 1
    assert result["persisted"][0]["role"] == "assistant"
    assert result["persisted"][0]["metadata"]["source"] == "slash"
