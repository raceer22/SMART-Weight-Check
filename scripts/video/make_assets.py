"""Assets for the peer-vote video: app stills with element boxes, the cold-open chart, layered cards, overlays.

Start the app, then run from the repo root:
    streamlit run app/app.py --server.headless true
    python scripts/video/make_assets.py [http://localhost:8501] [--cards-only]

Writes scripts/video/build/assets/*.png, boxes.json (element boxes in the app stills) and parts.json (every
card is a background plus one transparent image per text block, so build_video.py can animate each block on its
word). Needs Playwright with Chromium and an internet connection (Poppins from Google Fonts and GitHub, Vega from
jsDelivr). Synthetic data only.
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from timeline import ASSETS, BUILD, H, VIDEO, W  # noqa: E402

ROOT = VIDEO.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from europress_data.sdk import open_dataset  # noqa: E402

URL = next((a for a in sys.argv[1:] if a.startswith("http")), "http://localhost:8501").rstrip("/")
DPR = 8 / 3                     # app stills: a 1440 px wide page becomes 3840 px, sharp at 2× zoom in a 1920 frame
STORY = "CMP-00046"
AMBER, LINE, BRAND, ACTION, DEEP = "#e09b00", "#0099c7", "#03b4e0", "#0077a6", "#00618a"

FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" '
         'rel="stylesheet">')
CSS = """
*{box-sizing:border-box} html,body{margin:0;padding:0}
body{width:1920px;height:1080px;overflow:hidden;font-family:Poppins,sans-serif;color:#141618;background:#f3f9fc;position:relative}
.none{background:transparent!important}
.light{background:radial-gradient(circle at 88% 8%,rgba(3,180,224,.30),transparent 46%),linear-gradient(135deg,#fff 0%,#e6f6fc 100%)}
.cyan{background:radial-gradient(circle at 86% 12%,rgba(255,255,255,.20),transparent 42%),linear-gradient(135deg,#00618a 0%,#0077a6 48%,#03b4e0 100%);color:#fff}
.pad{position:absolute;inset:0;padding:110px 150px;display:flex;flex-direction:column;justify-content:center}
.eyebrow{font-size:28px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#0077a6;display:flex;align-items:center;gap:16px}
.eyebrow i{width:16px;height:16px;border-radius:50%;background:#03b4e0;display:inline-block}
.cyan .eyebrow{color:#dff4fb} .cyan .eyebrow i{background:#fff}
h1{font-size:132px;line-height:1.04;font-weight:700;margin:26px 0 0;letter-spacing:-.015em}
h1 em{font-style:normal;color:#0077a6} .cyan h1 em{color:#c9f1ff}
.sub{font-size:46px;font-weight:500;color:#5b6670;margin-top:34px;line-height:1.25} .cyan .sub{color:#e9f8fd}
.foot{position:absolute;left:150px;right:150px;bottom:70px;font-size:26px;color:#5b6670} .cyan .foot{color:#d6f1fb}
.steps{display:flex;gap:34px;align-items:stretch;margin-top:60px}
.step{flex:1;background:#fff;border:2px solid #d3e6ee;border-radius:34px;padding:44px 44px 48px;transition:none}
.step .n{width:72px;height:72px;border-radius:50%;background:#e4f3f9;color:#0077a6;font-weight:700;font-size:34px;display:flex;align-items:center;justify-content:center}
.step h2{font-size:64px;margin:30px 0 10px;font-weight:700} .step p{font-size:32px;color:#5b6670;margin:0;line-height:1.35}
.step.on{background:linear-gradient(135deg,#0077a6,#03b4e0);border-color:transparent;color:#fff;box-shadow:0 24px 60px rgba(0,119,166,.28)}
.step.on .n{background:#fff} .step.on p{color:#e9f8fd}
.step.later{opacity:.38}
.figure{display:flex;justify-content:center;margin-top:30px} .figure img{width:1500px}
.spec{display:grid;grid-template-columns:1000px 1fr;gap:70px;align-items:center;margin-top:30px}
.spec img{width:1000px}
.fact{padding:22px 0 24px;border-bottom:2px solid #d3e6ee} .fact:last-child{border-bottom:none}
.fact b{display:block;font-size:66px;line-height:1.05;color:#00618a} .fact span{font-size:28px;color:#5b6670}
.fact.hide{opacity:0}
.price{display:flex;gap:80px;align-items:flex-end;margin-top:40px}
.big{font-size:240px;font-weight:700;line-height:.95;color:#00618a;letter-spacing:-.02em}
.unit{font-size:46px;color:#5b6670;font-weight:500;margin-top:16px}
.value{background:#fff;border-radius:36px;padding:44px 52px;box-shadow:0 24px 60px rgba(0,119,166,.14);max-width:820px}
.value b{display:block;font-size:110px;line-height:1;color:#0077a6}
.value span{display:block;font-size:34px;color:#303133;margin-top:16px;line-height:1.35}
.value small{display:block;font-size:24px;color:#5b6670;margin-top:14px}
.value.hide{opacity:0}
"""


def page_html(body: str, cls: str = "light") -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{CSS}</style><style id="iso"></style></head>'
            f'<body class="{cls}">{body}</body></html>')


def fonts_ready(page) -> None:
    page.evaluate("Promise.all(['400 30px Poppins','500 30px Poppins','600 30px Poppins','700 30px Poppins']"
                  ".map(f => document.fonts.load(f))).then(() => document.fonts.ready)")
    time.sleep(0.3)


def weigh_frame_svg() -> str:
    """The concept illustration in the app palette, as a data URI (deck greens → Europress cyans)."""
    svg = (ROOT / "submission" / "img" / "weigh_frame.svg").read_text()
    for old, new in {"#1f6f5a": ACTION, "#1d2b27": "#141618", "#4a5652": "#4b5963", "#6b7570": "#5b6670",
                     "#9aa39f": "#9aa7b0", "#b9c0bc": "#b9c7cf", "#c9d0cc": "#c9d6dd", "#dfe4e1": "#dbe7ee",
                     "#e6f2ee": "#e4f3f9", "#eef1ef": "#eef4f7", "#f3f5f4": "#f3f7f9", "#f4f6f5": "#f4f8fa"}.items():
        svg = svg.replace(old, new).replace(old.upper(), new)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# ---------------------------------------------------------------- layered cards (rendered at 2×)
def groups() -> dict[str, tuple[str, list[str]]]:
    """Card name → (background, HTML variants). Every [data-part] element becomes its own transparent image."""
    fig = weigh_frame_svg()
    steps = [("Weigh", "every lift, inside the compactor"), ("Check", "against the invoice, the ticket and the contract"),
             ("Decide", "each difference becomes a decision you control")]

    def eyebrow(text: str) -> str:
        return f'<div class="eyebrow" data-part="eyebrow"><i></i>{text}</div>'

    def step_row(active: int, names: list[str]) -> str:
        out = []
        for i, (h, p) in enumerate(steps, 1):
            cls = "on" if i == active else ("later" if i > active else "")
            out.append(f'<div class="step {cls}" data-part="{names[i - 1]}"><div class="n">{"✓" if i < active else i}</div>'
                       f'<h2>{h}</h2><p>{p}</p></div>')
        return '<div class="steps">' + "".join(out) + "</div>"

    facts = [("4", "load cells under the container"), ("0 kg", "resets to zero every time the container leaves"),
             ("±3 %", "accuracy target, on 95 % of loads"), ("€1,200", "fitted in the factory · €3,400 as a retrofit")]
    fact_rows = "".join(f'<div class="fact" data-part="f{i + 1}"><b>{v}</b><span>{t}</span></div>' for i, (v, t) in enumerate(facts))
    big = 'style="margin-top:{}px;font-size:64px;font-weight:600;color:#fff"'
    return {
        "c2a": ("light", [page_html(f'<div class="pad">{eyebrow("Today")}<h1><span data-part="l1">Pay per lift.</span><br>'
                                    '<span data-part="l2a">Pay per </span><em data-part="l2b">tonne.</em></h1></div>')]),
        "c2b": ("light", [page_html(f'<div class="pad">{eyebrow("The catch")}<h1><span data-part="l1">The only scale</span><br>'
                                    '<span data-part="l2a">belongs to the </span><em data-part="l2b">operator.</em></h1></div>')]),
        "c2c": ("cyan", [page_html(f'<div class="pad">{eyebrow("Introducing")}<h1><span data-part="l1">SMART</span><br>'
                                   '<span data-part="l2">Weight Check</span></h1>'
                                   '<div class="sub" data-part="sub">Weigh at source. Check every tonne.</div></div>', "cyan")]),
        "c3a": ("light", [page_html(f'<div class="pad">{eyebrow("1 · Weigh")}<div class="sub" data-part="sub" '
                                    'style="margin-top:14px;color:#141618;font-weight:600">An independent scale inside the compactor</div>'
                                    f'<div class="figure" data-part="fig"><img src="{fig}"></div></div>')]),
        "c3s": ("light", [page_html(f'<div class="pad">{eyebrow("How it works")}{step_row(2, ["s1", "s2on", "s3later"])}</div>'),
                          page_html(f'<div class="pad">{eyebrow("How it works")}{step_row(3, ["s1", "s2done", "s3on"])}</div>')]),
        "c7": ("light", [page_html(f'<div class="pad">{eyebrow("The scale")}<div class="spec"><img data-part="fig" src="{fig}">'
                                   f'<div>{fact_rows}</div></div></div>')]),
        "c8": ("light", [page_html(f'<div class="pad">{eyebrow("The service")}<div class="price"><div>'
                                   '<div class="big" data-part="big">€15</div><div class="unit" data-part="unit">per compactor per month</div></div>'
                                   '<div class="value" data-part="value"><b>≈ 2.4×</b><span>back in value for the typical customer: '
                                   'about €36 per compactor-month</span><small>estimated · our business model · synthetic data</small></div>'
                                   '</div></div>')]),
        "end": ("cyan", [page_html(f'<div class="pad">{eyebrow("SMART Weight Check")}<h1><span data-part="l1">SMART</span><br>'
                                   '<span data-part="l2">Weight Check</span></h1>'
                                   f'<div class="sub" data-part="w1" {big.format(40)}>Weigh at source.</div>'
                                   f'<div class="sub" data-part="w2" {big.format(18)}>Check every tonne.</div></div>'
                                   '<div class="foot" data-part="foot">All data is synthetic · A concept for Europress SMART compactors · '
                                   'Since AI Hackathon 2026</div>', "cyan")]),
        "ov": ("none", [OVERLAY]),
    }


# ---------------------------------------------------------------- overlays (transparent, same 2× space as the cards)
OVERLAY = page_html(
    '<div data-part="amount" style="position:absolute;right:120px;top:170px;background:#fff;border-radius:34px;'
    'padding:34px 46px 38px;box-shadow:0 26px 70px rgba(20,22,24,.16);border:2px solid #f3d9a4">'
    '<div data-part="num" style="font-size:150px;font-weight:700;line-height:1;color:#00618a;letter-spacing:-.02em">€346</div>'
    '<div style="font-size:38px;font-weight:600;color:#141618;margin-top:12px">for nothing</div>'
    '<div style="font-size:28px;color:#5b6670;margin-top:6px">4 trucks · an empty container</div></div>'
    '<div data-part="chip" style="position:absolute;right:56px;top:46px;font-size:24px;font-weight:500;color:#5b6670;'
    'background:rgba(255,255,255,.9);border:1.5px solid #d3e6ee;border-radius:999px;padding:8px 22px">All data is synthetic</div>',
    "none")
COUNT = [round(346 * (1 - (1 - k / 20) ** 3)) for k in range(21)]   # €0 … €346, fast then slow

CURSOR_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="44" height="56" viewBox="0 0 22 28">'
              '<path d="M2 2 L2 22 L7.2 17.4 L10.6 25.6 L14 24.2 L10.6 16.2 L17.6 16.2 Z" fill="#fff" stroke="#141618" '
              'stroke-width="1.6" stroke-linejoin="round"/></svg>')
FONT_FILES = ("Poppins-SemiBold.ttf", "Poppins-Bold.ttf")   # captions and counters drawn with Pillow (OFL)


def fonts() -> None:
    (BUILD / "fonts").mkdir(parents=True, exist_ok=True)
    for name in FONT_FILES:
        if not (BUILD / "fonts" / name).exists():
            urllib.request.urlretrieve(f"https://github.com/google/fonts/raw/main/ofl/poppins/{name}", BUILD / "fonts" / name)


ISO = "[data-part]{visibility:hidden!important}"


def layered(page, name: str, variants: list[str]) -> dict:
    """Screenshot each [data-part] alone on a transparent page; returns {part: box in 2× pixels}."""
    boxes = {}
    for html in variants:
        page.set_content(html)
        fonts_ready(page)
        for part in page.eval_on_selector_all("[data-part]", "els => els.map(e => e.dataset.part)"):
            page.evaluate("""p => { document.getElementById('iso').textContent =
                `body{background:transparent!important} [data-part]{visibility:hidden!important}
                 [data-part='${p}']{visibility:visible!important}`; }""", part)
            if part == "num":
                continue
            b = page.locator(f"[data-part='{part}']").bounding_box()
            x0, y0 = max(0, b["x"] - 60), max(0, b["y"] - 60)
            x1, y1 = min(W, b["x"] + b["width"] + 60), min(H, b["y"] + b["height"] + 60)
            page.screenshot(path=ASSETS / f"p_{name}_{part}.png", omit_background=True,
                            clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})
            boxes[part] = [round(v * 2) for v in (x0, y0, x1, y1)]
        if page.locator("[data-part='num']").count():           # the €346 counter, one image per step
            page.evaluate("""() => { document.getElementById('iso').textContent =
                `body{background:transparent!important} [data-part]{visibility:hidden!important}
                 [data-part='num']{visibility:visible!important}`; }""")
            b = page.locator("[data-part='num']").bounding_box()
            clip = {"x": b["x"] - 10, "y": b["y"] - 10, "width": b["width"] + 20, "height": b["height"] + 20}
            for k, v in enumerate(COUNT):
                page.evaluate(f"() => {{ document.querySelector(\"[data-part='num']\").textContent = '€{v}'; }}")
                page.screenshot(path=ASSETS / f"p_{name}_num{k}.png", omit_background=True, clip=clip)
                boxes[f"num{k}"] = [round(v * 2) for v in (clip["x"], clip["y"], clip["x"] + clip["width"], clip["y"] + clip["height"])]
    return boxes


# ---------------------------------------------------------------- cold-open chart (CMP-00046, July)
def story_data():
    con = open_dataset(ROOT / "data" / "quickstart" / "public")
    con.execute("SET TimeZone='UTC'")
    h = con.sql(f"""SELECT measured_at, fill_pct, CASE WHEN quality_flag = 'VALID' THEN mass_kg END AS mass_kg
                    FROM telemetry_hourly WHERE device_id = '{STORY}'
                    AND measured_at >= '2026-07-01' AND measured_at < '2026-08-01' ORDER BY 1""").df()
    trips = con.sql(f"""SELECT actual_at FROM collection_events WHERE device_id = '{STORY}' AND status = 'WASTED_TRIP'
                        ORDER BY 1""").df()
    con.close()
    loc = lambda s: s.dt.tz_convert("Europe/Helsinki").dt.tz_localize(None)  # noqa: E731
    h = h.assign(t=loc(h.measured_at)).drop(columns="measured_at")
    h = h.set_index("t").resample("3h").max().reset_index()   # 3-hour maxima: the same story, a calmer line
    stuck = h[h.fill_pct >= 80].t
    return h, loc(trips.actual_at), stuck.min(), stuck.max()


def story_chart(variant: int) -> dict:
    h, trips, a, b = story_data()
    x = alt.X("t:T", title=None, scale=alt.Scale(domain=["2026-07-01T00:00:00", "2026-08-01T00:00:00"]),
              axis=alt.Axis(format="%-d %b", tickCount=8, grid=False, labelPadding=10))
    span = pd.DataFrame({"a": [a - pd.Timedelta(hours=6)], "b": [b + pd.Timedelta(hours=6)]})
    trip_df = pd.DataFrame({"t": trips})

    def panel(field, title, top, label_y, label):
        y = alt.Y(f"{field}:Q", title=title, scale=alt.Scale(domain=[0, top]), axis=alt.Axis(tickCount=4, titlePadding=18))
        layers = [alt.Chart(h).mark_area(color=BRAND, opacity=0.12, interpolate="monotone").encode(x=x, y=y),
                  alt.Chart(h).mark_line(color=LINE, strokeWidth=4, interpolate="monotone").encode(x=x, y=y)]
        if label and variant >= label[0]:
            layers.insert(0, alt.Chart(span).mark_rect(color=AMBER, opacity=0.13, stroke=AMBER, strokeWidth=3,
                                                       cornerRadius=8).encode(x="a:T", x2="b:T", y=alt.value(0),
                                                                               y2=alt.value(330)))
            layers.append(alt.Chart(span.assign(y=label_y, txt=label[1])).mark_text(
                color="#8a5a00", fontSize=28, fontWeight=600, align="right", dx=-18).encode(x="a:T", y=alt.Y("y:Q", scale=alt.Scale(domain=[0, top])), text="txt:N"))
        if variant >= 3:
            layers.append(alt.Chart(trip_df).mark_rule(color=AMBER, strokeWidth=4, strokeDash=[10, 6]).encode(x="t:T"))
        return alt.layer(*layers).properties(width=1600, height=330)

    fill = panel("fill_pct", "Fill reading, %", 100, 80, (1, "stuck at 88 %"))
    mass = panel("mass_kg", "Weight in the container, kg", 1600, 200, (2, "20–35 kg"))
    if variant >= 3:
        mass = alt.layer(mass, alt.Chart(pd.DataFrame({"t": [trips.iloc[-1]], "y": [1300], "txt": ["4 trucks · nothing to collect"]}))
                         .mark_text(color="#8a5a00", fontSize=28, fontWeight=600, align="left", dx=18)
                         .encode(x="t:T", y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 1600])), text="txt:N"))
    chart = alt.vconcat(fill, mass, spacing=56).configure(font="Poppins", background="transparent").configure_view(
        stroke=None).configure_axis(labelColor="#5b6670", titleColor="#5b6670", labelFontSize=24, titleFontSize=25,
                                    titleFontWeight=500, gridColor="#e3eef3", domainColor="#c9dbe3", tickColor="#c9dbe3")
    return chart.to_dict()


def story_boxes(page) -> dict:
    """Where each build-up step of the cold-open chart changes the picture, in 2× pixels."""
    v = [np.asarray(Image.open(ASSETS / f"s1_v{k}.png").convert("RGB")).astype(int) for k in range(4)]

    def changed(a, b):
        return np.abs(a - b).sum(axis=2) > 40

    def box(m):
        ys, xs = np.where(m)
        return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]

    out = {"stuck": box(changed(v[0], v[1])), "low": box(changed(v[1], v[2])), "trips": box(changed(v[2], v[3]))}
    y0, y1 = out["low"][1], out["low"][3]
    cols = np.where(changed(v[2], v[3])[y0:y1].sum(axis=0) > 40)[0]
    groups = np.split(cols, np.where(np.diff(cols) > 6)[0] + 1)
    out["trip_x"] = [int(g.mean()) for g in groups if len(g)]
    e = page.locator(".eyebrow").bounding_box()
    out["eyebrow"] = [round(e["x"] * 2), round(e["y"] * 2), round((e["x"] + e["width"]) * 2), round((e["y"] + e["height"]) * 2)]
    return out


def story_html(spec: dict) -> str:
    v, vl, ve = alt.VEGA_VERSION, alt.VEGALITE_VERSION, alt.VEGAEMBED_VERSION
    return (f'<!doctype html><html><head><meta charset="utf-8">{FONTS}<style>{CSS}</style>'
            f'<script src="https://cdn.jsdelivr.net/npm/vega@{v}"></script>'
            f'<script src="https://cdn.jsdelivr.net/npm/vega-lite@{vl}"></script>'
            f'<script src="https://cdn.jsdelivr.net/npm/vega-embed@{ve}"></script></head>'
            '<body class="light"><div style="position:absolute;left:110px;top:58px" class="eyebrow"><i></i>'
            'CMP-00046 · cardboard compactor · Lohja · July 2026</div>'
            '<div id="vis" style="position:absolute;left:70px;top:150px"></div><script>'
            "Promise.all(['400 24px Poppins','500 25px Poppins','600 28px Poppins'].map(f=>document.fonts.load(f)))"
            f".then(()=>vegaEmbed('#vis',{json.dumps(spec)},{{actions:false,renderer:'svg'}})).then(()=>{{window.READY=true}});"
            "</script></body></html>")


# ---------------------------------------------------------------- app stills
def settle(page, extra=2.0):
    page.wait_for_selector(".hero", timeout=120_000)
    page.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=120_000)
    time.sleep(extra)


TEXT_BOX_JS = """([el, s]) => { const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let n;
  while ((n = w.nextNode())) { const i = n.data.indexOf(s); if (i >= 0) { const r = document.createRange();
    r.setStart(n, i); r.setEnd(n, i + s.length); const b = r.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; } }
  return null; }"""


def app_stills(browser) -> dict:
    boxes: dict[str, dict] = {}

    def bx(loc):
        b = loc.bounding_box()
        return [round(v * DPR, 1) for v in (b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"])]

    def tb(loc, s):
        r = loc.evaluate(f"(el, s) => ({TEXT_BOX_JS})([el, s])", s)
        return [round(v * DPR, 1) for v in r]

    def card(page, text):
        return page.locator("[class*='st-key-card_']", has_text=text).first

    def new(height):
        ctx = browser.new_context(viewport={"width": 1440, "height": height}, device_scale_factor=DPR)
        p = ctx.new_page()
        p.goto(URL + "/")
        settle(p, 3)
        return p

    # A · the inbox as it opens (also the "after Undo" state)
    p = new(1700)
    c42, c46 = card(p, "shared trucks split equally"), card(p, "trucks came for nothing")
    boxes["inbox"] = {"hero": bx(p.locator(".hero")), "h1": bx(p.locator(".hero h1")), "tiles": bx(p.locator(".tiles")),
                      "tile_q": bx(p.locator(".tile").first), "section": bx(p.locator(".section").first),
                      "sub25": tb(p.locator(".hero"), "25 compactors at 8 sites"),
                      "h1t": tb(p.locator(".hero h1"), "40 decisions are waiting for you."),
                      "card42": bx(c42), "stake42": bx(c42.locator(".stake")), "why42": bx(c42.get_by_role("button", name="Why?")),
                      "t294": tb(c42, "2.94 t"), "t580": tb(c42, "580 kg"),
                      "card46": bx(c46), "why46": bx(c46.get_by_role("button", name="Why?"))}
    p.screenshot(path=ASSETS / "app_inbox.png")

    # B · Why? on the shared truck: the weight table
    c42.get_by_role("button", name="Why?").click()
    settle(p)
    c42 = card(p, "shared trucks split equally")
    boxes["why42"] = {"card42": bx(c42), "table": bx(c42.locator("[data-testid='stDataFrame']").first),
                      "lines": bx(c42.locator(".lines"))}
    p.screenshot(path=ASSETS / "app_why42.png")
    p.context.close()

    # C · Why? on the story compactor: charts with the wasted trips in amber
    p = new(2000)
    card(p, "trucks came for nothing").get_by_role("button", name="Why?").click()
    settle(p)
    c46 = card(p, "trucks came for nothing")
    charts = c46.locator("[data-testid='stVegaLiteChart']")
    boxes["why46"] = {"card46": bx(c46), "lines": bx(c46.locator(".lines")), "chart_fill": bx(charts.nth(0)),
                      "chart_mass": bx(charts.nth(1)), "approve": bx(c46.get_by_role("button", name="Approve"))}
    p.screenshot(path=ASSETS / "app_why46.png")

    # D · Approve: the counter, the toast and the sent row
    c46.get_by_role("button", name="Approve").click()
    settle(p, 0.8)
    sent = p.locator("[class*='st-key-card_'][class*='_approved']").first
    boxes["approved"] = {"tiles": bx(p.locator(".tiles")), "tile_sent": bx(p.locator(".tile.sent")),
                         "hero": bx(p.locator(".hero")), "sent_row": bx(sent),
                         "undo": bx(sent.get_by_role("button", name="Undo"))}
    toast = p.locator("[data-testid='stToast']")
    if toast.count():
        boxes["approved"]["toast"] = bx(toast.first)
    p.screenshot(path=ASSETS / "app_approved.png")
    p.context.close()

    # amber columns in the story charts (the wasted trips), found from the pixels
    img = np.asarray(Image.open(ASSETS / "app_why46.png").convert("RGB")).astype(int)
    for name in ("chart_fill", "chart_mass"):
        x0, y0, x1, y1 = (int(v) for v in boxes["why46"][name])
        r, g, b = (img[y0:y1, x0:x1, i] for i in range(3))
        amber = (r > 190) & (g > 120) & (g < 185) & (b < 80)
        cols = np.where(amber.sum(axis=0) > 20)[0]
        rows = np.where(amber.sum(axis=1) > 0)[0]
        boxes["why46"][name + "_amber"] = [x0 + cols.min(), y0 + rows.min(), x0 + cols.max(), y0 + rows.max()] if len(cols) else None
    return boxes


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    fonts()
    layout = {"groups": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # cold-open chart, four build-up variants
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=2, timezone_id="UTC")
        page = ctx.new_page()
        for v in range(4):
            page.set_content(story_html(story_chart(v)))
            page.wait_for_function("window.READY === true", timeout=60_000)
            time.sleep(0.5)
            page.screenshot(path=ASSETS / f"s1_v{v}.png")
        layout["s1"] = story_boxes(page)

        # layered cards: one background per colour, then every text block on its own
        for cls in ("light", "cyan"):
            page.set_content(page_html("", cls))
            page.screenshot(path=ASSETS / f"bg_{cls}.png")
        for name, (bg, variants) in groups().items():
            layout["groups"][name] = {"bg": bg, "parts": layered(page, name, variants)}
        ctx.close()

        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1)
        page = ctx.new_page()
        page.set_content(page_html(f'<div id="cur" style="position:absolute;left:10px;top:10px">{CURSOR_SVG}</div>', "none"))
        page.locator("#cur").screenshot(path=ASSETS / "cursor.png", omit_background=True)
        ctx.close()
        (ASSETS / "parts.json").write_text(json.dumps(layout, indent=1))

        if "--cards-only" not in sys.argv:          # keep the app stills and boxes.json from the last full run
            boxes = app_stills(browser)
            (ASSETS / "boxes.json").write_text(json.dumps(boxes, indent=1, default=float))
        browser.close()
    print("assets in", ASSETS, "·", len(list(ASSETS.glob("*.png"))), "images")


if __name__ == "__main__":
    main()
