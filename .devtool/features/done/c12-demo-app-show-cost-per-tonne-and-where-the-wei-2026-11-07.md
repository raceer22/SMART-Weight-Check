---
id: "c12-demo-app-show-cost-per-tonne-and-where-the-wei-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["app", "python", "task-a"]
order: "b0Y"
---
# C12 · Demo app: show cost per tonne and where the weight came from

**Time:** ~30 min  ·  **Do first:** C10, C01

**Why:** Customers want € per tonne, and judges want to know whether the weight was measured or estimated.

## Steps
1. Load `my_task_a.csv` (from C01).
2. Filter to collections of the selected device.
3. Show the average €/t with `st.metric(...)`.
4. Show the mass source next to it (weighbridge / invoice / device estimate). If unknown, show “unknown” and **don't** make up a number.

## Done when
- [x] The app shows €/t and its mass source for the device.

## Help
- Unknown mass ⇒ €/t is NULL. Never fill it in.
