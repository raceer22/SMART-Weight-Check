"""Baseline 1 — transparent economic calculator (Task A).

Reconstructs expected charges per collection event using ONLY public tables:
  contract version (by local service date) x billing mass x grade x index price.
Mass basis fallback chain (each step is reported, nothing is silently imputed):
  1. published weighbridge ticket (allocated_net_kg)          -> WEIGHBRIDGE
  2. per-tonne quantity on the operator invoice               -> INVOICE_QUANTITY
  3. device-side estimate (before - after)                     -> DEVICE_ESTIMATE
  4. otherwise NULL                                            -> UNKNOWN (per-tonne results NULL)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from europress_data.economics import price_event, summarize  # noqa: E402
from europress_data.sdk import open_dataset  # noqa: E402


def load_inputs(root):
    con = open_dataset(root)
    ce = con.sql("""SELECT c.*, CAST(timezone('Europe/Helsinki', coalesce(actual_at, scheduled_at)) AS DATE) AS service_date,
                    d.material_stream, m.credit_eligible, ct.price_index_id
                    FROM collection_events c JOIN devices d USING (device_id) JOIN material_classes m USING (material_stream)
                    JOIN contracts ct ON ct.contract_id = c.contract_id""").df()
    cv = con.sql("SELECT * FROM contract_versions ORDER BY contract_id, version_no").df()
    wb = con.sql("SELECT operator_job_ref, ticket_id, allocated_net_kg, loads_on_vehicle, tare_method, net_kg FROM weighbridge_tickets").df()
    qa = con.sql("SELECT ticket_id, grade FROM quality_assessments").df()
    il = con.sql("SELECT l.*, i.contract_id FROM invoice_lines l JOIN invoices i USING (invoice_id)").df()
    pi = con.sql("SELECT index_id, month, price_eur_per_t FROM price_index_monthly").df()
    return con, ce, cv, wb, qa, il, pi


def compute(root) -> tuple[pd.DataFrame, pd.DataFrame]:
    con, ce, cv, wb, qa, il, pi = load_inputs(root)
    vers = {k: g.to_dict("records") for k, g in cv.groupby("contract_id")}
    wbm = wb.merge(qa, on="ticket_id", how="left").drop_duplicates("operator_job_ref").set_index("operator_job_ref")
    inv_t = il[il.unit == "t"].groupby("operator_job_ref").quantity.max()
    inv_types = il.groupby("operator_job_ref").line_type.apply(set)
    idx = {(r.index_id, r.month): int(round(r.price_eur_per_t * 100)) for r in pi.itertuples()}
    rows, lines = [], []
    for r in ce.itertuples():
        vl = vers[r.contract_id]
        v = vl[0]
        for vv in vl:
            if vv["effective_from"] <= r.service_date:
                v = vv
        kg, basis, grade = None, "NOT_A_LIFT", None
        if r.status in ("COMPLETED", "PARTIAL"):
            if r.operator_job_ref in wbm.index:
                kg, basis = max(0, int(wbm.loc[r.operator_job_ref, "allocated_net_kg"])), "WEIGHBRIDGE"
                g = wbm.loc[r.operator_job_ref, "grade"]
                grade = g if isinstance(g, str) else None
            elif r.operator_job_ref in inv_t.index:
                kg, basis = int(round(inv_t[r.operator_job_ref] * 1000)), "INVOICE_QUANTITY"
            elif pd.notna(r.device_estimated_collected_kg):
                kg, basis = max(0, int(round(r.device_estimated_collected_kg))), "DEVICE_ESTIMATE"
            else:
                basis = "UNKNOWN"
            if r.credit_eligible and grade is None:
                types = inv_types.get(r.operator_job_ref, set())
                grade = "R" if "REJECTION_REPROCESSING" in types else "C" if "CONTAMINATION_PENALTY" in types else "A"
        ix = idx.get((r.price_index_id, str(r.service_date)[:7])) if r.credit_eligible else None
        res = price_event(v, r.status, kg, grade, ix, emergency=r.original_trigger_type == "AD_HOC_CUSTOMER",
                          side_waste=bool(False if pd.isna(r.driver_reported_side_waste) else r.driver_reported_side_waste), notice_hours=None if pd.isna(r.cancellation_notice_hours) else float(r.cancellation_notice_hours),
                          credit_eligible=bool(r.credit_eligible))
        if r.status in ("COMPLETED", "PARTIAL") and kg is None:
            # mass unknown: report only mass-independent lines; per-tonne results stay NULL
            pass
        s = summarize(res["lines"], kg)
        rows.append({"collection_id": r.collection_id, "device_id": r.device_id, "contract_id": r.contract_id,
                     "contract_version_id": v["contract_version_id"], "operator_job_ref": r.operator_job_ref,
                     "status": r.status, "service_date": r.service_date, "mass_kg": kg, "mass_basis": basis, "grade": grade,
                     "collection_cost_eur": s["collection_cost_cents"] / 100, "processing_cost_eur": s["processing_cost_cents"] / 100,
                     "penalties_eur": s["penalties_cents"] / 100, "material_credit_eur": s["material_credit_cents"] / 100,
                     "net_material_contribution_eur": s["net_material_contribution_cents"] / 100,
                     "collection_cost_eur_per_t": s["collection_cost_eur_per_t"],
                     "benchmark_eur_per_t": v["target_collection_cost_cents_per_t"] / 100,
                     "mass_known": kg is not None})
        for k, ln in enumerate(res["lines"]):
            lines.append({"collection_id": r.collection_id, "operator_job_ref": r.operator_job_ref, "line_type": ln["line_type"],
                          "quantity": float(ln["quantity"]), "unit_price_eur": ln["unit_price_cents"] / 100, "amount_eur": ln["amount_cents"] / 100})
    con.close()
    return pd.DataFrame(rows), pd.DataFrame(lines)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "data/quickstart/public"
    out, _ = compute(root)
    out.to_csv(sys.argv[2] if len(sys.argv) > 2 else "b1_predictions.csv", index=False)
    print(out.mass_basis.value_counts())
