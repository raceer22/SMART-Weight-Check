---
id: "u06-plot-weight-mass-over-time-for-the-same-device-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:12:17.000Z"
completedAt: "2026-11-07T02:12:17.000Z"
labels: ["data", "beginner", "python", "chart"]
order: "b0F"
---
# U06 · Plot weight (mass) over time for the same device

**Time:** ~20 min  ·  **Do first:** U05

**Why:** Weight is the heart of this challenge. Does it rise and fall like the fill level?

## Steps
1. Copy your U05 code.
2. Plot `mass_kg_last_valid` instead of `fill_pct_max`. Save as `notes/mass.png`.
3. Bonus: plot both on the same chart (`plt.twinx()`).
4. Write 1 sentence: do fill and mass move together?

## Done when
- [x] `notes/mass.png` exists + your sentence is in FINDINGS.md.

## Help
- If the device has no weight sensor the line will be empty. Pick a device with `has_weight_measurement = true`.
