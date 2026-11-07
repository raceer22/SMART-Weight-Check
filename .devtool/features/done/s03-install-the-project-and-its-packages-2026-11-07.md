---
id: "s03-install-the-project-and-its-packages-2026-11-07"
status: "done"
priority: "critical"
assignee: null
epic: "0 · Setup"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-06T23:32:23.885Z"
completedAt: "2026-11-06T23:32:23.885Z"
labels: ["setup", "beginner", "python"]
order: "b03"
---
# S03 · Install the project and its packages

**Time:** \~10 min · **Do first:** S02

**Why:** The scripts need pandas, duckdb, etc. This command installs all of them.

## Steps

1. Make sure the venv is active (`(.venv)` in the prompt).
2. Run `pip install -e ".[dev]"`.
3. Also run `pip install matplotlib streamlit` (we use them for charts and the demo app).
4. Test it: `python -c "import europress_data; print('ok')"`.

## Done when

- [ ] The test command prints `ok`.

## Help

- If an install fails, copy the **last 10 lines** of the error into the team chat.