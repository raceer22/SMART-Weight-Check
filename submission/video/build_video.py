"""Render the peer-vote video from the assets and the ElevenLabs audio.

    python submission/video/make_assets.py http://localhost:8501         # once, with the app running
    python submission/video/build_video.py [--out NAME] [--preview]       # → submission/video/build/NAME.mp4
    python submission/video/build_video.py --stills 3.2,14.0              # single frames → build/stills/

Every frame is composed with Pillow. The camera holds each framing still, snaps or glides to the next one on the
spoken words and shakes briefly on the four big impacts. The video opens on the chart's blank background and fades
the chart in. Scenes change with whip pans, zooms and a window fly-in; card text slides, pops or slams in word by
word; captions highlight the word being spoken; a thin bar shows progress. Fast movement gets motion blur from
sub-frames. The voice clips, music, clicks and the sound effects (sfx.py, placed from the same shot list) are mixed
with ffmpeg. A full render also writes NAME_thumbnail.png (the finished July chart with €346) to upload as the
video's thumbnail. --preview renders 960×540 at 15 fps.
Synthetic data only.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from multiprocessing import get_context
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sfx  # noqa: E402
from timeline import (AMOUNT_AT, ASSETS, AUDIO, BUILD, FPS, START, TOTAL, H, W, caption_spans,  # noqa: E402
                      caption_tokens, cue)

S = START
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")  # needs libx264 for the best quality; falls back to OpenH264
AMBER, CYAN, INK = (224, 155, 0), (3, 180, 224), (20, 22, 24)
BOX = json.loads((ASSETS / "boxes.json").read_text())
LAYOUT = json.loads((ASSETS / "parts.json").read_text())
GROUPS, S1 = LAYOUT["groups"], LAYOUT["s1"]
CARD = (2 * W, 2 * H)          # cards, overlays and the cold-open chart are rendered at 2×
SHUTTER = 0.5                  # motion blur: half a frame


# ---------------------------------------------------------------- easing and rectangles
def cl(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def smooth(x):
    x = cl(x)
    return x * x * (3 - 2 * x)


def out_cubic(x):
    return 1 - (1 - cl(x)) ** 3


def in_cubic(x):
    return cl(x) ** 3


def in_out_cubic(x):
    x = cl(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def in_out_quint(x):
    x = cl(x)
    return 16 * x ** 5 if x < 0.5 else 1 - (-2 * x + 2) ** 5 / 2


def out_back(x, s=1.9):
    x = cl(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


EASE = {"snap": in_out_quint, "glide": in_out_cubic, "out": out_cubic}


def clamp(r, size):
    """Keep a 16:9 camera rect inside the image, shrinking it if it is too big."""
    x0, y0, x1, y1 = r
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    k = min(1.0, size[0] / w, size[1] / h)
    w, h = w * k, h * k
    x0, y0 = min(max(cx - w / 2, 0), size[0] - w), min(max(cy - h / 2, 0), size[1] - h)
    return (x0, y0, x0 + w, y0 + h)


def fit(box, size, pad=0.08, zoom=1.0):
    """16:9 camera rect around a box (source pixels), padded, clamped inside the image."""
    x0, y0, x1, y1 = box
    w, h = (x1 - x0) * (1 + 2 * pad), (y1 - y0) * (1 + 2 * pad)
    if w / h < W / H:
        w = h * W / H
    else:
        h = w * H / W
    w, h = w / zoom, h / zoom
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return clamp((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), size)


def full(size, zoom=1.0, cx=0.5, cy=0.5):
    w, h = size[0] / zoom, size[0] / zoom * H / W
    return clamp((cx * size[0] - w / 2, cy * size[1] - h / 2, cx * size[0] + w / 2, cy * size[1] + h / 2), size)


def zoom_rect(r, f, size, fx=0.5, fy=0.5):
    """Zoom a camera rect by f (>1 = closer) around a point given as fractions of the rect."""
    x0, y0, x1, y1 = r
    px, py = x0 + (x1 - x0) * fx, y0 + (y1 - y0) * fy
    w, h = (x1 - x0) / f, (y1 - y0) / f
    return clamp((px - w * fx, py - h * fy, px - w * fx + w, py - h * fy + h), size)


def lerp(a, b, k):
    return tuple(p + (q - p) * k for p, q in zip(a, b))


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def grow(b, dx, dy=None):
    dy = dx if dy is None else dy
    return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy]


# ---------------------------------------------------------------- beats: shakes, sound effects
SHAKE: list = []    # (t, amplitude in 1920-wide pixels)
EVENTS: list = []   # (t, sound, gain dB, mirror stereo)
GAIN = {"whoosh": -9, "swish": -18, "swoosh": -24, "pop": -19, "impact": -10, "thump": -14, "riser": -14,   # dB on a
        "ticker": -17, "click": -14}                                                                   # −1 dBFS peak


def fx(t, sound, gain=None, flip=False):
    EVENTS.append((round(t, 3), sound, GAIN[sound] if gain is None else gain, flip))


def shake(t):
    """Decaying camera shake; 8 and 11 Hz stay under 15 Hz, the fastest a 30 fps video shows without aliasing."""
    dx = dy = 0.0
    for ts, a in SHAKE:
        x = t - ts
        if 0 <= x < 0.7:
            d = a * math.exp(-x / 0.14)
            dx += d * math.sin(2 * math.pi * 8 * x + 1.3)
            dy += d * math.sin(2 * math.pi * 11 * x + 0.2)
    return dx, dy


# ---------------------------------------------------------------- shots
def K(t, rect, move=None, ease="snap"):
    """Camera keyframe: arrive at `rect` at time t after a move of `move` seconds; then hold until the next one."""
    return (t, rect, move, ease)


@dataclass
class Shot:
    src: str                 # a still ("app_inbox", "s1_v2") or a layered card ("card:c2a")
    t0: float                # when it starts to enter
    keys: list               # K(...) camera keyframes in source pixels
    trans: tuple = ("cut", 0.0)   # how it enters: cut | fade d | whip d (dx, dy) | zoom d focus | window d | wipe d (x0, x1)
    hl: list = field(default_factory=list)      # (on, off, box) amber highlights
    clicks: list = field(default_factory=list)  # (t, (x, y)) cursor clicks
    parts: list = field(default_factory=list)   # (part, t_in, anim[, t_out[, sound]]) for layered cards
    layers: list = field(default_factory=list)  # overlays in frame space (dicts, see draw_layers)
    move: float = 0.55

    @property
    def size(self):
        return CARD if self.src.startswith("card:") else IMG[self.src].size

    def rect(self, t):
        ta, ra, *_ = self.keys[0]
        for tb, rb, mv, ease in self.keys[1:]:
            start = max(ta, tb - (mv or self.move))
            if t < start:
                return ra
            if t < tb:
                return lerp(ra, rb, EASE[ease]((t - start) / (tb - start)))
            ta, ra = tb, rb
        return ra

    def cam(self, t):
        r = self.rect(t)
        dx, dy = shake(t)
        if dx or dy:
            k = (r[2] - r[0]) / W
            r = clamp((r[0] + dx * k, r[1] + dy * k, r[2] + dx * k, r[3] + dy * k), self.size)
        return r


def shots() -> list[Shot]:
    out: list[Shot] = []

    # 1 · the chart fades in on its own blank background, then builds up ------------------------------------
    s1 = IMG["s1_v0"].size
    T = S[1]
    eyebrow_view = fit([S1["eyebrow"][0], S1["eyebrow"][1] - 40, S1["eyebrow"][2] + 300, S1["eyebrow"][3] + 420], s1, pad=0.04)
    st, lo = S1["stuck"], S1["low"]
    fill_view = fit([st[0] - 500, st[1] - 120, st[2] + 900, st[3] + 140], s1, pad=0.04)
    mass_view = fit([lo[0] - 620, lo[1] - 120, lo[2] + 900, lo[3] + 140], s1, pad=0.04)
    trips_view = full(s1, 1.04, cx=0.47, cy=0.5)
    amount_t = T + AMOUNT_AT                                 # "three hundred and forty-six" (whisper is late on numbers)
    hit = amount_t + 0.6                                     # the counter lands
    cam1 = [K(0, eyebrow_view),
            K(cue(1, "its") - 0.1, full(s1), move=1.2, ease="glide"),
            K(cue(1, "froze", "stuck") + 0.02, fill_view, move=0.5),
            K(cue(1, "scale") + 0.15, mass_view, move=0.45),
            K(cue(1, "four") + 0.1, trips_view, move=0.55),
            K(hit, full(s1, 1.12, cx=0.4, cy=0.66), move=0.45)]
    chip = dict(part="chip", t=cue(1, "its") - 0.1, anim="pop")      # after the opening close-up on the label
    reveal = [chip, dict(part="amount", t=amount_t, anim="pop"),
              dict(part="num", t=amount_t, anim="pop", pivot="amount", count=(amount_t + 0.05, 0.55))]
    out.append(Shot("bg_light", 0, cam1))                   # the chart's background with nothing on it
    out.append(Shot("s1_v0", 0.2, cam1, trans=("fade", 0.5), layers=[chip]))
    out.append(Shot("s1_v1", cue(1, "froze", "stuck") + 0.04, cam1, trans=("fade", 0.15), layers=[chip]))
    out.append(Shot("s1_v2", cue(1, "scale") + 0.17, cam1, trans=("fade", 0.15), layers=[chip]))
    x0, x1, wipe = S1["trips"][0] - 60, S1["trips"][2] + 40, 1.25
    t_wipe = cue(1, "four") + 0.15
    out.append(Shot("s1_v3", t_wipe, cam1, trans=("wipe", wipe, (x0, x1)), layers=reveal))
    for x in S1["trip_x"][:4]:                               # a hit as each wasted trip appears
        fx(t_wipe + wipe * (x - x0) / (x1 - x0) - 0.02, "thump", -16)
    SHAKE.append((hit, 11))
    fx(amount_t, "pop", -16)
    fx(amount_t + 0.05, "ticker")
    fx(hit - 0.02, "impact")

    # 2 · the problem, then the name ----------------------------------------------------------------------
    T = S[2]
    out.append(Shot("card:c2a", T - 0.2, [K(T - 0.2, full(CARD, 1.1, cx=0.4, cy=0.53))], trans=("whip", 0.4, (-1, 0)),
                    parts=[("eyebrow", T - 0.05, "left"), ("l1", cue(2, "pay") - 0.08, "up"),
                           ("l2a", cue(2, "by", n=1) - 0.08, "up"), ("l2b", cue(2, "ton"), "pop")]))
    t = cue(2, "but") - 0.15
    out.append(Shot("card:c2b", t, [K(t, full(CARD))], trans=("whip", 0.4, (0, -1)),   # "operator." runs to the edge
                    parts=[("eyebrow", t + 0.05, "left"), ("l1", cue(2, "only") - 0.1, "up"),
                           ("l2a", cue(2, "belongs") - 0.1, "up"), ("l2b", cue(2, "operator"), "pop")]))
    t = cue(2, "so") - 0.1
    out.append(Shot("card:c2c", t, [K(t, full(CARD, 1.06, cx=0.4, cy=0.5))],
                    trans=("zoom", 0.4, center(GROUPS["c2b"]["parts"]["l2b"])),
                    parts=[("eyebrow", t + 0.15, "left"), ("l1", cue(2, "smart"), "slam"),
                           ("l2", cue(2, "weight"), "slam", None, "thump"), ("sub", cue(2, "check") + 0.15, "up")]))
    SHAKE.append((cue(2, "smart") + 0.2, 9))
    fx(t - 1.4 + 0.15, "riser")

    # 3 · weigh, check, decide ------------------------------------------------------------------------------
    T = S[3]
    out.append(Shot("card:c3a", T - 0.2, [K(T - 0.2, full(CARD)), K(cue(3, "weighs"), fit([700, 850, 3000, 1650], CARD, pad=0.02)),
                                          K(cue(3, "our") - 0.5, full(CARD, 1.15, cy=0.6), move=0.8, ease="glide")],
                    trans=("whip", 0.4, (-1, 0)),
                    parts=[("eyebrow", T - 0.05, "left"), ("sub", T + 0.05, "up"), ("fig", cue(3, "scale") - 0.1, "up")]))
    sp = GROUPS["c3s"]["parts"]

    def step_view(name):
        return full(CARD, 1.2, cx=center(sp[name])[0] / CARD[0], cy=0.55)
    t, turns = cue(3, "our") - 0.15, cue(3, "turns")
    out.append(Shot("card:c3s", t, [K(t, full(CARD)), K(cue(3, "checks"), step_view("s2on")), K(turns + 0.1, step_view("s3on"))],
                    trans=("whip", 0.4, (0, -1)),
                    parts=[("eyebrow", t + 0.05, "left"), ("s1", t + 0.1, "up"), ("s2on", cue(3, "checks") - 0.15, "up", turns),
                           ("s3later", cue(3, "checks") + 0.25, "up", turns, ""), ("s2done", turns, "fade", None, ""),
                           ("s3on", turns, "pop")]))

    # 4 + 5 · the inbox flies in, then the shared truck (one continuous camera on the inbox still) ------------
    a, ib = IMG["app_inbox"].size, BOX["inbox"]
    T = S[4]
    cw = (3253 - 586) * 1.04
    cards_view = (1919.5 - cw / 2, 1060, 1919.5 + cw / 2, 1060 + cw * H / W)   # top edge just under the header
    card42_all = fit(ib["card42"], a, pad=0.03)
    y_line = center(ib["t294"])[1]

    def line_view(cx, w=1500):
        return clamp((cx - w / 2, y_line - w * H / W / 2, cx + w / 2, y_line + w * H / W / 2), a)
    t294, t580, two = cue(5, "2"), cue(5, "580"), cue(5, "two")
    click42 = two + 0.45
    out.append(Shot("app_inbox", T - 0.3,
                    [K(T - 0.3, fit(ib["hero"], a, pad=0.03)),
                     K(cue(4, "25") - 0.05, fit(grow(ib["sub25"], 700, 250), a, pad=0)),
                     K(cue(4, "every"), fit(ib["h1t"], a, pad=0.1)),
                     K(cue(4, "ranked") + 0.1, fit(ib["tile_q"], a, pad=0.18)),
                     K(cue(4, "biggest"), cards_view),
                     K(S[5] + 0.15, card42_all, move=0.45),
                     K(t294 - 0.05, line_view(center(ib["t294"])[0] - 150), move=0.5),
                     K(t580 - 0.05, line_view(center(ib["t580"])[0] - 50), move=0.35),
                     K(two - 0.15, card42_all, move=0.5)],
                    trans=("window", 1.0),
                    hl=[(cue(4, "25"), cue(4, "every") - 0.15, ib["sub25"]), (cue(4, "money"), cue(4, "biggest") - 0.1, ib["tile_q"]),
                        (cue(4, "first"), S[5] + 0.2, ib["stake42"]), (t294, two + 0.3, ib["t294"]), (t580, two + 0.3, ib["t580"])],
                    clicks=[(click42, center(ib["why42"]))]))
    tb = BOX["why42"]["table"]
    row = (3376, 3470)
    cell = {"container": [846, row[0], 1320, row[1]], "invoiced": [1548, row[0], 1826, row[1]],
            "stake": [1826, row[0], 2086, row[1]], "why": [2086, row[0], tb[2], row[1]]}
    t = click42 + 0.05
    split, this = cue(5, "split"), cue(5, "this")
    out.append(Shot("app_why42", t, [K(t, card42_all), K(t + 0.75, fit([tb[0], tb[1] - 260, tb[2], tb[3] + 40], IMG["app_why42"].size, pad=0.04)),
                                     K(this, fit([1100, 3280, 2800, 3570], IMG["app_why42"].size, pad=0.06), move=0.45)],
                    trans=("fade", 0.1),
                    hl=[(t + 0.8, split - 0.1, cell["container"]), (t + 1.0, split - 0.1, cell["invoiced"]),
                        (split, this - 0.1, cell["why"]), (this, S[6], cell["stake"])]))

    # 6 · Why? on the story compactor, Approve, Undo -------------------------------------------------------
    T = S[6]
    w46, ap = BOX["why46"], BOX["approved"]
    c46_closed = fit(ib["card46"], a, pad=0.05)
    why = cue(6, "why")
    out.append(Shot("app_inbox", T - 0.25, [K(T - 0.25, c46_closed)], trans=("whip", 0.4, (0, -1)),
                    clicks=[(why + 0.1, center(ib["why46"]))]))
    a46 = IMG["app_why46"].size
    charts_view = fit([586, w46["card46"][1], 3253, w46["chart_fill"][3] + 60], a46, pad=0.03)

    def column(r, chart):
        return [r[0] - 70, chart[1] + 4, r[2] + 70, r[3] + 12]
    fill_col, mass_col = column(w46["chart_fill_amber"], w46["chart_fill"]), column(w46["chart_mass_amber"], w46["chart_mass"])
    approve, every2 = cue(6, "approve"), cue(6, "every", n=1)
    t = why + 0.15
    out.append(Shot("app_why46", t, [K(t, c46_closed), K(t + 0.8, charts_view),
                                     K(cue(6, "frozen"), fit([600, 3600, 1900, 4200], a46, pad=0.04), move=0.45),
                                     K(cue(6, "empty"), fit([1900, 3600, 3200, 4200], a46, pad=0.04), move=0.4),
                                     K(cue(6, "every") + 0.1, charts_view, move=0.45),
                                     K(approve - 0.05, fit([1700, 2880, 3253, 3110], a46, pad=0.12), move=0.45)],
                    trans=("fade", 0.1),
                    hl=[(cue(6, "frozen"), approve - 0.45, fill_col), (cue(6, "empty"), approve - 0.45, mass_col)],
                    clicks=[(approve + 0.3, center(w46["approve"]))]))
    aa = IMG["app_approved"].size
    row_view = fit(ap["sent_row"], aa, pad=0.05)
    t = approve + 0.4
    undo = cue(6, "undone") - 0.25
    out.append(Shot("app_approved", t, [K(t, fit(ap["tile_sent"], aa, pad=0.35)), K(every2 - 0.1, row_view, move=0.5)],
                    trans=("whip", 0.35, (0, 1)),
                    hl=[(t + 0.3, every2 - 0.35, ap["tile_sent"])], clicks=[(undo, center(ap["undo"]))]))
    out.append(Shot("app_inbox", undo + 0.1, [K(undo + 0.1, fit(ap["sent_row"], a, pad=0.05))], trans=("fade", 0.1)))

    # 7 · the scale, fact by fact ---------------------------------------------------------------------------
    T = S[7]
    c7 = GROUPS["c7"]["parts"]

    def fact_view(k):
        return full(CARD, 1.15, cx=0.6, cy=center(c7[f"f{k}"])[1] / CARD[1])
    beats = [cue(7, "four"), cue(7, "every", "rechecks"), cue(7, "accurate", "target"), cue(7, "1200", "twelve")]
    out.append(Shot("card:c7", T - 0.2,
                    [K(T - 0.2, fit(grow(c7["fig"], -120), CARD, pad=0.02)), K(beats[0] - 0.05, full(CARD, 1.04), move=0.6),
                     K(beats[1], fact_view(2)), K(beats[2], fact_view(3)), K(beats[3], fact_view(4)),
                     K(cue(7, "factory"), full(CARD, 1.03), move=0.7, ease="glide")],
                    trans=("whip", 0.4, (-1, 0)),
                    parts=[("eyebrow", T - 0.05, "left"), ("fig", T, "up")] + [(f"f{k + 1}", b - 0.05, "right") for k, b in enumerate(beats)]))

    # 8 · price, then the end card --------------------------------------------------------------------------
    T = S[8]
    c8 = GROUPS["c8"]["parts"]
    out.append(Shot("card:c8", T - 0.2, [K(T - 0.2, fit([180, 560, 2000, 1700], CARD, pad=0.05)),
                                         K(cue(8, "in") - 0.1, full(CARD, 1.06, cx=0.48, cy=0.55))],
                    trans=("whip", 0.4, (0, -1)),
                    parts=[("eyebrow", T - 0.05, "left"), ("big", cue(8, "15"), "slam"), ("unit", cue(8, "per") - 0.05, "up"),
                           ("value", cue(8, "in") + 0.1, "up")]))
    SHAKE.append((cue(8, "15") + 0.2, 7))
    t = cue(8, "smart") - 0.45
    fx(t - 1.4 + 0.2, "riser")
    out.append(Shot("card:end", t, [K(t, full(CARD))], trans=("zoom", 0.4, center(c8["value"])),
                    parts=[("eyebrow", t + 0.1, "left"), ("l1", cue(8, "smart"), "slam"), ("l2", cue(8, "weight") + 0.12, "slam", None, "thump"),
                           ("w1", cue(8, "weigh", n=1) - 0.05, "up"), ("w2", cue(8, "check", n=1) - 0.05, "up"),
                           ("foot", cue(8, "ton") + 0.3, "fade")]))
    SHAKE.append((cue(8, "smart") + 0.2, 8))
    return sorted(out, key=lambda s: s.t0)


SOUND_OF = {"up": "swoosh", "left": "swoosh", "right": "swoosh", "pop": "pop", "slam": "impact"}


def auto_sounds() -> None:
    """Sound effects that follow from the shot list: transitions, camera snaps, text, highlights, clicks."""
    seen = set()                                     # shots that share one camera (the chart build-up) swish once
    for s in SHOTS:
        kind = s.trans[0]
        if kind == "whip":
            fx(s.t0 - 0.08, "whoosh", flip=s.trans[2][0] > 0 or s.trans[2][1] > 0)
        elif kind in ("zoom", "window"):
            fx(s.t0 - 0.1, "whoosh", -8 if kind == "zoom" else -10)
        for (ta, ra, *_), (tb, rb, mv, ease) in ([] if id(s.keys) in seen else zip(s.keys, s.keys[1:])):
            mv = mv or s.move
            wa, wb = ra[2] - ra[0], rb[2] - rb[0]
            size = abs(center(ra)[0] - center(rb)[0]) / wa + abs(center(ra)[1] - center(rb)[1]) / wa + abs(math.log(wb / wa))
            if ease == "snap" and mv <= 0.8 and size > 0.6 and tb - mv > s.t0 + 0.3:      # big camera snaps only
                fx(tb - mv * 0.85, "swish", GAIN["swish"] + (3 if size > 0.9 else 0), flip=center(rb)[0] < center(ra)[0])
        seen.add(id(s.keys))
        for p in s.parts:
            name, t_in, anim = p[:3]
            sound = p[4] if len(p) > 4 else SOUND_OF.get(anim)
            if sound and t_in - s.t0 >= 0.3:
                fx(t_in + (0.18 if anim == "slam" else 0.0), sound, -12 if sound == "thump" else None)
        for on, *_ in s.hl:
            fx(on, "pop", -22)
        for tc, _ in s.clicks:
            fx(tc - 0.02, "click")
    thin_swishes()


def thin_swishes(before=1.5, after=0.6) -> None:
    """Camera snaps are the most frequent and least meaningful sound: drop a swish that another whoosh-type sound
    precedes by under `before` seconds or follows within `after`."""
    others = [t for t, name, *_ in EVENTS if name in ("whoosh", "swoosh")]
    kept, out = [], []
    for e in sorted(EVENTS):
        if e[1] == "swish":
            if any(-after < e[0] - x < before for x in others + kept):
                continue
            kept.append(e[0])
        out.append(e)
    EVENTS[:] = out


# ---------------------------------------------------------------- drawing
IMG: dict[str, Image.Image] = {}
SHOTS: list[Shot] = []
CAPS = caption_spans()
TOKS = caption_tokens()
CAP_LAYOUT: dict = {}
OUT_W, OUT_H, RENDER_FPS = W, H, FPS
SHADOW = None


def px(v: float) -> float:
    """A length given for a 1920-wide frame, in output pixels."""
    return v * OUT_W / W


def to_out(pt, r):
    return ((pt[0] - r[0]) * OUT_W / (r[2] - r[0]), (pt[1] - r[1]) * OUT_H / (r[3] - r[1]))


def crop(img, r, fast):
    return img.resize((OUT_W, OUT_H), Image.BILINEAR if fast else Image.BICUBIC, box=r, reducing_gap=None if fast else 2.0)


ANIM = {"up": 0.55, "left": 0.5, "right": 0.5, "pop": 0.45, "slam": 0.34, "fade": 0.3, "none": 0.0}


def part_state(anim, x):
    """(dx, dy, scale, alpha) x seconds after a part starts entering; dx, dy in 2× pixels. None before it enters."""
    if x < 0:
        return None
    d = ANIM[anim]
    if d == 0 or x >= d:
        return 0.0, 0.0, 1.0, 1.0
    p = x / d
    e = out_cubic(p)
    if anim == "up":
        return 0.0, 120 * (1 - e), 1.0, smooth(p / 0.6)
    if anim in ("left", "right"):
        return (-200 if anim == "left" else 200) * (1 - e), 0.0, 1.0, smooth(p / 0.5)
    if anim == "pop":
        return 0.0, 0.0, 0.5 + 0.5 * out_back(p), smooth(p / 0.3)
    if anim == "slam":
        return 0.0, 0.0, 2.0 - e, smooth(p / 0.4)
    return 0.0, 0.0, 1.0, smooth(p)


def paste_part(frame, img, box, r, dx, dy, s, a, fast, pivot=None):
    """Draw a part (its box in source pixels) through camera rect r, moved, scaled about its centre (or a pivot)."""
    if a <= 0.004:
        return
    cx, cy = center(box)
    if pivot is not None:
        pcx, pcy = center(pivot)
        cx, cy = pcx + (cx - pcx) * s, pcy + (cy - pcy) * s
    hw, hh = (box[2] - box[0]) * s / 2, (box[3] - box[1]) * s / 2
    p0, p1 = to_out((cx + dx - hw, cy + dy - hh), r), to_out((cx + dx + hw, cy + dy + hh), r)
    ox, oy = math.floor(max(0, p0[0])), math.floor(max(0, p0[1]))
    ex, ey = math.ceil(min(OUT_W, p1[0])), math.ceil(min(OUT_H, p1[1]))
    if ex - ox < 1 or ey - oy < 1:
        return
    kx, ky = img.width / (p1[0] - p0[0]), img.height / (p1[1] - p0[1])
    sb = (max(0.0, (ox - p0[0]) * kx), max(0.0, (oy - p0[1]) * ky),
          min(img.width, (ex - p0[0]) * kx), min(img.height, (ey - p0[1]) * ky))
    im = img.resize((ex - ox, ey - oy), Image.BILINEAR if fast else Image.BICUBIC, box=sb)
    if a < 0.997:
        im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
    frame.paste(im, (ox, oy), im)


def highlight(frame, box_out, alpha, s=1.0):
    """Amber rounded box, drawn at 2× and scaled down for smooth edges."""
    x0, y0, x1, y1 = box_out
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = (x1 - x0) / 2 * s + px(10), (y1 - y0) / 2 * s + px(10)
    x0, y0, x1, y1 = cx - hw, cy - hh, cx + hw, cy + hh
    w, h = int(x1 - x0) + 8, int(y1 - y0) + 8
    if w <= 8 or h <= 8 or w > 3 * OUT_W:
        return
    k = 2
    layer = Image.new("RGBA", (w * k, h * k), (0, 0, 0, 0))
    r, lw = int(px(16) * k), max(2, int(px(5) * k))
    ImageDraw.Draw(layer).rounded_rectangle([4 * k, 4 * k, (w - 4) * k, (h - 4) * k], radius=r, fill=AMBER + (int(30 * alpha),),
                                            outline=AMBER + (int(255 * alpha),), width=lw)
    layer = layer.resize((w, h), Image.LANCZOS)
    frame.paste(layer, (int(x0) - 4, int(y0) - 4), layer)


def cursor(frame, shot, t, r):
    for tc, pt in shot.clicks:
        if not (tc - 0.8 <= t <= tc + 0.5):
            continue
        tx, ty = to_out(pt, r)
        start = (tx + px(300), ty + px(190))
        k = out_cubic((t - (tc - 0.7)) / 0.55)
        x, y = start[0] + (tx - start[0]) * k, start[1] + (ty - start[1]) * k
        if t >= tc:                                    # click ripple
            p = (t - tc) / 0.45
            if p < 1:
                rad = px(14 + 44 * p)
                ring = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                ImageDraw.Draw(ring).ellipse([tx - rad, ty - rad, tx + rad, ty + rad], outline=CYAN + (int(230 * (1 - p)),),
                                             width=max(2, int(px(5))))
                frame.paste(ring, (0, 0), ring)
        press = 0.88 if tc <= t < tc + 0.12 else 1.0
        cur = IMG["cursor"]
        cur = cur.resize((max(1, int(cur.width * OUT_W / W * press)), max(1, int(cur.height * OUT_W / W * press))), Image.LANCZOS)
        frame.paste(cur, (int(x - px(6)), int(y - px(6))), cur)


def draw_layers(frame, shot, t, fast):
    """Overlays in frame space (the €346 card, its counter, the synthetic-data chip). They shake with the camera."""
    dx, dy = shake(t)
    r = (2 * dx, 2 * dy, CARD[0] + 2 * dx, CARD[1] + 2 * dy)
    parts = GROUPS["ov"]["parts"]
    for L in shot.layers:
        stt = part_state(L["anim"], t - L["t"])
        if stt is None:
            continue
        mx, my, s, a = stt
        if L.get("out") is not None and t >= L["out"]:
            q = (t - L["out"]) / 0.3
            a *= 1 - smooth(q)
            if L.get("out_anim") == "grow":
                s *= 1 + 0.35 * out_cubic(q)
        name = L["part"]
        if "count" in L:
            c0, dur = L["count"]
            name = f"num{min(20, max(0, int(21 * (t - c0) / dur)))}"
        pivot = parts[L["pivot"]] if L.get("pivot") else None
        paste_part(frame, IMG[f"p_ov_{name}"], parts[name], r, mx, my, s, a, fast, pivot)


def draw_shot(shot: Shot, t: float, fast: bool, extra=None) -> Image.Image:
    r = shot.cam(t)
    if extra:
        r = zoom_rect(r, extra[0], shot.size, extra[1], extra[2])
    if shot.src.startswith("card:"):
        g = shot.src[5:]
        frame = crop(IMG["bg_" + GROUPS[g]["bg"]], r, fast)
        for p in shot.parts:
            name, t_in, anim = p[:3]
            stt = part_state(anim, t - t_in)
            if stt is None:
                continue
            mx, my, s, a = stt
            t_out = p[3] if len(p) > 3 else None
            if t_out is not None and t >= t_out:
                a *= 1 - smooth((t - t_out) / 0.25)
            paste_part(frame, IMG[f"p_{g}_{name}"], GROUPS[g]["parts"][name], r, mx, my, s, a, fast)
    else:
        frame = crop(IMG[shot.src], r, fast)
    for on, off, box in shot.hl:
        if on <= t < off:
            p = (t - on) / 0.3
            a = smooth(p / 0.5) * (1 - smooth((t - (off - 0.2)) / 0.2))
            p0, p1 = to_out(box[:2], r), to_out(box[2:], r)
            highlight(frame, (p0[0], p0[1], p1[0], p1[1]), a, 1 + 0.18 * (1 - out_cubic(p)))
    cursor(frame, shot, t, r)
    draw_layers(frame, shot, t, fast)
    return frame


def window(fa, fb, p):
    """The incoming frame flies up in a rounded window and grows to fill the screen."""
    e = out_cubic(p)
    sc = 0.6 + 0.4 * e
    w, h = round(OUT_W * sc), round(OUT_H * sc)
    x, y = (OUT_W - w) // 2, round((OUT_H - h) / 2 + (1 - e) * 0.32 * OUT_H)
    frame = fa.copy()
    m = round(px(60) * sc)
    sh = SHADOW.resize((w + 2 * m, h + 2 * m), Image.BILINEAR)
    sh.putalpha(sh.getchannel("A").point(lambda v: int(v * (1 - e * e))))
    frame.paste(sh, (x - m, y - m + round(px(24))), sh)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=max(0, round(px(34) * (1 - e))), fill=255)
    frame.paste(fb.resize((w, h), Image.BILINEAR), (x, y), mask)
    return frame


def active(t):
    k = 0
    for i, s in enumerate(SHOTS):
        if s.t0 <= t:
            k = i
    return k


def base(t: float, fast: bool) -> Image.Image:
    k = active(t)
    B = SHOTS[k]
    kind, d = B.trans[0], B.trans[1]
    if k == 0 or kind == "cut" or t >= B.t0 + d:
        return draw_shot(B, t, fast)
    A = SHOTS[k - 1]
    p = (t - B.t0) / d
    if kind == "fade":
        return Image.blend(draw_shot(A, t, fast), draw_shot(B, t, fast), smooth(p))
    if kind == "whip":
        ux, uy = B.trans[2]
        e = in_out_cubic(p)
        frame = Image.new("RGB", (OUT_W, OUT_H))
        ax, ay = round(ux * e * OUT_W), round(uy * e * OUT_H)
        frame.paste(draw_shot(A, t, fast), (ax, ay))
        frame.paste(draw_shot(B, t, fast), (ax - round(ux * OUT_W), ay - round(uy * OUT_H)))
        return frame
    if kind == "zoom":
        ra = A.cam(t)
        f = B.trans[2]
        fxy = (0.5, 0.5) if f is None else (cl((f[0] - ra[0]) / (ra[2] - ra[0])), cl((f[1] - ra[1]) / (ra[3] - ra[1])))
        fa = draw_shot(A, t, fast, extra=(1 + 2.2 * in_cubic(p), *fxy))
        fb = draw_shot(B, t, fast, extra=(1 + 0.5 * (1 - out_cubic(p)), 0.5, 0.5))
        return Image.blend(fa, fb, smooth((p - 0.3) / 0.4))
    if kind == "window":
        return window(draw_shot(A, t, fast), draw_shot(B, t, fast), p)
    if kind == "wipe":                                   # same camera: reveal the new still left to right
        x0, x1 = B.trans[2]
        r = B.cam(t)
        xo = int((x0 + (x1 - x0) * p - r[0]) * OUT_W / (r[2] - r[0]))
        frame = draw_shot(A, t, fast)
        if xo > 0:
            frame.paste(draw_shot(B, t, fast).crop((0, 0, min(xo, OUT_W), OUT_H)), (0, 0))
        return frame
    raise ValueError(kind)


def motion(t: float) -> float:
    """Largest on-screen movement, in output pixels, during the shutter interval ending at t."""
    dt = SHUTTER / RENDER_FPS
    k = active(t)
    B = SHOTS[k]
    kind, d = B.trans[0], B.trans[1]
    both = k > 0 and kind != "cut" and B.t0 <= t < B.t0 + d
    m = 0.0
    for s in ([B, SHOTS[k - 1]] if both else [B]):
        r1, r0 = s.cam(t), s.cam(t - dt)
        m = max(m, max(abs(u - v) for u, v in zip(r1, r0)) * OUT_W / (r1[2] - r1[0]))
    if both:
        p1, p0 = (t - B.t0) / d, (t - dt - B.t0) / d
        if kind == "whip":
            m = max(m, abs(in_out_cubic(p1) - in_out_cubic(p0)) * OUT_W)
        elif kind == "zoom":
            m = max(m, (2.2 * abs(in_cubic(p1) - in_cubic(p0)) + 0.5 * abs(out_cubic(p1) - out_cubic(p0))) * OUT_W / 2)
        elif kind == "window":
            m = max(m, abs(out_cubic(p1) - out_cubic(p0)) * 0.4 * OUT_W)
    return m


# ---------------------------------------------------------------- captions and progress
def layout_captions() -> None:
    font = ImageFont.truetype(str(BUILD / "fonts" / "Poppins-SemiBold.ttf"), round(px(40)))
    space, pad_x, pad_y, line_h = font.getlength(" "), px(32), px(15), px(54)
    max_w = px(1480) - 2 * pad_x
    for (_, _, i, _), toks in zip(CAPS, TOKS):
        words = [w for w, _ in toks]
        widths = [font.getlength(w) for w in words]

        def width(ws):
            return sum(ws) + space * (len(ws) - 1)
        if width(widths) <= max_w:
            lines = [list(range(len(words)))]
        else:                                          # two balanced lines
            cut = min(range(1, len(words)), key=lambda c: max(width(widths[:c]), width(widths[c:])))
            lines = [list(range(cut)), list(range(cut, len(words)))]
        bw = max(width([widths[j] for j in ln]) for ln in lines) + 2 * pad_x
        bh = line_h * len(lines) + 2 * pad_y
        pos = {}
        for li, ln in enumerate(lines):
            x = (bw - width([widths[j] for j in ln])) / 2
            for j in ln:
                pos[j] = (x, pad_y + line_h * (li + 0.5), widths[j], li)
                x += widths[j] + space
        CAP_LAYOUT[i] = dict(font=font, words=words, times=[x for _, x in toks], pos=pos, size=(math.ceil(bw), math.ceil(bh)))


def captions(frame, t):
    for a, b, i, _ in CAPS:
        if not (a <= t < b):
            continue
        L = CAP_LAYOUT[i]
        img = Image.new("RGBA", L["size"], (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, L["size"][0] - 1, L["size"][1] - 1], radius=round(px(20)), fill=INK + (208,))
        j = max([k for k, x in enumerate(L["times"]) if x <= t + 0.04] or [0])
        q = out_cubic((t - L["times"][j]) / 0.1)
        x, y, w, li = L["pos"][j]
        if j > 0 and L["pos"][j - 1][3] == li and q < 1:          # the marker slides from the previous word
            px0, _, pw, _ = L["pos"][j - 1]
            x, w = px0 + (x - px0) * q, pw + (w - pw) * q
        fs = L["font"].size
        d.rounded_rectangle([x - px(10), y - fs * 0.62, x + w + px(10), y + fs * 0.62], radius=round(px(10)), fill=CYAN + (255,))
        for k, word in enumerate(L["words"]):
            wx, wy, _, _ = L["pos"][k]
            d.text((wx, wy), word, font=L["font"], fill=INK if (k == j and q > 0.5) else (255, 255, 255), anchor="lm")
        pop = 0.92 + 0.08 * out_back((t - a) / 0.22, 1.4)
        alpha = smooth((t - a) / 0.1) * (1 - smooth((t - (b - 0.1)) / 0.1))
        if pop < 0.999:
            img = img.resize((max(1, round(img.width * pop)), max(1, round(img.height * pop))), Image.BILINEAR)
        if alpha < 0.999:
            img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
        frame.paste(img, ((OUT_W - img.width) // 2, round(OUT_H - px(52) - (L["size"][1] + img.height) / 2)), img)


def progress(frame, t):
    w = round(OUT_W * t / TOTAL)
    if w > 0:
        h = max(2, round(px(6)))
        ImageDraw.Draw(frame).rectangle([0, OUT_H - h, w, OUT_H], fill=CYAN)


def thumbnail(path: Path) -> None:
    """The finished July chart with the €346 card, to upload as the video's thumbnail."""
    s1 = IMG["s1_v3"].size
    shot = Shot("s1_v3", 0, [K(0, full(s1))], layers=[dict(part="chip", t=0, anim="none"), dict(part="amount", t=0, anim="none"),
                                                       dict(part="num20", t=0, anim="none", pivot="amount")])
    draw_shot(shot, 0, False).save(path)


def render(i: int) -> bytes:
    return frame_at(i / RENDER_FPS).tobytes()


def frame_at(t: float) -> Image.Image:
    m = motion(t)
    n = 1 if m < 3 else min(24, int(m / 3) + 1)
    if n == 1:
        frame = base(t, False)
    else:
        dt = SHUTTER / RENDER_FPS
        acc = np.zeros((OUT_H, OUT_W, 3), np.float32)
        for j in range(n):
            acc += np.asarray(base(t - dt * j / (n - 1), True), dtype=np.float32)
        frame = Image.fromarray((acc / n + 0.5).astype(np.uint8))
    captions(frame, t)
    progress(frame, t)
    return frame


# ---------------------------------------------------------------- loading
def load() -> None:
    global SHADOW
    for n in ("s1_v0", "s1_v1", "s1_v2", "s1_v3", "bg_light", "bg_cyan", "app_inbox", "app_why42", "app_why46", "app_approved"):
        IMG[n] = Image.open(ASSETS / f"{n}.png").convert("RGB")
    IMG["cursor"] = Image.open(ASSETS / "cursor.png").convert("RGBA")
    for g, spec in GROUPS.items():
        for part in spec["parts"]:
            IMG[f"p_{g}_{part}"] = Image.open(ASSETS / f"p_{g}_{part}.png").convert("RGBA")
    m = round(px(60))
    SHADOW = Image.new("RGBA", (OUT_W + 2 * m, OUT_H + 2 * m), (0, 0, 0, 0))
    ImageDraw.Draw(SHADOW).rounded_rectangle([m, m, m + OUT_W, m + OUT_H], radius=round(px(34)), fill=(10, 40, 60, 90))
    SHADOW = SHADOW.filter(ImageFilter.GaussianBlur(px(26)))
    SHOTS.extend(shots())
    auto_sounds()
    layout_captions()


# ---------------------------------------------------------------- audio
def lufs(args: list) -> float:
    err = subprocess.run([FFMPEG, "-hide_banner", "-nostats", *args, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])


def sfx_bus(path: Path) -> None:
    n = int((TOTAL + 2) * sfx.SR)
    bus = np.zeros((n, 2), np.float32)
    cache, count = {}, {}
    for t, name, gain, flip in sorted(EVENTS):
        v = count.get(name, 0) % sfx.VARIANTS if name in sfx.AIR else 0      # whoosh-types rotate through their variants
        count[name] = count.get(name, 0) + 1
        if (name, v) not in cache:
            cache[name, v] = sfx._norm(sfx.decode(AUDIO / "tick.mp3")) if name == "click" else sfx.load(name, v)
        snd = cache[name, v][:, ::-1] if flip else cache[name, v]
        a = int(max(0.0, t) * sfx.SR)
        b = min(n, a + len(snd))
        bus[a:b] += snd[: b - a] * 10 ** (gain / 20)
    peak = float(np.abs(bus).max())
    print(f"  sfx: {len(EVENTS)} sounds, peak {20 * math.log10(peak + 1e-9):.1f} dBFS", flush=True)
    bus[: int(TOTAL * sfx.SR)].astype("<f4").tofile(path)


def mix_audio(out: Path) -> None:
    music_gain = -35.0 - lufs(["-i", str(AUDIO / "music.mp3")])     # music about 19 dB under the voice (−16 LUFS)
    bus = out.with_suffix(".sfx.f32")
    sfx_bus(bus)
    inputs, parts = [], []
    for n in range(1, 9):
        inputs += ["-i", str(AUDIO / f"{n:02d}.mp3")]
        parts.append(f"[{n - 1}:a]aformat=sample_rates=48000:channel_layouts=mono,adelay={int(S[n] * 1000)}:all=1[v{n}]")
    parts.append("".join(f"[v{n}]" for n in range(1, 9)) + f"amix=inputs=8:normalize=0:duration=longest,"
                 f"apad=whole_dur={TOTAL},loudnorm=I=-16:TP=-1.5:LRA=11,aformat=sample_rates=48000:channel_layouts=stereo[voice]")
    inputs += ["-i", str(AUDIO / "music.mp3")]
    parts.append(f"[8:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{TOTAL},volume={music_gain:.1f}dB,"
                 f"afade=t=in:st=0:d=1.2,afade=t=out:st={TOTAL - 3.2:.2f}:d=3.2[music]")
    inputs += ["-f", "f32le", "-ar", str(sfx.SR), "-ac", "2", "-i", str(bus)]
    parts.append("[voice][music][9:a]amix=inputs=3:normalize=0:duration=first,"
                 f"atrim=0:{TOTAL},alimiter=limit=0.95[out]")
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", ";".join(parts),
                    "-map", "[out]", "-c:a", "pcm_s16le", str(out)], check=True)
    sfx_l = lufs(["-f", "f32le", "-ar", str(sfx.SR), "-ac", "2", "-i", str(bus)])
    print(f"  mix: {lufs(['-i', str(out)]):.1f} LUFS · sound effects alone {sfx_l:.1f} LUFS", flush=True)
    bus.unlink()


# ---------------------------------------------------------------- main
def init_worker(w, h, fps):
    global OUT_W, OUT_H, RENDER_FPS
    OUT_W, OUT_H, RENDER_FPS = w, h, fps


def main() -> None:
    global OUT_W, OUT_H, RENDER_FPS
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="smart_weight_check")
    ap.add_argument("--preview", action="store_true", help="960×540, 15 fps")
    ap.add_argument("--stills", help="comma-separated times in seconds: write those frames to build/stills/ and stop")
    args = ap.parse_args()
    if args.preview:
        OUT_W, OUT_H, RENDER_FPS = 960, 540, 15
    BUILD.mkdir(parents=True, exist_ok=True)
    load()
    if args.stills:
        (BUILD / "stills").mkdir(exist_ok=True)
        times = [float(x) for x in args.stills.split(",")]
        with get_context("fork").Pool(min(12, os.cpu_count())) as pool:
            for t, img in zip(times, pool.map(frame_at, times)):
                img.save(BUILD / "stills" / f"t{t:06.2f}.png")
        print("wrote", len(times), "stills to", BUILD / "stills")
        return
    n = int(TOTAL * RENDER_FPS)
    silent, wav, final = BUILD / f"{args.out}_video.mp4", BUILD / f"{args.out}_audio.wav", BUILD / f"{args.out}.mp4"
    thumbnail(BUILD / f"{args.out}_thumbnail.png")
    mix_audio(wav)
    encoders = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    codec = (["-c:v", "libx264", "-preset", "medium", "-crf", "17"] if "libx264" in encoders
             else ["-c:v", "libopenh264", "-b:v", "14M", "-profile:v", "high"])
    enc = subprocess.Popen([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{OUT_W}x{OUT_H}", "-r", str(RENDER_FPS), "-i", "-", *codec, "-pix_fmt", "yuv420p",
                            str(silent)], stdin=subprocess.PIPE)
    # fork, so the workers share the loaded images (Python 3.14 defaults to forkserver)
    with get_context("fork").Pool(min(12, os.cpu_count()), initializer=init_worker, initargs=(OUT_W, OUT_H, RENDER_FPS)) as pool:
        for k, buf in enumerate(pool.imap(render, range(n), chunksize=4)):
            enc.stdin.write(buf)
            if k % (RENDER_FPS * 10) == 0:
                print(f"  {k / RENDER_FPS:5.1f} s / {TOTAL:.1f} s", flush=True)
    enc.stdin.close()
    enc.wait()
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-map", "0:v",
                    "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    str(final)], check=True)
    silent.unlink()
    print("wrote", final, f"({TOTAL:.2f} s)")


if __name__ == "__main__":
    main()
