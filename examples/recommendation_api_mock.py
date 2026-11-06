"""Illustrative JSON 'API' payload: how a solution COULD hand a proposal to a SMART-like UI.
No real Europress API is implied. python examples/recommendation_api_mock.py data/quickstart/public [case_id]"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "baselines"))
import pandas as pd  # noqa: E402
from b3_next_best_action import case_features, decide  # noqa: E402

root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/quickstart/public")
cases = pd.read_parquet(root / "benchmark" / "decision_cases.parquet")
case = cases[cases.case_id == sys.argv[2]] if len(sys.argv) > 2 else cases.head(1)
f = case_features(root, case)
d = decide(f).iloc[0]
r = f.iloc[0]
payload = {
    "schema": "smve.recommendation.v0 (illustrative mock)",
    "synthetic": True,
    "case_id": d.case_id, "device_id": r.device_id, "as_of": str(r.decision_at),
    "proposal": {"action": d.action, "requires_human_approval": True, "auto_execute": False},
    "diagnostics": {"verify_weight_sensor": bool(d.verify_weight_sensor), "review_invoices": bool(d.review_invoices)},
    "evidence": {"observed": {"lifts_last_56d": int(r.n_lifts_56d), "median_fill_before_lift_pct": None if pd.isna(r.med_fill_56d) else float(r.med_fill_56d),
                              "full_hours_last_28d": int(r.full_hours_28d), "share_lifts_device_vs_weighbridge_gt_10pct_90d": None if pd.isna(r.wb_diff_share_90d) else float(r.wb_diff_share_90d)},
                 "estimated": {}, "hypothetical": {}},
    "assumptions": ["Synthetic world; not Europress data", "Decision uses only data received before as_of"],
    "rationale": d.rationale,
    "not_proven": ["Savings are not demonstrated; a simulated counterfactual is not causal evidence"],
}
print(json.dumps(payload, indent=2, default=str))
