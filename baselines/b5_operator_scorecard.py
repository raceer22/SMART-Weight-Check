"""Baseline 5 — operator performance scorecard from public data only (Task B2).

Each metric is computed the obvious way from the records a customer actually has:
  punctuality, missed visits, order-to-lift time  -> collection_events (exact, they are the customer's own records)
  weighbridge sharing and lag                     -> weighbridge tickets that were shared (published before extraction)
  billing over/under-charge                       -> invoices vs. Baseline 1 contract-expected charges per job
  weight bias                                     -> operator allocated net vs. the device's own mass estimate
Known blind spots (deliberate): Baseline 1 uses the invoice tonnage when no ticket is shared, so on unshared jobs an
invoice tonnage that differs from the weighbridge record looks correct; device estimates carry sensor drift and calibration errors.

python baselines/b5_operator_scorecard.py competition
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from b1_economic_calculator import compute  # noqa: E402

TZ = "Europe/Helsinki"
KEY = ["operator_id", "region_code", "month"]


def scorecard(pub: Path, b1=None, b1l=None) -> pd.DataFrame:
    if b1 is None:
        b1, b1l = compute(pub)
    ce = pd.read_parquet(pub / "operations" / "collection_events.parquet")
    sites = pd.read_parquet(pub / "reference" / "sites.parquet", columns=["site_id", "region_code"])
    ce = ce.merge(sites, on="site_id")
    jobs = ce[ce.status.isin(["COMPLETED", "PARTIAL", "MISSED_BY_OPERATOR", "WASTED_TRIP"])].copy()
    jobs["month"] = jobs.scheduled_at.dt.tz_convert(TZ).dt.strftime("%Y-%m")
    comp = jobs[jobs.status.isin(["COMPLETED", "PARTIAL"])].copy()
    comp["on_time"] = ((comp.actual_at - comp.scheduled_at).dt.total_seconds() / 3600).abs() <= 2
    comp["o2l"] = (comp.actual_at - comp.order_placed_at).dt.total_seconds() / 3600
    sc = pd.DataFrame({"missed_visit_rate": jobs.groupby(KEY).status.apply(lambda s: float((s == "MISSED_BY_OPERATOR").mean()))})
    g = comp.groupby(KEY)
    sc["on_time_rate"] = g.on_time.mean()
    sc["median_order_to_lift_hours"] = g.o2l.median()
    wb = pd.read_parquet(pub / "operations" / "weighbridge_tickets.parquet",
                         columns=["operator_job_ref", "arrival_at", "published_at", "allocated_net_kg"]).drop_duplicates("operator_job_ref")
    w = comp.merge(wb, on="operator_job_ref", how="left")
    lag = (w.published_at - w.arrival_at).dt.total_seconds() / 86400
    w["shared7"] = lag.notna() & (lag <= 7)
    w["lag"] = lag
    gw = w.groupby(KEY)
    sc["weighbridge_shared_7d_rate"] = gw.shared7.mean()
    sc["median_share_lag_days"] = gw.lag.median()
    both = w.dropna(subset=["allocated_net_kg", "device_estimated_collected_kg"])
    both = both[both.device_estimated_collected_kg > 50]
    gb = both.groupby(KEY)
    sc["weight_bias_pct"] = 100 * (gb.allocated_net_kg.sum() - gb.device_estimated_collected_kg.sum()) / gb.device_estimated_collected_kg.sum()
    # billing: billed vs Baseline-1 expected per (job, line type); unknown jobs and duplicates count fully
    inv = pd.read_parquet(pub / "finance" / "invoices.parquet", columns=["invoice_id", "contract_id", "operator_id", "billing_period"])
    il = pd.read_parquet(pub / "finance" / "invoice_lines.parquet")
    ct = pd.read_parquet(pub / "reference" / "contracts.parquet", columns=["contract_id", "site_id"]).merge(sites, on="site_id")
    il = il.merge(inv, on="invoice_id").merge(ct[["contract_id", "region_code"]], on="contract_id").rename(columns={"billing_period": "month"})
    il = il[il.line_type != "RENTAL"].copy()
    exp = b1l.groupby(["operator_job_ref", "line_type"]).amount_eur.sum()
    il["dup"] = il.duplicated(["operator_job_ref", "line_type"], keep="first")
    il["exp"] = [0.0 if d else exp.get((r, t), 0.0) for r, t, d in zip(il.operator_job_ref, il.line_type, il.dup)]
    il["diff"] = il.amount_eur - il.exp
    gi = il.groupby(KEY)
    expected_total = gi.exp.sum()
    sc["billing_overcharge_pct"] = 100 * gi["diff"].apply(lambda s: s[s > 0.005].sum()) / expected_total.where(expected_total.abs() > 1)
    # expected charges that never appear on an invoice (completed jobs only, invoice month issued)
    billed_refs = set(il.operator_job_ref.dropna())
    b1c = b1[b1.status.isin(["COMPLETED", "PARTIAL"]) & ~b1.operator_job_ref.isin(billed_refs)].copy()
    b1c = b1c.merge(ce[["collection_id", "operator_id", "region_code"]], on="collection_id")
    b1c["month"] = pd.to_datetime(b1c.service_date).dt.strftime("%Y-%m")
    issued_months = set(zip(inv.contract_id, inv.billing_period))
    b1c = b1c[[(c, m) in issued_months for c, m in zip(b1c.contract_id, b1c.month)]]
    missing = (-b1c.net_material_contribution_eur).groupby([b1c.operator_id, b1c.region_code, b1c.month]).sum()
    missing.index.names = KEY
    under_lines = gi["diff"].apply(lambda s: -s[s < -0.005].sum())
    sc["billing_undercharge_pct"] = 100 * under_lines.add(missing, fill_value=0) / expected_total.where(expected_total.abs() > 1)
    sc["discrepant_line_rate"] = gi["diff"].apply(lambda s: float((s.abs() > 0.005).mean()))
    return sc.reset_index()


if __name__ == "__main__":
    prof = sys.argv[1] if len(sys.argv) > 1 else "quickstart"
    print(scorecard(ROOT / "data" / prof / "public").round(3).head(20).to_string())
