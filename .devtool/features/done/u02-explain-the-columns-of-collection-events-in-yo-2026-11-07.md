---
id: "u02-explain-the-columns-of-collection-events-in-yo-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T01:52:29.836Z"
completedAt: "2026-11-07T01:52:29.836Z"
labels: ["data", "beginner", "reading"]
order: "b0B"
---
# U02 · Explain the columns of collection_events in your own words

**Time:** \~30 min · **Do first:** U01

**Why:** `collection_events` (one row per container emptying) is the most important table.

## Steps

1. Run `con.sql("SELECT * FROM collection_events LIMIT 5").df()` and print it (or open `data/quickstart/public/csv/collection_events.csv`).
2. Open `docs/DATA_DICTIONARY.md` and search for `collection_events`.
3. For each column write 1 short line: what it means, with an example value.
4. Mark the 5 columns you think matter most for **weight**.

## Done when

- [x] A column table is in FINDINGS.md with your top-5 weight columns marked.

## Help

- Key columns: `device_estimated_collected_kg`, `operator_job_ref`, `status`, `trigger_type`.