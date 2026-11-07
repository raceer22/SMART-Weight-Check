---
id: "u10-run-the-weighing-accuracy-value-script-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:12:17.000Z"
completedAt: "2026-11-07T02:12:17.000Z"
labels: ["weight", "beginner", "python"]
order: "b0J"
---
# U10 · Run the weighing-accuracy value script

**Time:** ~15 min  ·  **Do first:** S03

**Why:** Brief part 1 is “get the weight”. This script shows what each level of accuracy is worth.

## Steps
1. Run `python examples/weighing_accuracy_value.py data/competition/public`.
2. Copy the printed table into FINDINGS.md under `## Weight`.
3. Find the row where ~95 % of 3 t loads are within ±100 kg.

## Done when
- [x] The table is in FINDINGS.md and the ±100 kg row is highlighted.

## Help
- Read the comment at the top of `examples/weighing_accuracy_value.py`.
