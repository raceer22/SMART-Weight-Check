---
id: "c13-demo-app-list-flagged-issues-as-proposals-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["app", "python", "task-b"]
order: "b0Z"
---
# C13 · Demo app: list flagged issues as proposals

**Time:** ~30 min  ·  **Do first:** C10, C04

**Why:** Turns anomalies into actions the customer can approve or reject.

## Steps
1. Load `my_task_b.csv` (from C04).
2. Filter to the selected device and show it with `st.dataframe(...)`.
3. Above it write: “Proposals. A human must approve each one.”
4. Bonus: add an `st.button('Approve')` per row that just shows `st.success('Approved (demo)')`.

## Done when
- [x] Flagged issues for the device appear in the app.
