---
id: "s08-run-all-baselines-once-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "0 · Setup"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T00:49:16.220Z"
completedAt: "2026-11-07T00:49:16.220Z"
labels: ["setup", "beginner", "python"]
order: "b08"
---
# S08 · Run all baselines once

**Time:** \~10 min · **Do first:** S03

**Why:** Baselines are the organiser's simple solutions. Our work should beat or explain them.

## Steps

1. Run `python baselines/run_all.py quickstart`.
2. Wait until it finishes (a minute or two).
3. Open `reports/baselines_quickstart.json` and find the `f1` numbers under `task_B`.

## Done when

- [ ] The file `reports/baselines_quickstart.json` was updated (check its date).

## Help

- `baselines/run_all.py`, `docs/BENCHMARK.md` (*Baselines* section)