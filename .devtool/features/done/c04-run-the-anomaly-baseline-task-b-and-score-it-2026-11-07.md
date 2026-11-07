---
id: "c04-run-the-anomaly-baseline-task-b-and-score-it-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["task-b", "beginner", "python"]
order: "b0Q"
---
# C04 · Run the anomaly baseline (Task B) and score it

**Time:** ~10 min  ·  **Do first:** S03

**Why:** Task B = find irregularities (unnecessary lifts, delays, weight differences, billing errors).

## Steps
1. Run `python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv`.
2. Run `python -m europress_data.evaluate --task B --pred my_task_b.csv --labels data/quickstart/public/labels_dev --split validation`.
3. Write down which anomaly family has the **lowest** F1.

## Done when
- [x] The weakest family is named in FINDINGS.md.
