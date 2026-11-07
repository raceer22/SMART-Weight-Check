---
id: "p07-write-how-to-run-our-solution-in-the-readme-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "4 · Demo & pitch"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T12:50:00.000Z"
completedAt: "2026-11-07T12:50:00.000Z"
labels: ["docs", "beginner"]
order: "b0q"
---
# P07 · Write “How to run our solution” in the README

**Time:** ~20 min  ·  **Do first:** C13

**Why:** Judges may try to run our code.

## Steps
1. Add a section at the **top** of `README.md`: `## Our solution`.
2. List the exact commands: create venv, `pip install -e ".[dev]" streamlit matplotlib`, `streamlit run app/app.py`.
3. Add 2 sentences on what the app shows.

## Done when
- [x] The section is in the README and pushed.

## Result
- `## Our solution` is at the top of `README.md`: jury pointer to `submission/README.md`, exact commands (clone, venv, `pip install -e ".[dev,app]"`, the two baselines, `streamlit run app/app.py`), what the app shows, and how to reproduce the analysis. matplotlib is now in the `app` extra, so one install command is enough.
