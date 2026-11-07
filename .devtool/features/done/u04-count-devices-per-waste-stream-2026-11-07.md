---
id: "u04-count-devices-per-waste-stream-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:12:17.000Z"
completedAt: "2026-11-07T02:12:17.000Z"
labels: ["data", "beginner", "sql"]
order: "b0D"
---
# U04 · Count devices per waste stream

**Time:** ~15 min  ·  **Do first:** U01

**Why:** Cardboard and plastics can earn money (material credit); other streams always cost money.

## Steps
1. Run:
   ```sql
   SELECT material_stream, COUNT(*) AS n FROM devices GROUP BY 1 ORDER BY n DESC
   ```
2. Also count how many devices have a weight sensor: `GROUP BY has_weight_measurement`.
3. Write both results in FINDINGS.md.

## Done when
- [x] Both counts are in FINDINGS.md.

## Help
- Use `con.sql("...").show()` to run SQL from Python.
