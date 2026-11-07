"""C06 · Operator scorecard (Task B2) as a CSV.

Run from repo root:  python notes/scorecard.py
Writes my_scorecard.csv. Score it with:
  python -m europress_data.evaluate --task B2 --pred my_scorecard.csv --labels data/quickstart/public/labels_dev --split all
"""
import sys; sys.path.insert(0, 'baselines')
from pathlib import Path
from b5_operator_scorecard import scorecard
scorecard(Path('data/quickstart/public')).to_csv('my_scorecard.csv', index=False)
