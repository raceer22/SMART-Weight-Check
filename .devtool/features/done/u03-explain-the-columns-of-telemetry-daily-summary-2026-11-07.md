---
id: "u03-explain-the-columns-of-telemetry-daily-summary-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:03:49.254Z"
completedAt: "2026-11-07T02:03:49.254Z"
labels: ["data", "beginner", "reading"]
order: "b0C"
---
# U03 · Explain the columns of telemetry_daily_summary

**Time:** \~20 min · **Do first:** U01

**Why:** This is the device's daily diary: fill level, weight, compaction, downtime.

## Steps

1. Print 5 rows of `telemetry_daily_summary`.
2. Look up each column in `docs/DATA_DICTIONARY.md`.
3. Write 1 line per column in FINDINGS.md.

## Done when

- [x] Column explanations are in FINDINGS.md.

## Help

- `fill_pct_max`, `mass_kg_last_valid`, `hours_full`, `data_completeness_pct` are the interesting ones.