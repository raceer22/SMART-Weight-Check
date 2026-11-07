---
id: "c02-find-the-10-most-expensive-devices-per-tonne-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["task-a", "beginner", "data"]
order: "b0O"
---
# C02 · Find the 10 most expensive devices per tonne

**Time:** ~20 min  ·  **Do first:** S07

**Why:** Expensive €/t *and* low fill = the customer probably pays for half-empty lifts.

## Steps
1. Run `python examples/first_analysis.py data/quickstart/public`.
2. Copy the top 10 rows (highest `vs_benchmark`) into FINDINGS.md.
3. Mark the ones with median fill below 50 %.

## Done when
- [x] Top-10 list with low-fill devices marked is in FINDINGS.md.

## Help
- Check if it's biowaste: biowaste must be emptied every 7 days (hygiene) even when not full, so it's *explained*, not waste.
