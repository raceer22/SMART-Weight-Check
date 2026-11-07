---
id: "c07-chart-punctuality-per-operator-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["task-b2", "chart", "python"]
order: "b0T"
---
# C07 · Chart: punctuality per operator

**Time:** ~30 min  ·  **Do first:** C06

**Why:** One clear chart of operator performance is a strong pitch visual.

## Steps
1. Load `my_scorecard.csv` with pandas.
2. The punctuality column is `on_time_rate` (share of visits on time, 0–1).
3. Group by `operator_id`, take the mean, and draw a bar chart. Save as `notes/punctuality.png`.

## Done when
- [x] `notes/punctuality.png` exists.

## Help
- Keep the tone **neutral**: “operator A was on time 82 % of the time”, not “operator A is bad”.
