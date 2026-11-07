---
id: "c06-save-the-operator-scorecard-task-b2-as-a-csv-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["task-b2", "beginner", "python"]
order: "b0S"
---
# C06 · Save the operator scorecard (Task B2) as a CSV

**Time:** ~15 min  ·  **Do first:** S03

**Why:** The scorecard compares operators on punctuality, missed visits, billing accuracy and weight bias.

## Steps
1. Create `notes/scorecard.py` with:
   ```python
   import sys; sys.path.insert(0, 'baselines')
   from pathlib import Path
   from b5_operator_scorecard import scorecard
   scorecard(Path('data/quickstart/public')).to_csv('my_scorecard.csv', index=False)
   ```
2. Run it and open `my_scorecard.csv`.
3. Score it: `python -m europress_data.evaluate --task B2 --pred my_scorecard.csv --labels data/quickstart/public/labels_dev --split all`.

## Done when
- [x] `my_scorecard.csv` exists and the score is in FINDINGS.md.
