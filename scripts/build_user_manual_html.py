from __future__ import annotations

import html
import re
from pathlib import Path

SRC = Path("docs/CARBON_AGENT_USER_MANUAL.md")
OUT = Path("docs/CARBON_AGENT_USER_MANUAL.html")


def inline_md(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def table_to_html(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        return ""
    head = rows[0]
    body = rows[2:]
    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{inline_md(c)}</th>" for c in head)
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        out.extend(f"<td>{inline_md(c)}</td>" for c in row)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            close_lists()
            i += 1
            continue

        if stripped == "---":
            close_lists()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            close_lists()
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(table_to_html(table_lines))
            continue

        img = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if img:
            close_lists()
            alt, src = img.groups()
            out.append(f'<figure><img src="{html.escape(src)}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>')
            i += 1
            continue

        if stripped.startswith("### "):
            close_lists()
            out.append(f"<h3>{inline_md(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            close_lists()
            out.append(f"<h2>{inline_md(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            close_lists()
            out.append(f"<h1>{inline_md(stripped[2:])}</h1>")
        elif stripped.startswith("- "):
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline_md(stripped[2:])}</li>")
        elif re.match(r"\d+\. ", stripped):
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline_md(re.sub(r'^\d+\. ', '', stripped))}</li>")
        else:
            close_lists()
            out.append(f"<p>{inline_md(stripped)}</p>")
        i += 1
    close_lists()
    return "\n".join(out)


css = """
:root { --red:#c61a1d; --ink:#171717; --muted:#666; --line:#ddd; --bg:#fff; --soft:#f7f7f7; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height:1.55; }
.manual { max-width: 980px; margin: 0 auto; padding: 42px 42px 70px; }
h1 { font-size: 2.35rem; color: var(--red); margin: 0 0 0.4rem; letter-spacing: -0.03em; }
h2 { break-before: page; margin-top: 2.2rem; padding-top: 0.7rem; border-top: 2px solid var(--red); color: #222; font-size: 1.55rem; }
h2:first-of-type { break-before: auto; }
h3 { color:#333; margin-top:1.4rem; }
p { margin: 0.55rem 0 0.8rem; }
ul, ol { margin-top:0.4rem; padding-left:1.45rem; }
li { margin:0.22rem 0; }
hr { border:none; border-top:1px solid var(--line); margin:1.4rem 0; }
code { background:#f0eeee; color:#9a1114; padding:0.12rem 0.28rem; border-radius:4px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:0.92em; }
figure { margin: 1.05rem 0 1.4rem; padding: 10px; background: var(--soft); border:1px solid var(--line); border-radius:12px; break-inside: avoid; }
img { display:block; width:100%; height:auto; border-radius:8px; border:1px solid #e4e4e4; }
figcaption { color:var(--muted); font-size:0.86rem; margin-top:0.45rem; text-align:center; }
table { width:100%; border-collapse:collapse; margin:1rem 0; font-size:0.92rem; }
th, td { border:1px solid var(--line); padding:0.45rem 0.55rem; text-align:left; vertical-align:top; }
th { background:#f4eeee; color:#8d1417; }
.cover-note { border-left: 4px solid var(--red); padding: 0.8rem 1rem; background:#fff7f7; margin:1rem 0 1.4rem; }
@media print {
  body { font-size: 11.5pt; }
  .manual { max-width: none; padding: 20mm 16mm; }
  h1 { font-size: 24pt; }
  h2 { font-size: 16pt; }
  figure { break-inside: avoid; }
}
"""

body = convert(SRC.read_text())
html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CarbonAgent User Manual</title>
<style>{css}</style>
</head>
<body>
<main class="manual">
{body}
</main>
</body>
</html>
"""
OUT.write_text(html_doc)
print(OUT)
