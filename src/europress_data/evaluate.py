"""Scoring harness for Tasks A, B, B2, C and C2.

python -m europress_data.evaluate --task A --pred predictions.csv --labels data/competition/public/labels_dev --split validation
For the private test: --labels data/competition/private_evaluation/labels_test --split test

Submission formats (CSV or Parquet):
  Task A: collection_id, collection_cost_eur, processing_cost_eur, penalties_eur, material_credit_eur,
          net_material_contribution_eur, collection_cost_eur_per_t (NULL allowed = "cannot be computed")
  Task B: entity_type, entity_id, label_family            (one row per predicted positive)
  Task C: case_id, action [, verify_weight_sensor (bool), review_invoices (bool)]
  Task B2: operator_id, region_code, month, <any of the scorecard metrics>   (labels file: operator_scorecard)
  Task C2: case_id, actions   (semicolon or comma list of chosen actions; empty / missing = no action)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TASK_B_FAMILIES = ["PREMATURE_UNJUSTIFIED", "COST_PER_T_HIGH", "DELAYED_COLLECTION", "WEIGHT_DISCREPANCY",
                   "CONTAMINATION_VALUE_LOSS", "REJECTED_LOAD", "OUTDATED_TARIFF", "DUPLICATE_LINE", "WRONG_SURCHARGE",
                   "WEIGHT_BASIS_MISMATCH", "UNMATCHED_LINE", "MISSING_LINE", "UNINVOICED_COLLECTION"]
CONSTRAINT_PENALTY_EUR = 500.0
# families whose label is (almost) a direct read of a public operator record; reported, but excluded from
# macro_f1_detection_only because they test reconstruction/explanation rather than detection
DIRECTLY_OBSERVABLE = {"REJECTED_LOAD", "CONTAMINATION_VALUE_LOSS"}


def _read(p):
    p = Path(p)
    return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)


def _period_filter(df, labels_dir: Path, split: str, time_col="event_at"):
    if split in (None, "all"):
        return df
    man = None
    for cand in [labels_dir.parent / "metadata" / "dataset_manifest.json"]:
        if cand.exists():
            man = json.load(open(cand))
    if man is None or split not in man["label_periods"]:
        return df
    a, b = man["label_periods"][split]
    t = pd.to_datetime(df[time_col], utc=True).dt.tz_convert("Europe/Helsinki").dt.tz_localize(None)
    return df[(t >= pd.Timestamp(a)) & (t < pd.Timestamp(b))]


def score_a(pred: pd.DataFrame, labels_dir: Path, split: str) -> dict:
    ref = pd.read_parquet(labels_dir / "reference_economics.parquet")
    ref = _period_filter(ref, labels_dir, split, "eval_at")
    pred = pred.drop_duplicates("collection_id")
    m = ref.merge(pred, on="collection_id", how="left", suffixes=("", "_pred"))
    out = {"n_reference_events": len(ref), "n_predicted": int(m["collection_cost_eur_pred"].notna().sum()) if "collection_cost_eur_pred" in m else 0}
    out["coverage"] = round(out["n_predicted"] / max(len(ref), 1), 4)
    for c in ["collection_cost_eur", "processing_cost_eur", "penalties_eur", "material_credit_eur", "net_material_contribution_eur"]:
        if f"{c}_pred" not in m:
            continue
        err = (m[f"{c}_pred"] - m[c]).abs()
        out[f"{c}:exact_to_cent_share"] = round(float((err < 0.005).mean()), 4)      # missing predictions count as wrong
        out[f"{c}:mae_eur"] = round(float(err.mean()), 3) if err.notna().any() else None
    if "collection_cost_eur_per_t_pred" in m:
        m = m[m.status.isin(["COMPLETED", "PARTIAL"])]
        known = m.collection_cost_eur_per_t.notna()
        p = m.collection_cost_eur_per_t_pred
        out["per_t:coverage"] = round(float(p[known].notna().mean()), 4)
        ape = ((p - m.collection_cost_eur_per_t).abs() / m.collection_cost_eur_per_t.abs())[known & p.notna()]
        out["per_t:median_ape"] = round(float(ape.median()), 4) if len(ape) else None
        out["per_t:within_5pct_share"] = round(float((ape <= 0.05).mean()), 4) if len(ape) else None
        out["per_t:fabricated_where_reference_null"] = int((~known & p.notna()).sum())
        if "observable_mass_source" in m:
            none = m.observable_mass_source == "NONE"
            out["per_t:reported_where_no_observable_mass"] = int((none & p.notna()).sum())
            out["per_t:n_no_observable_mass"] = int(none.sum())
            for src in ("WEIGHBRIDGE_PUBLISHED", "INVOICE_TONNAGE", "DEVICE_ESTIMATE_ONLY"):
                sel = known & p.notna() & (m.observable_mass_source == src)
                a_ = ((p - m.collection_cost_eur_per_t).abs() / m.collection_cost_eur_per_t.abs())[sel]
                out[f"per_t:within_5pct_share[{src}]"] = round(float((a_ <= 0.05).mean()), 4) if len(a_) else None
    return out


def _entity_times(labels_dir: Path) -> pd.DataFrame:
    """Evaluation time of every scorable entity, computed from observable data exactly as the generator does:
    collections -> max(event time, issue of the invoice for its contract-month); executed but not yet invoiced ->
    extraction time; invoice lines -> invoice issue time."""
    roots = [labels_dir.parent, labels_dir.parent.parent / "public", labels_dir.parent / "holdout_full"]
    ext = None
    man = labels_dir.parent / "metadata" / "dataset_manifest.json"
    if man.exists():
        ext = pd.Timestamp(json.load(open(man))["extraction_time_utc"])
    parts = []
    for r in roots:
        ce, inv, il = r / "operations" / "collection_events.parquet", r / "finance" / "invoices.parquet", r / "finance" / "invoice_lines.parquet"
        if ce.exists() and inv.exists():
            c = pd.read_parquet(ce, columns=["collection_id", "contract_id", "status", "actual_at", "scheduled_at"])
            t = c.actual_at.fillna(c.scheduled_at)
            i = pd.read_parquet(inv, columns=["contract_id", "billing_period", "issued_at"])
            c = c.assign(t=t, billing_period=t.dt.tz_convert("Europe/Helsinki").dt.strftime("%Y-%m")).merge(i, on=["contract_id", "billing_period"], how="left")
            executed = c.status.isin(["COMPLETED", "PARTIAL", "WASTED_TRIP"])
            ev = c[["t", "issued_at"]].max(axis=1)
            if ext is not None:
                ev = ev.where(c.issued_at.notna() | ~executed, ext)
            parts.append(pd.DataFrame({"entity_id": c.collection_id, "eval_at": ev}))
        if inv.exists() and il.exists():
            i = pd.read_parquet(inv, columns=["invoice_id", "issued_at"])
            l = pd.read_parquet(il, columns=["invoice_line_id", "invoice_id"]).merge(i, on="invoice_id")
            parts.append(pd.DataFrame({"entity_id": l.invoice_line_id, "eval_at": l.issued_at}))
    return pd.concat(parts, ignore_index=True).drop_duplicates("entity_id") if parts else pd.DataFrame(columns=["entity_id", "eval_at"])


BILLING_FAMILIES = {"UNINVOICED_COLLECTION", "MISSING_LINE"}


def score_b(pred: pd.DataFrame, labels_dir: Path, split: str) -> dict:
    lab = pd.read_parquet(labels_dir / "anomaly_labels.parquet")
    lab = _period_filter(lab, labels_dir, split, "eval_at")
    lab = lab[lab.entity_type.isin(["collection", "invoice_line"])]
    ent = _period_filter(_entity_times(labels_dir), labels_dir, split, "eval_at")
    pred = pred.drop_duplicates(["entity_type", "entity_id", "label_family"])
    pred = pred[pred.entity_id.isin(set(ent.entity_id))]
    pred = pred.assign(label_family=pred.label_family.str.split(":").str[0])
    res, f1s = {}, []
    for fam in TASK_B_FAMILIES:
        pos = set(lab[(lab.label_family == fam) & lab.is_actionable].entity_id)
        expl = set(lab[(lab.label_family.isin([fam, "EARLY_JUSTIFIED"] if fam == "PREMATURE_UNJUSTIFIED" else [fam])) & ~lab.is_actionable].entity_id)
        pr = set(pred[pred.label_family == fam].entity_id)
        tp = len(pos & pr)
        prec = tp / len(pr) if pr else 0.0
        rec = tp / len(pos) if pos else (1.0 if not pr else 0.0)
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        val = lab[(lab.label_family == fam) & lab.is_actionable & lab.entity_id.isin(pr)].value_at_stake_eur.abs().sum()
        tot = lab[(lab.label_family == fam) & lab.is_actionable].value_at_stake_eur.abs().sum()
        res[fam] = {"positives": len(pos), "predicted": len(pr), "tp": tp, "precision": round(prec, 4), "recall": round(rec, 4),
                    "f1": round(f1, 4), "explained_flagged_as_anomaly": len(expl & pr),
                    "value_weighted_recall": round(float(val / tot), 4) if tot else None}
        if pos:
            f1s.append(f1)
    res["macro_f1"] = round(float(np.mean(f1s)), 4) if f1s else None
    det = [res[f]["f1"] for f in TASK_B_FAMILIES if f not in DIRECTLY_OBSERVABLE and res[f]["positives"]]
    res["macro_f1_detection_only"] = round(float(np.mean(det)), 4) if det else None
    return res


def score_c(pred: pd.DataFrame, labels_dir: Path, split: str) -> dict:
    tr = pd.read_parquet(labels_dir / "decision_truth.parquet")
    oc = pd.read_parquet(labels_dir / "decision_outcomes.parquet")
    if split not in (None, "all"):
        tr = tr[tr.split.isin([split] if split != "test" else ["test", "test_private"])]
    pred = pred.drop_duplicates("case_id")
    m = tr.merge(pred, on="case_id", how="left")
    m["action"] = m.action.fillna("NO_ACTION")        # no answer = doing nothing
    o = oc.set_index(["case_id", "action"])
    regrets, imperm, best, acc = [], 0, 0, 0
    for r in m.itertuples():
        best_cost = o.loc[(r.case_id, r.best_action)].adjusted_cost_cents
        if (r.case_id, r.action) not in o.index:          # not a candidate action for this case: invalid
            regrets.append((o.loc[(r.case_id, "NO_ACTION")].adjusted_cost_cents - best_cost) / 100 + CONSTRAINT_PENALTY_EUR)
            imperm += 1
            continue
        row = o.loc[(r.case_id, r.action)]
        reg = (row.adjusted_cost_cents - best_cost) / 100
        if not row.permissible:
            imperm += 1
            reg += CONSTRAINT_PENALTY_EUR
        regrets.append(reg)
        best += r.action == r.best_action
        acc += r.action in r.acceptable_actions.split(",")
    n = len(m)
    out = {"n_cases": n, "best_action_share": round(best / n, 4) if n else None, "acceptable_share": round(acc / n, 4) if n else None,
           "mean_regret_eur": round(float(np.mean(regrets)), 2) if n else None, "impermissible_share": round(imperm / n, 4) if n else None}
    noact = tr.merge(pd.DataFrame({"case_id": tr.case_id, "action": "NO_ACTION"}), on="case_id")
    out["reference_always_no_action_regret_eur"] = round(float(np.mean([(o.loc[(c, "NO_ACTION")].adjusted_cost_cents - o.loc[(c, b)].adjusted_cost_cents) / 100
                                                                        for c, b in zip(noact.case_id, noact.best_action)])), 2) if n else None
    for col, truth in (("verify_weight_sensor", m.truth_sensor_issue_active.notna()), ("review_invoices", m.truth_invoice_overcharge_90d_eur > 20)):
        if col in m:
            p = m[col].fillna(False).astype(bool)
            tp = int((p & truth).sum())
            out[f"{col}:precision"] = round(tp / p.sum(), 4) if p.sum() else None
            out[f"{col}:recall"] = round(tp / truth.sum(), 4) if truth.sum() else None
    return out


# ------------------------------------------------------------------ Task B2: operator performance scorecard
# tolerance per metric: an absolute error equal to the tolerance scores 0, a perfect value scores 1
B2_TOLERANCE = {"on_time_rate": 0.10, "missed_visit_rate": 0.02, "weighbridge_shared_7d_rate": 0.10, "median_share_lag_days": 3.0,
                "billing_overcharge_pct": 1.5, "billing_undercharge_pct": 1.5, "discrepant_line_rate": 0.02, "weight_bias_pct": 2.0,
                "median_order_to_lift_hours": 6.0}
B2_MIN_JOBS = 10


def score_b2(pred: pd.DataFrame, labels_dir: Path, split: str) -> dict:
    lab = pd.read_parquet(labels_dir / "operator_scorecard.parquet")
    if split not in (None, "all"):
        lab = lab[lab.split == split] if split != "test" else lab
    lab = lab[lab.n_operator_jobs >= B2_MIN_JOBS]
    key = ["operator_id", "region_code", "month"]
    pred = pred.drop_duplicates(key)
    m = lab.merge(pred, on=key, how="left", suffixes=("", "_pred"))
    out = {"n_rows": len(m), "min_jobs_per_row": B2_MIN_JOBS}
    scores = []
    for c, tol in B2_TOLERANCE.items():
        pc = f"{c}_pred"
        if pc not in m:
            out[f"{c}:score"] = 0.0
            scores.append(0.0)
            continue
        sel = m[c].notna()
        err = (m.loc[sel, pc] - m.loc[sel, c]).abs()
        sc_ = (1 - (err / tol).clip(upper=1)).fillna(0.0)          # missing prediction = 0
        out[f"{c}:mae"] = round(float(err.mean()), 4) if err.notna().any() else None
        out[f"{c}:score"] = round(float(sc_.mean()), 4) if len(sc_) else None
        if len(sc_):
            scores.append(float(sc_.mean()))
        # ranking: do the predictions order operators within a region-month like the truth does?
        g = m.loc[sel & m[pc].notna()].groupby(["region_code", "month"])
        rho = [x[c].rank().corr(x[pc].rank()) for _, x in g if len(x) >= 3 and x[c].nunique() > 1]
        out[f"{c}:mean_rank_corr"] = round(float(np.nanmean(rho)), 4) if rho else None
    out["scorecard_score_0_100"] = round(100 * float(np.mean(scores)), 2) if scores else None
    return out


# ------------------------------------------------------------------ Task C2: operator and contract actions
C2_ACTIONS = ["DISPUTE_INVOICE", "REQUEST_WEIGHBRIDGE_DATA", "RENEGOTIATE_CONTRACT", "TENDER_OR_SWITCH_OPERATOR"]


def _set_value(vals: dict, chosen: set) -> float:
    v = sum(vals.get(a, 0.0) for a in chosen if a in ("DISPUTE_INVOICE", "REQUEST_WEIGHBRIDGE_DATA"))
    exclusive = [a for a in chosen if a in ("RENEGOTIATE_CONTRACT", "TENDER_OR_SWITCH_OPERATOR")]
    if len(exclusive) == 2:          # both started: the effort of both is spent, only the worse outcome counts
        v += min(vals.get(a, 0.0) for a in exclusive)
    elif exclusive:
        v += vals.get(exclusive[0], 0.0)
    return v


def score_c2(pred: pd.DataFrame, labels_dir: Path, split: str) -> dict:
    lab = pd.read_parquet(labels_dir / "operator_action_values.parquet")
    if split in ("dev", "test"):
        lab = lab[lab.split == split]
    vals = {c: dict(zip(g.action, g.value_eur)) for c, g in lab.groupby("case_id")}
    best = lab.groupby("case_id").best_set_value_eur.first()
    col = "actions" if "actions" in pred.columns else ("action" if "action" in pred.columns else None)
    chosen = {}
    if col:
        for c, a in zip(pred.case_id, pred[col].fillna("")):
            chosen[c] = {x.strip() for x in str(a).replace(";", ",").split(",") if x.strip() and x.strip() != "NO_ACTION"}
    regret, captured, invalid = [], [], 0
    tp = {a: 0 for a in C2_ACTIONS}
    npred = {a: 0 for a in C2_ACTIONS}
    npos = {a: 0 for a in C2_ACTIONS}
    for c, v in vals.items():
        ch = chosen.get(c, set())
        bad = {a for a in ch if a not in v}
        invalid += bool(bad)
        ch = ch - bad
        val = _set_value(v, ch)
        regret.append(best[c] - val)
        captured.append(val)
        for a in C2_ACTIONS:
            if a in v:
                npos[a] += v[a] > 0
                npred[a] += a in ch
                tp[a] += (a in ch) and v[a] > 0
    n = len(vals)
    out = {"n_cases": n, "mean_regret_eur": round(float(np.mean(regret)), 2) if n else None,
           "value_captured_eur": round(float(np.sum(captured)), 2), "best_possible_value_eur": round(float(best.sum()), 2),
           "value_capture_share": round(float(np.sum(captured) / best.sum()), 4) if best.sum() > 0 else None,
           "cases_with_invalid_actions": invalid,
           "reference_no_action_regret_eur": round(float(best.mean()), 2) if n else None}
    for a in C2_ACTIONS:
        out[f"{a}:precision"] = round(tp[a] / npred[a], 4) if npred[a] else None
        out[f"{a}:recall"] = round(tp[a] / npos[a], 4) if npos[a] else None
        out[f"{a}:n_positive"] = npos[a]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=["A", "B", "B2", "C", "C2"])
    ap.add_argument("--pred", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--split", default="validation")
    a = ap.parse_args(argv)
    f = {"A": score_a, "B": score_b, "B2": score_b2, "C": score_c, "C2": score_c2}[a.task]
    print(json.dumps(f(_read(a.pred), Path(a.labels), a.split), indent=2))


if __name__ == "__main__":
    sys.exit(main())
