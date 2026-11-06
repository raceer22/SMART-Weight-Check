"""Baseline 2 — transparent rules-based anomaly detector (Task B).

Every rule is a single readable condition on public data (plus Baseline 1 expected charges).
Known blind spots are deliberate: rules ignore legitimate explanations they cannot see.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from b1_economic_calculator import compute  # noqa: E402
from europress_data.sdk import open_dataset  # noqa: E402

LEGIT = ("MAX_INTERVAL_RULE", "CUSTOMER_REQUEST_PRE_CLOSURE", "DECOMMISSION", "CUSTOMER_REQUEST")


def collection_features(root, b1: pd.DataFrame | None = None) -> pd.DataFrame:
    if b1 is None:
        b1, _ = compute(root)
    con = open_dataset(root)
    ce = con.sql("""SELECT c.*, d.material_stream, d.collection_policy, d.fixed_schedule_per_week, d.has_weight_measurement,
                    d.container_volume_m3, m.max_days_between_collections, m.credit_eligible
                    FROM collection_events c JOIN devices d USING (device_id) JOIN material_classes m USING (material_stream)""").df()
    wb = con.sql("SELECT operator_job_ref, allocated_net_kg, loads_on_vehicle, tare_method FROM weighbridge_tickets").df().drop_duplicates("operator_job_ref")
    full = con.sql("""SELECT c.collection_id, count(t.message_id) AS full_hours_72h FROM collection_events c
                      JOIN telemetry_dedup t ON t.device_id = c.device_id AND t.measured_at < c.actual_at
                      AND t.measured_at >= c.actual_at - INTERVAL 72 HOUR AND t.operational_state = 'FULL'
                      WHERE c.status IN ('COMPLETED','PARTIAL') GROUP BY 1""").df()
    prev = con.sql("""SELECT collection_id, epoch(actual_at - lag(actual_at) OVER (PARTITION BY device_id ORDER BY actual_at))/3600 AS hours_since_prev
                      FROM collection_events WHERE status IN ('COMPLETED','PARTIAL')""").df()
    con.close()
    f = ce.merge(b1[["collection_id", "mass_kg", "mass_basis", "grade", "collection_cost_eur", "collection_cost_eur_per_t", "benchmark_eur_per_t",
                     "material_credit_eur"]], on="collection_id", how="left")
    f = f.merge(wb, on="operator_job_ref", how="left").merge(full, on="collection_id", how="left").merge(prev, on="collection_id", how="left")
    f["full_hours_72h"] = f.full_hours_72h.fillna(0)
    f["delay_hours"] = (f.actual_at - f.scheduled_at).dt.total_seconds() / 3600
    min_f = 7.0 / f.max_days_between_collections
    opts = np.array([5.0, 3.0, 2.0, 1.0, 0.5, 0.25])
    f["at_min_frequency"] = [bool(pol != "ON_CALL" and not any((o >= mf - 1e-9) and (o < fr) for o in opts))
                             for pol, fr, mf in zip(f.collection_policy, f.fixed_schedule_per_week.fillna(0), min_f)]
    f["cost_ratio"] = f.collection_cost_eur_per_t / f.benchmark_eur_per_t
    f["wb_diff_kg"] = f.device_estimated_collected_kg - f.allocated_net_kg
    f["wb_diff_rel"] = f.wb_diff_kg / f.allocated_net_kg.where(f.allocated_net_kg > 0)
    return f


def detect_collections(f: pd.DataFrame) -> pd.DataFrame:
    done = f.status.isin(["COMPLETED", "PARTIAL"])
    out = []

    def add(mask, fam):
        for cid in f.loc[mask & done, "collection_id"]:
            out.append(("collection", cid, fam))
    sched = f.original_trigger_type == "SCHEDULED"
    add(sched & (f.device_fill_pct_before < 40) & ~f.at_min_frequency, "PREMATURE_UNJUSTIFIED")
    add((f.cost_ratio > 2.0) & ~f.original_trigger_type.isin(LEGIT) & ~f.at_min_frequency & (f.status == "COMPLETED"), "COST_PER_T_HIGH")
    add((f.full_hours_72h >= 12) | (f.delay_hours > 24), "DELAYED_COLLECTION")
    add((f.wb_diff_kg.abs() > 100) & (f.wb_diff_rel.abs() > 0.10) & (f.loads_on_vehicle == 1) & (f.driver_reported_side_waste != True), "WEIGHT_DISCREPANCY")
    add(f.grade == "C", "CONTAMINATION_VALUE_LOSS")
    add(f.grade == "R", "REJECTED_LOAD")
    return pd.DataFrame(out, columns=["entity_type", "entity_id", "label_family"])


def detect_invoices(root, b1: pd.DataFrame, b1_lines: pd.DataFrame) -> pd.DataFrame:
    con = open_dataset(root)
    il = con.sql("SELECT l.*, i.contract_id, i.billing_period FROM invoice_lines l JOIN invoices i USING (invoice_id)").df()
    cv = con.sql("SELECT * FROM contract_versions").df()
    con.close()
    out = []
    jobs = set(b1.operator_job_ref)
    by_date = b1.assign(sd=pd.to_datetime(b1.service_date).dt.date).groupby(["contract_id", "sd"]).operator_job_ref.apply(list)
    exp = b1_lines.groupby(["operator_job_ref", "line_type"]).agg(amount=("amount_eur", "sum"), qty=("quantity", "first"),
                                                                 price=("unit_price_eur", "first")).to_dict("index")
    prev_price = {}
    for c, g in cv.sort_values("version_no").groupby("contract_id"):
        g = g.reset_index(drop=True)
        for i in range(1, len(g)):
            prev_price[(c, g.loc[i, "effective_from"].date() if hasattr(g.loc[i, "effective_from"], "date") else g.loc[i, "effective_from"])] = g.loc[i - 1]
    il = il.sort_values(["invoice_id", "line_no"])
    seen = set()
    for r in il.itertuples():
        if r.line_type == "RENTAL":
            continue
        ref = r.operator_job_ref
        if ref not in jobs:
            sd = pd.Timestamp(r.service_date).date()
            if (r.contract_id, sd) in by_date.index:
                cands = by_date[(r.contract_id, sd)]
                ref = cands[0]               # tolerate job-ref typos when contract + date match
            else:
                out.append(("invoice_line", r.invoice_line_id, "UNMATCHED_LINE"))
                continue
        key = (ref, r.line_type)
        if key in seen:
            out.append(("invoice_line", r.invoice_line_id, "DUPLICATE_LINE"))
            continue
        seen.add(key)
        e = exp.get(key)
        if e is None:
            out.append(("invoice_line", r.invoice_line_id, "WRONG_SURCHARGE" if r.line_type in ("REMOTE_SURCHARGE", "FUEL_SURCHARGE") else "UNMATCHED_LINE"))
            continue
        if abs(r.amount_eur - e["amount"]) < 0.005:
            continue
        if r.unit == "t" and abs(r.quantity - e["qty"]) > 0.0005:
            out.append(("invoice_line", r.invoice_line_id, "WEIGHT_BASIS_MISMATCH"))
        elif r.line_type in ("FUEL_SURCHARGE", "TRANSPORT", "REMOTE_SURCHARGE") and abs(r.quantity - e["qty"]) > 1e-6:
            out.append(("invoice_line", r.invoice_line_id, "WRONG_SURCHARGE"))
        else:
            out.append(("invoice_line", r.invoice_line_id, "OUTDATED_TARIFF"))
    # expected but absent
    billed = set(zip(il.operator_job_ref, il.line_type))
    billed_jobs = set(il.operator_job_ref)
    months = set(zip(il.contract_id, il.billing_period))
    b1i = b1.drop_duplicates("operator_job_ref").set_index("operator_job_ref")
    for (ref, lt), e in exp.items():
        row = b1i.loc[ref]
        if (row.contract_id, str(row.service_date)[:7]) not in months:
            continue                           # invoice not issued yet
        if ref not in billed_jobs and row.status in ("COMPLETED", "PARTIAL"):
            out.append(("collection", row.collection_id, "UNINVOICED_COLLECTION"))
        elif ref in billed_jobs and (ref, lt) not in billed and lt in ("MATERIAL_CREDIT", "LIFT_FEE", "TRANSPORT"):
            out.append(("collection", row.collection_id, "MISSING_LINE"))
    return pd.DataFrame(out, columns=["entity_type", "entity_id", "label_family"]).drop_duplicates()


def run(root):
    b1, b1l = compute(root)
    f = collection_features(root, b1)
    return pd.concat([detect_collections(f), detect_invoices(root, b1, b1l)], ignore_index=True), f, b1


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "data/quickstart/public"
    pred, _, _ = run(root)
    pred.to_csv(sys.argv[2] if len(sys.argv) > 2 else "b2_predictions.csv", index=False)
    print(pred.label_family.value_counts())
