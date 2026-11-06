"""Run and score all baselines for a profile. python baselines/run_all.py competition

Writes reports/baselines_<profile>.json. Test-period scores use the PRIVATE labels and are produced only
when they are present (organisers); participants get validation / dev scores.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from b1_economic_calculator import compute  # noqa: E402
from b2_rules_anomaly import collection_features, detect_collections, detect_invoices  # noqa: E402
from b3_next_best_action import case_features, decide  # noqa: E402
import b4_ml_models as ml  # noqa: E402
from europress_data.evaluate import _entity_times, _period_filter, score_a, score_b, score_b2, score_c, score_c2  # noqa: E402
from b5_operator_scorecard import scorecard  # noqa: E402
from b6_operator_actions import decide as decide_c2  # noqa: E402


def main(profile="quickstart"):
    t0 = time.time()
    d = ROOT / "data" / profile
    pub, priv = d / "public", d / "private_evaluation"
    roots = [pub] + ([priv / "holdout_full"] if (priv / "holdout_full" / "reference").exists() else [])
    A, B_rules, F, inv_flags = [], [], [], []
    pub_parts = None
    for r in roots:
        b1, b1l = compute(r)
        A.append(b1)
        f = collection_features(r, b1)
        F.append(f)
        inv = detect_invoices(r, b1, b1l)
        B_rules += [detect_collections(f), inv]
        if pub_parts is None:
            pub_parts = (b1, b1l, inv)
        issued = pd.read_parquet(r / "finance" / "invoices.parquet", columns=["invoice_id", "issued_at"])
        il = inv[inv.entity_type == "invoice_line"].assign(invoice_id=lambda x: x.entity_id.str.rsplit("-", n=1).str[0])
        inv_flags.append(il.merge(issued, on="invoice_id"))
    A, B_rules, F, inv_flags = pd.concat(A), pd.concat(B_rules), pd.concat(F), pd.concat(inv_flags)
    print(f"B1/B2 done {time.time() - t0:.0f}s", flush=True)
    dev, test = pub / "labels_dev", priv / "labels_test"
    has_test = (test / "anomaly_labels.parquet").exists()      # private labels exist only for the organisers

    def _T(key, fn, pred, labels):
        return {key: fn(pred, labels, key)} if has_test else {}
    res = {"profile": profile, "task_A": {}, "task_B": {}, "task_C": {}}
    res["task_A"]["B1_calculator"] = {"validation": score_a(A, dev, "validation"), **_T("test", score_a, A, test)}
    res["task_A"]["mass_basis_counts"] = A.mass_basis.value_counts().to_dict()
    res["task_B"]["B2_rules"] = {"validation": score_b(B_rules, dev, "validation"), **_T("test", score_b, B_rules, test)}
    # ML for Task B
    lab = pd.read_parquet(dev / "anomaly_labels.parquet")
    lab_tr = _period_filter(lab, dev, "train", "eval_at")
    f_pub = F[F.collection_id.isin(pd.read_parquet(pub / "operations" / "collection_events.parquet", columns=["collection_id"]).collection_id)]
    ent = _entity_times(dev)
    man = json.load(open(pub / "metadata" / "dataset_manifest.json"))["label_periods"]
    tl = f_pub.collection_id.map(ent.set_index("entity_id").eval_at).dt.tz_convert("Europe/Helsinki").dt.tz_localize(None)
    f_tr = f_pub[tl < pd.Timestamp(man["train"][1])]
    f_trval = f_pub[tl < pd.Timestamp(man["validation"][1])]
    pb_val = ml.task_b(f_tr, lab_tr, F)
    pb_test = ml.task_b(f_trval, lab, F)
    res["task_B"]["B4_gradient_boosting"] = {"validation": score_b(pb_val, dev, "validation"), **_T("test", score_b, pb_test, test)}
    # combined: ML collection families + rules for invoice families
    inv_fams = ["OUTDATED_TARIFF", "DUPLICATE_LINE", "WRONG_SURCHARGE", "WEIGHT_BASIS_MISMATCH", "UNMATCHED_LINE", "MISSING_LINE", "UNINVOICED_COLLECTION", "REJECTED_LOAD"]
    hyb_v = pd.concat([pb_val, B_rules[B_rules.label_family.isin(inv_fams)]])
    hyb_t = pd.concat([pb_test, B_rules[B_rules.label_family.isin(inv_fams)]])
    res["task_B"]["hybrid_ml_plus_rules"] = {"validation": score_b(hyb_v, dev, "validation"), **_T("test", score_b, hyb_t, test)}
    print(f"Task B done {time.time() - t0:.0f}s", flush=True)
    # Task C
    cases_pub = pd.read_parquet(pub / "benchmark" / "decision_cases.parquet")
    fc_pub = case_features(pub, cases_pub, inv_flags)
    fcs = [fc_pub]
    cp = priv / "benchmark" / "decision_cases_private.parquet"
    snaps = list(priv.glob("holdout_asof_*"))
    if cp.exists() and snaps:
        cases_priv = pd.read_parquet(cp)
        if len(cases_priv):
            fcs.append(case_features(snaps[0], cases_priv, inv_flags))
    fc = pd.concat(fcs, ignore_index=True)
    truth_dev = pd.read_parquet(dev / "decision_truth.parquet")
    rules_c = decide(fc)
    noact = pd.DataFrame({"case_id": fc.case_id, "action": "NO_ACTION"})
    aggressive = pd.DataFrame({"case_id": fc.case_id, "action": [next((a for a in ("REDUCE_FREQUENCY", "RAISE_THRESHOLD", "SWITCH_TO_ON_CALL") if a in c.split(",")), "NO_ACTION") for c in fc.candidate_actions]})
    tr_ids = truth_dev[truth_dev.split == "train"].case_id
    ml_val = ml.task_c(fc[fc.case_id.isin(tr_ids)], truth_dev, fc)
    ml_test = ml.task_c(fc[fc.case_id.isin(truth_dev.case_id)], truth_dev, fc)
    for name, p_val, p_test in [("always_no_action", noact, noact), ("naive_aggressive_saver", aggressive, aggressive),
                                ("B3_rules", rules_c, rules_c), ("B4_gradient_boosting", ml_val, ml_test)]:
        res["task_C"][name] = {"validation": score_c(p_val, dev, "validation"), **_T("test", score_c, p_test, test)}
    # Task B2: operator performance scorecard (Europress review 30.10.2026)
    b1p, b1lp, invp = pub_parts
    sc = scorecard(pub, b1p, b1lp)
    # B5 has no trained parameters, so it is scored on all public dev months ("validation" key = all dev months)
    res["task_B2"] = {"B5_public_records": {"validation": score_b2(sc, dev, "all"), **_T("test", score_b2, sc, test)}}
    # Task C2: operator and contract actions
    cases_c2 = pd.read_parquet(pub / "benchmark" / "operator_action_cases.parquet")
    none_c2 = pd.DataFrame({"case_id": cases_c2.case_id, "actions": ""})
    all_c2 = pd.DataFrame({"case_id": cases_c2.case_id, "actions": cases_c2.candidate_actions.str.replace("TENDER_OR_SWITCH_OPERATOR", "", regex=False).str.strip(",")})
    rules_c2 = decide_c2(pub, b1p, b1lp, invp)
    res["task_C2"] = {name: {"dev": score_c2(p_, dev, "dev"), **_T("test", score_c2, p_, test)}
                      for name, p_ in (("no_action", none_c2), ("act_on_everything", all_c2), ("B6_rules", rules_c2))}
    print(f"Tasks B2/C2 done {time.time() - t0:.0f}s", flush=True)
    res["runtime_seconds"] = round(time.time() - t0, 1)
    (ROOT / "reports").mkdir(exist_ok=True)
    out = ROOT / "reports" / f"baselines_{profile}.json"
    json.dump(res, open(out, "w"), indent=2, default=str)
    A.to_parquet(ROOT / "reports" / f"b1_task_a_predictions_{profile}.parquet")
    print(json.dumps(summary(res), indent=1))
    return res


def summary(res):
    s = {}
    for k, v in res["task_A"].items():
        if isinstance(v, dict) and "validation" in v:
            s[f"A/{k}"] = {sp: {m: v[sp].get(m) for m in ("net_material_contribution_eur:exact_to_cent_share", "per_t:coverage", "per_t:within_5pct_share")} for sp in v}
    for k, v in res["task_B"].items():
        s[f"B/{k}"] = {sp: v[sp]["macro_f1"] for sp in v}
    for k, v in res["task_C"].items():
        s[f"C/{k}"] = {sp: {m: v[sp].get(m) for m in ("best_action_share", "acceptable_share", "mean_regret_eur", "impermissible_share")} for sp in v}
    for k, v in res.get("task_B2", {}).items():
        s[f"B2/{k}"] = {sp: v[sp].get("scorecard_score_0_100") for sp in v}
    for k, v in res.get("task_C2", {}).items():
        s[f"C2/{k}"] = {sp: {m: v[sp].get(m) for m in ("mean_regret_eur", "value_capture_share")} for sp in v}
    return s


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "quickstart")
