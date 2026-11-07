---
id: "c01-run-the-cost-calculator-task-a-and-score-it-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["task-a", "beginner", "python"]
order: "b0N"
---
# C01 · Run the cost calculator (Task A) and score it

**Time:** ~10 min  ·  **Do first:** S03

**Why:** Task A = what each collection *should* cost under the contract. The baseline is already perfect on quickstart, so we can reuse it.

## Steps
1. Run `python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv`.
2. Run `python -m europress_data.evaluate --task A --pred my_task_a.csv --labels data/quickstart/public/labels_dev --split validation`.
3. Note the `exact_to_cent_share` numbers.

## Done when
- [x] Scores are in FINDINGS.md under `## Customer value`.

## Help
- `docs/ECONOMIC_MODEL.md` explains the formulas.
