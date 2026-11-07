---
id: "u07-find-duplicate-telemetry-messages-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:12:17.000Z"
completedAt: "2026-11-07T02:12:17.000Z"
labels: ["data", "beginner", "sql", "data-quality"]
order: "b0G"
---
# U07 · Find duplicate telemetry messages

**Time:** ~15 min  ·  **Do first:** U01

**Why:** The hourly telemetry is an *ingest log*: the same message can arrive twice. We must not double count.

## Steps
1. Run:
   ```sql
   SELECT COUNT(*) AS all_rows, COUNT(DISTINCT message_id) AS unique_msgs FROM telemetry_hourly
   ```
2. Calculate: duplicates = all_rows − unique_msgs.
3. Note that the SDK also gives a cleaned view called `telemetry_dedup`.

## Done when
- [x] The duplicate count is in FINDINGS.md under *Data quality*.

## Help
- `docs/QUICKSTART_FOR_BUILDERS.md` → *Traps*
