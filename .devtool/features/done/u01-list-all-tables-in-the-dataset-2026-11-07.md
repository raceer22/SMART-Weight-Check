---
id: "u01-list-all-tables-in-the-dataset-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T01:04:16.383Z"
completedAt: "2026-11-07T01:04:16.383Z"
labels: ["data", "beginner", "sql"]
order: "b0A"
---
# U01 · List all tables in the dataset

**Time:** \~10 min · **Do first:** S03

**Why:** Before analysing anything we need to know what tables exist.

## Steps

1. Create a file `notes/explore.py`.
2. Paste:

```python
import sys; sys.path.insert(0, "src")
from europress_data.sdk import open_dataset
con = open_dataset("data/quickstart/public")
```

`con.sql("SHOW TABLES").show()`3. Run `python notes/explore.py`. 4. Copy the table names into `notes/FINDINGS.md` under `## Data`.

## Done when

- [x] The list of tables is in FINDINGS.md.

## Help

- `docs/SCHEMA.md` explains how the tables connect.