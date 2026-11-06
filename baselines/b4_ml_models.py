"""Baseline 4 — simple ML (scikit-learn gradient boosting, no paid APIs).

(a) Task B: one classifier per collection-level label family, trained on TRAIN-period labels.
(b) Task C: multiclass classifier predicting best_action from as-of case features, restricted to the
    case's candidate actions at prediction time.
Thresholds are fixed (0.5) — deliberately simple so teams can beat it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

B_FAMILIES = ["PREMATURE_UNJUSTIFIED", "COST_PER_T_HIGH", "DELAYED_COLLECTION", "WEIGHT_DISCREPANCY", "CONTAMINATION_VALUE_LOSS"]
NUM = ["device_fill_pct_before", "device_fill_pct_after", "device_mass_kg_before", "device_estimated_collected_kg", "mass_kg",
       "collection_cost_eur_per_t", "cost_ratio", "full_hours_72h", "delay_hours", "hours_since_prev", "allocated_net_kg",
       "wb_diff_kg", "wb_diff_rel", "loads_on_vehicle", "container_volume_m3", "fixed_schedule_per_week", "max_days_between_collections"]
CAT = ["trigger_type", "original_trigger_type", "collection_policy", "material_stream", "grade", "tare_method", "mass_basis", "status"]


def _X(f: pd.DataFrame, cols=None) -> pd.DataFrame:
    X = f[NUM].astype(float).copy()
    X["at_min_frequency"] = f.at_min_frequency.astype(float)
    X["side_waste"] = f.driver_reported_side_waste.astype("float")
    X["has_weight"] = f.has_weight_measurement.astype(float)
    X = pd.concat([X, pd.get_dummies(f[CAT].astype(str), dtype=float)], axis=1)
    if cols is not None:
        X = X.reindex(columns=cols, fill_value=0.0)
    return X


def task_b(f_train: pd.DataFrame, labels: pd.DataFrame, f_pred: pd.DataFrame) -> pd.DataFrame:
    tr = f_train[f_train.status.isin(["COMPLETED", "PARTIAL"])]
    X = _X(tr)
    Xp = _X(f_pred[f_pred.status.isin(["COMPLETED", "PARTIAL"])], X.columns)
    ids = f_pred[f_pred.status.isin(["COMPLETED", "PARTIAL"])].collection_id.values
    out = []
    for fam in B_FAMILIES:
        pos = set(labels[(labels.label_family == fam) & labels.is_actionable].entity_id)
        y = tr.collection_id.isin(pos).astype(int).values
        if y.sum() < 5:
            continue
        m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, random_state=0).fit(X, y)
        p = m.predict_proba(Xp)[:, 1]
        out += [("collection", cid, fam) for cid in ids[p >= 0.5]]
    return pd.DataFrame(out, columns=["entity_type", "entity_id", "label_family"])


C_NUM = ["n_lifts_56d", "med_fill_56d", "adhoc_share_56d", "side_share_56d", "n_skips_56d", "wb_diff_share_90d", "full_hours_28d",
         "bad_mass_share_14d", "n_grade_cr_90d", "fixed_schedule_per_week", "on_call_threshold_pct", "container_volume_m3",
         "max_days_between_collections", "invoice_flags_90d"]


def _XC(f, cols=None):
    X = f[C_NUM].astype(float).copy()
    X["has_weight"] = f.has_weight_measurement.astype(float)
    X["credit_eligible"] = f.credit_eligible.astype(float)
    X = pd.concat([X, pd.get_dummies(f[["collection_policy", "material_stream"]].astype(str), dtype=float)], axis=1)
    return X.reindex(columns=cols, fill_value=0.0) if cols is not None else X


def task_c(f_train: pd.DataFrame, truth: pd.DataFrame, f_pred: pd.DataFrame) -> pd.DataFrame:
    tr = f_train.merge(truth[["case_id", "best_action"]], on="case_id")
    X = _XC(tr)
    m = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, random_state=0).fit(X, tr.best_action)
    P = m.predict_proba(_XC(f_pred, X.columns))
    classes = list(m.classes_)
    out = []
    for i, r in enumerate(f_pred.itertuples()):
        cands = r.candidate_actions.split(",")
        best = max(cands, key=lambda a: P[i, classes.index(a)] if a in classes else -1)
        out.append({"case_id": r.case_id, "action": best})
    return pd.DataFrame(out)
