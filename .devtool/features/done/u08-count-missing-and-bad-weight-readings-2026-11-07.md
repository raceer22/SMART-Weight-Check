---
id: "u08-count-missing-and-bad-weight-readings-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:12:17.000Z"
completedAt: "2026-11-07T02:12:17.000Z"
labels: ["data", "beginner", "sql", "data-quality"]
order: "b0H"
---
# U08 · Count missing and bad weight readings

**Time:** ~15 min  ·  **Do first:** U07

**Why:** Weight can be missing (NULL), negative or flagged as bad. This shows how trustworthy device weight is today.

## Steps
1. Count rows where `mass_kg IS NULL` in `telemetry_dedup`.
2. Count rows per `quality_flag`: `SELECT quality_flag, COUNT(*) FROM telemetry_dedup GROUP BY 1`.
3. Do the same for `sensor_status`.

## Done when
- [x] Three small count tables are in FINDINGS.md.
