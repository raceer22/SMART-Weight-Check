"""C07 · Chart: punctuality per operator.

Run from repo root after notes/scorecard.py:  python notes/punctuality.py
Reads my_scorecard.csv and writes notes/punctuality.png.
On time = the lift happened within ±2 h of the scheduled time (baselines/b5_operator_scorecard.py).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
import pandas as pd

SURFACE, INK, INK_2, GRID, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"

sc = pd.read_csv("my_scorecard.csv")
g = sc.groupby("operator_id").on_time_rate.agg(["mean", "count"]).sort_values("mean")
print(g.round(3).to_string())

fig, ax = plt.subplots(figsize=(8, 3.4), dpi=150, facecolor=SURFACE)
ax.set_facecolor(SURFACE)
h = 0.34  # bar thickness (~24 px)


def bar(y, w, rx=0.006, ry=0.09):
    """Horizontal bar, square at the baseline, rounded (~4 px) at the data end."""
    y0, y1, k = y - h / 2, y + h / 2, 0.45
    verts = [(0, y0), (w - rx, y0), (w - rx * k, y0), (w, y0 + ry * k), (w, y0 + ry),
             (w, y1 - ry), (w, y1 - ry * k), (w - rx * k, y1), (w - rx, y1), (0, y1), (0, y0)]
    codes = [Path.MOVETO, Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.LINETO, Path.CLOSEPOLY]
    return PathPatch(Path(verts, codes), fc=SERIES, ec="none")


for i, (op, row) in enumerate(g.iterrows()):
    w = row["mean"]
    ax.add_patch(bar(i, w))
    ax.text(w + 0.012, i, f"{w:.0%}", va="center", ha="left", fontsize=10, color=INK)
ax.set_yticks(range(len(g)), [f"{op}  ({int(n)} region-months)" for op, n in zip(g.index, g["count"])], color=INK, fontsize=10)
ax.set_xlim(0, 1.02)
ax.set_ylim(-0.6, len(g) - 0.4)
ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0 %", "25 %", "50 %", "75 %", "100 %"], color=INK_2, fontsize=9)
ax.xaxis.grid(True, color=GRID, lw=1)
ax.set_axisbelow(True)
ax.tick_params(length=0)
for s in ax.spines.values():
    s.set_visible(False)
fig.text(0.02, 0.95, "Share of visits on time, by operator", ha="left", va="top", fontsize=13, color=INK, fontweight="bold")
fig.text(0.02, 0.87, "On time = lift within ±2 h of the scheduled time. Mean of monthly rates per region, Jul–Sep 2026.",
         ha="left", va="top", fontsize=9, color=INK_2)
fig.text(0.02, 0.02, "Observed in synthetic quickstart data (operator scorecard baseline). Not Europress data.",
         fontsize=8, color=INK_2)
fig.tight_layout(rect=(0, 0.05, 1, 0.82))
fig.savefig("notes/punctuality.png", facecolor=SURFACE)
