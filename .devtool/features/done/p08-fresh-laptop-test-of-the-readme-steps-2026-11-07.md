---
id: "p08-fresh-laptop-test-of-the-readme-steps-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "4 · Demo & pitch"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T12:50:00.000Z"
completedAt: "2026-11-07T12:50:00.000Z"
labels: ["qa", "beginner"]
order: "b0r"
---
# P08 · Fresh-laptop test of the README steps

**Time:** ~20 min  ·  **Do first:** P07

**Why:** If it only works on one laptop, it doesn't work.

## Steps
1. On a teammate's laptop, clone the repo fresh.
2. Follow **only** the README steps, without help.
3. Write down every step that fails or is unclear and fix the README.

## Done when
- [x] Someone other than the author got the app running from the README.

## Result
- Fresh clone of the branch into an empty folder, new venv (Python 3.14), README commands only: install took ~1 min; both baselines wrote their CSVs; the app started and rendered CMP-00046 and CMP-00042 with the weight check and proposals and no exceptions (checked in a headless browser); `notes/explore.py`, `notes/premature_rule.py` and `notes/business_case_sensitivity.py` ran and reproduced the committed outputs exactly.
- Not yet done: a run on a teammate's laptop, ideally Windows (the README gives the Windows activate command).
