---
id: "s02-create-a-python-virtual-environment-2026-11-07"
status: "done"
priority: "critical"
assignee: null
epic: "0 · Setup"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-06T23:30:49.296Z"
completedAt: "2026-11-06T23:30:49.296Z"
labels: ["setup", "beginner", "python"]
order: "b02"
---
# S02 · Create a Python virtual environment

**Time:** \~10 min · **Do first:** S01

**Why:** A virtual environment (venv) keeps this project's packages separate from the rest of your computer.

## Steps

1. Open the VS Code terminal (*Terminal → New Terminal*).
2. Run `python3 -m venv .venv`.
3. Activate it: `source .venv/bin/activate` (Mac/Linux) or `.venv\Scripts\activate` (Windows).
4. Your prompt should now start with `(.venv)`.
5. In VS Code press `Ctrl+Shift+P` → *Python: Select Interpreter* → choose `.venv`.

## Done when

- [x] `which python` (or `where python` on Windows) points into `.venv`.

## Help

- If `python3` is not found, try `python`.