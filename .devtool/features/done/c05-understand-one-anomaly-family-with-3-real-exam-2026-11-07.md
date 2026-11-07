---
id: "c05-understand-one-anomaly-family-with-3-real-exam-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["task-b", "data"]
order: "b0R"
---
# C05 · Understand one anomaly family with 3 real examples

**Time:** ~30 min  ·  **Do first:** C04

**Why:** To improve a rule you first need to see what the true cases look like.

## Steps
1. Open `data/quickstart/public/labels_dev/anomaly_labels.parquet` with pandas.
2. Filter to the weakest family from C04.
3. Look up 3 of those collections in `collection_events` and describe what is special about them.

## Done when
- [x] 3 described examples plus 1 idea for a better rule are in FINDINGS.md.

## Help
- `docs/SCENARIO_CATALOG.md` describes every scenario family.
