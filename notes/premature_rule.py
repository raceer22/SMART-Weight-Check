"""C05 · Idea for a better PREMATURE_UNJUSTIFIED rule, scored against the baseline.

Run from repo root after the Task B baseline has written its predictions:
  python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv
  python notes/premature_rule.py data/quickstart/public my_task_b.csv
  (competition: write the baseline to e.g. /tmp/comp_b.csv first and pass data/competition/public)

The baseline only flags SCHEDULED lifts below 40 % fill. On on-call devices it misses two mechanisms:
  * S39 precautionary orders: CUSTOMER_REQUEST at low fill just before a weekend or a closed day.
  * S40 fill sensor reads falsely high: an ON_CALL_ORDER fires on a high fill reading, but the weight
    shows the container was far from full.
The rule itself lives in app/weight_rules.py (premature_extra), so the demo app and this score use the same
code. It only ADDS predictions; it does not change the baseline file.
"""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "app")
warnings.filterwarnings("ignore")
import pandas as pd  # noqa: E402
from europress_data.evaluate import score_b  # noqa: E402
from weight_rules import premature_extra  # noqa: E402

root, base_csv = Path(sys.argv[1]), sys.argv[2]
extra_flags = premature_extra(root)
base = pd.read_csv(base_csv)
extra = pd.DataFrame({"entity_type": "collection", "entity_id": extra_flags.collection_id, "label_family": "PREMATURE_UNJUSTIFIED"})
new = pd.concat([base, extra]).drop_duplicates()
keys = ["positives", "predicted", "tp", "precision", "recall", "f1", "explained_flagged_as_anomaly"]
for split in ["validation", "all"]:
    a, b = score_b(base, root / "labels_dev", split), score_b(new, root / "labels_dev", split)
    print(f"{split:10s} baseline {[a['PREMATURE_UNJUSTIFIED'][k] for k in keys]}  macro_f1 {a['macro_f1']}")
    print(f"{'':10s} new      {[b['PREMATURE_UNJUSTIFIED'][k] for k in keys]}  macro_f1 {b['macro_f1']}")
print("columns:", keys)
print(f"extra flags: {extra_flags.rule.value_counts().to_dict()}")
