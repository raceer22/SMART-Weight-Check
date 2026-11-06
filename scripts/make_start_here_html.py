#!/usr/bin/env python3
"""Build the self-contained START_HERE.html (no external resources) from START_HERE.md.

python scripts/make_start_here_html.py            (needs the 'markdown' package: pip install markdown)
"""
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]

CSS = """
:root{--bg:#fbfbfa;--panel:#ffffff;--ink:#101418;--ink2:#4a5058;--muted:#767b82;--line:#e3e4e6;--accent:#0f5fa8;--accent-soft:#e9f1fa;
--warn:#7a4d00;--warn-soft:#fbf0d9;--code:#f1f2f3}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#15181b;--panel:#1d2125;--ink:#eceef0;--ink2:#c0c5ca;--muted:#959ba1;
--line:#33383d;--accent:#5aa2e6;--accent-soft:#1c2c3d;--warn:#f0c46b;--warn-soft:#3a3020;--code:#262b30}}
:root[data-theme="dark"]{--bg:#15181b;--panel:#1d2125;--ink:#eceef0;--ink2:#c0c5ca;--muted:#959ba1;--line:#33383d;--accent:#5aa2e6;
--accent-soft:#1c2c3d;--warn:#f0c46b;--warn-soft:#3a3020;--code:#262b30}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line);background:var(--panel)}
header .wrap{padding-top:40px;padding-bottom:28px}
.kicker{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
h1{font-size:clamp(28px,5vw,40px);line-height:1.15;margin:0 0 10px;letter-spacing:-.01em}
.sub{color:var(--ink2);margin:0 0 16px}
.badge{display:inline-block;font-size:12px;font-weight:600;letter-spacing:.04em;padding:4px 10px;border-radius:999px;
background:var(--warn-soft);color:var(--warn);margin:0 8px 6px 0}
nav.toc{margin:28px 0 8px;padding:16px 18px;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
nav.toc ol{margin:0;padding-left:22px;columns:2;column-gap:28px}nav.toc li{margin:0 0 4px;break-inside:avoid}
nav.toc a{color:var(--ink);text-decoration:none}nav.toc a:hover{color:var(--accent)}
main h2{font-size:22px;margin:44px 0 12px;padding-top:8px;letter-spacing:-.005em}
p,li{color:var(--ink)}a{color:var(--accent)}
blockquote{margin:16px 0;padding:10px 16px;border-left:3px solid var(--accent);background:var(--accent-soft);border-radius:0 8px 8px 0}
blockquote p{margin:4px 0}
code{font:13.5px/1.4 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--code);padding:1px 5px;border-radius:4px}
p code,li code,td code{overflow-wrap:anywhere}
pre{background:var(--code);padding:14px 16px;border-radius:8px;overflow-x:auto}pre code{padding:0;background:none}
.tbl{overflow-x:auto;margin:14px 0}table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line)}
th{font-weight:600;color:var(--ink2);border-bottom:2px solid var(--line)}
.gsearch{width:100%;font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:8px;background:var(--panel);color:var(--ink);margin:6px 0 4px}
footer{border-top:1px solid var(--line);margin-top:56px}footer .wrap{padding:20px 16px 40px;color:var(--muted);font-size:13.5px}
@media (max-width:640px){nav.toc ol{columns:1}}
"""

JS = """
const q=document.getElementById('gq');if(q){q.addEventListener('input',()=>{const v=q.value.toLowerCase();
document.querySelectorAll('#glossary tbody tr').forEach(tr=>{tr.style.display=tr.textContent.toLowerCase().includes(v)?'':'none';});});}
"""


def md(text: str) -> str:
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    return re.sub(r"<table>(.*?)</table>", r'<div class="tbl"><table>\1</table></div>', html, flags=re.S)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def build(src: Path, out: Path) -> Path:
    lines = src.read_text(encoding="utf-8").splitlines()
    head_title = re.sub(r"\*\*", "", lines[2]).strip()
    head_meta = lines[3].strip()
    body = "\n".join(lines[4:])
    sections = re.split(r"\n(?=## )", body.strip())
    toc, parts = [], []
    for sec in sections:
        h = re.match(r"## (.+)", sec)
        if not h:
            parts.append(md(sec))
            continue
        name = h.group(1).strip()
        sid = slug(name)
        toc.append((sid, name))
        html = md(sec).replace(f"<h2>{name}</h2>", f'<h2 id="{sid}">{name}</h2>', 1)
        if name.lower() == "glossary":
            html = html.replace(f'<h2 id="{sid}">{name}</h2>', f'<h2 id="{sid}">{name}</h2><input id="gq" class="gsearch" type="search" '
                                f'placeholder="Filter terms (e.g. tare, credit, on call)" aria-label="Filter glossary"><div id="glossary">', 1) + "</div>"
        parts.append(html)
    toc_html = "".join(f'<li><a href="#{i}">{n}</a></li>' for i, n in toc)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SMART Material Value Engine: start here</title>
<meta name="description" content="Plain-language overview of the Europress x Since AI Hackathon 2026 synthetic dataset">
<style>{CSS}</style></head><body>
<header><div class="wrap"><p class="kicker">{head_meta}</p><h1>{head_title}</h1>
<p class="sub">An overview for everyone: participants, mentors, jury and partners. Then open <code>docs/QUICKSTART_FOR_BUILDERS.md</code>.</p>
<span class="badge">SYNTHETIC DATA</span><span class="badge">ALL PRICES HYPOTHETICAL</span><span class="badge">HUMAN APPROVAL REQUIRED</span></div></header>
<div class="wrap"><nav class="toc" aria-label="Contents"><ol>{toc_html}</ol></nav><main>{''.join(parts)}</main></div>
<footer><div class="wrap">Europress × Since AI Hackathon 2026 · SMART Material Value Engine synthetic data. All data in this package are synthetic and
must not be presented as measurements, prices or savings of any real company, customer, operator or person.</div></footer>
<script>{JS}</script></body></html>"""
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    print(build(Path(a[0]) if a else ROOT / "START_HERE.md", Path(a[1]) if len(a) > 1 else ROOT / "START_HERE.html"))
