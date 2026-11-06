"""Baseline 6 — transparent rules for operator and contract actions (Task C2), public data only.

DISPUTE_INVOICE           if Baseline-2 flagged lines on undisputed invoices of the last 90 days add up to more
                          than the admin cost / recovery rate (estimated recoverable = billed - B1 expected)
REQUEST_WEIGHBRIDGE_DATA  if it is a candidate, the device has no weight measurement, and per-tonne charges are
                          material (> 1 500 EUR/year)
RENEGOTIATE_CONTRACT      if the contract re-priced at public peer-median terms (same region, material, pricing
                          model, size) is at least 12 % cheaper, using Baseline-1 masses
TENDER_OR_SWITCH_OPERATOR if an alternative operator's typical terms are at least 25 % cheaper and beat renegotiation
Valuation parameters come from configs/assumptions.yaml -> operator_actions (published). Blind spots (deliberate):
B1 masses inherit invoice tonnages that differ from the weighbridge record; operator billing quality is ignored when tendering.

python baselines/b6_operator_actions.py competition
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from b1_economic_calculator import compute  # noqa: E402
from b2_rules_anomaly import detect_invoices  # noqa: E402
from europress_data.operator_tasks import FEE_FIELDS, _bucket, _peer_table, _peer_version, _reprice  # noqa: E402


def decide(pub: Path, b1=None, b1l=None, flags=None) -> pd.DataFrame:
    OA = yaml.safe_load(open(ROOT / "configs" / "assumptions.yaml"))["operator_actions"]
    if b1 is None:
        b1, b1l = compute(pub)
    if flags is None:
        flags = detect_invoices(pub, b1, b1l)
    cases = pd.read_parquet(pub / "benchmark" / "operator_action_cases.parquet")
    dv = pd.read_parquet(pub / "reference" / "devices.parquet")
    ct = pd.read_parquet(pub / "reference" / "contracts.parquet")
    cv = pd.read_parquet(pub / "reference" / "contract_versions.parquet")
    sites = pd.read_parquet(pub / "reference" / "sites.parquet", columns=["site_id", "region_code"])
    mat = pd.read_parquet(pub / "reference" / "material_classes.parquet").set_index("material_stream").credit_eligible
    pi = pd.read_parquet(pub / "reference" / "price_index_monthly.parquet")
    inv = pd.read_parquet(pub / "finance" / "invoices.parquet")
    il = pd.read_parquet(pub / "finance" / "invoice_lines.parquet")
    cv_last = cv.sort_values("version_no").groupby("contract_id").tail(1)
    cvx = cv_last.merge(ct[["contract_id", "device_id", "operator_id", "material_stream", "site_id", "price_index_id"]], on="contract_id") \
        .merge(sites, on="site_id").merge(dv[["device_id", "container_volume_m3", "has_weight_measurement"]], on="device_id")
    cvx["bucket"] = cvx.container_volume_m3.map(_bucket)
    peers = _peer_table(cvx)
    ops = sorted(cvx.operator_id.unique())
    peers_op = {op: _peer_table(cvx[cvx.operator_id == op]) for op in ops}
    regions_of = cvx.groupby("operator_id").region_code.apply(set).to_dict()
    # Baseline-1 events in the repricing format
    idx = {(r.index_id, r.month): r.price_eur_per_t for r in pi.itertuples()}
    b = b1.merge(ct[["contract_id", "price_index_id"]], on="contract_id")
    types = b1l.groupby("collection_id").line_type.apply(set)
    ev = pd.DataFrame({"contract_id": b.contract_id, "status": b.status, "billing_mass_kg": b.mass_kg, "grade_applied": b.grade,
                       "index_price_eur_per_t": [idx.get((i, str(d)[:7])) for i, d in zip(b.price_index_id, b.service_date)],
                       "emergency": [("EMERGENCY_SURCHARGE" in types.get(c, set())) for c in b.collection_id],
                       "side_waste": [("SIDE_WASTE_FEE" in types.get(c, set())) for c in b.collection_id],
                       "cancel_fee": [("CANCELLATION_FEE" in types.get(c, set())) for c in b.collection_id]})
    # recoverable estimate from flagged invoice lines
    exp = b1l.groupby(["operator_job_ref", "line_type"]).amount_eur.sum()
    fl = flags[flags.entity_type == "invoice_line"].entity_id
    lines = il[il.invoice_line_id.isin(fl)].merge(inv[["invoice_id", "contract_id", "issued_at", "dispute_status"]], on="invoice_id")
    lines["dup"] = lines.duplicated(["operator_job_ref", "line_type"], keep="first")
    lines["est"] = [a if d else a - exp.get((r, t), 0.0) for a, r, t, d in zip(lines.amount_eur, lines.operator_job_ref, lines.line_type, lines.dup)]
    per_t = il[il.unit == "t"].merge(inv[["invoice_id", "contract_id"]], on="invoice_id").groupby("contract_id").amount_eur.sum()
    n_months = max(1, inv.billing_period.nunique())
    out = []
    for c in cases.itertuples(index=False):
        cand = set(c.candidate_actions.split(","))
        r = cvx[cvx.contract_id == c.contract_id].iloc[0]
        own = r[cv.columns].to_dict()
        cred = bool(mat[r.material_stream])
        e = ev[ev.contract_id == c.contract_id]
        ann = 12 / n_months
        chosen = []
        recent = lines[(lines.contract_id == c.contract_id) & (lines.issued_at > c.as_of_at - pd.Timedelta(days=OA["dispute_lookback_days"]))
                       & ~lines.dispute_status.isin(["RESOLVED_CREDIT_NOTE", "OPEN"])]
        if OA["dispute_recovery_rate"] * recent.est.clip(lower=0).sum() > OA["dispute_admin_cost_eur"]:
            chosen.append("DISPUTE_INVOICE")
        if "REQUEST_WEIGHBRIDGE_DATA" in cand and not bool(r.has_weight_measurement) and per_t.get(c.contract_id, 0) * ann > 1500:
            chosen.append("REQUEST_WEIGHBRIDGE_DATA")
        base = _reprice(e, own, cred)
        rowd = pd.Series(dict(region_code=r.region_code, material_stream=r.material_stream, pricing_model=own["pricing_model"], bucket=r.bucket))
        gap_r = gap_t = 0.0
        if "RENEGOTIATE_CONTRACT" in cand:
            p, _ = _peer_version(rowd, peers)
            if p is not None:
                nv = dict(own)
                for f in FEE_FIELDS:
                    nv[f] = int(round(p[f]))
                nv["credit_share_bp"] = int(round(p["credit_share_bp"] / 100) * 100) if cred else 0
                gap_r = (base - _reprice(e, nv, cred)) / max(base, 1)
        if "TENDER_OR_SWITCH_OPERATOR" in cand:
            for op in ops:
                if op == c.operator_id or r.region_code not in regions_of.get(op, set()):
                    continue
                p, _ = _peer_version(rowd, peers_op[op], min_n=2)
                if p is None:
                    continue
                av = dict(own)
                for f in FEE_FIELDS + ["free_km"]:
                    av[f] = int(round(p[f]))
                av["credit_share_bp"] = int(round(p["credit_share_bp"] / 100) * 100) if cred else 0
                gap_t = max(gap_t, (base - _reprice(e, av, cred)) / max(base, 1))
        if gap_t >= 0.25 and gap_t > gap_r:
            chosen.append("TENDER_OR_SWITCH_OPERATOR")
        elif gap_r >= 0.12:
            chosen.append("RENEGOTIATE_CONTRACT")
        out.append({"case_id": c.case_id, "actions": ";".join(chosen)})
    return pd.DataFrame(out)


if __name__ == "__main__":
    prof = sys.argv[1] if len(sys.argv) > 1 else "quickstart"
    d = decide(ROOT / "data" / prof / "public")
    print(d.actions.value_counts().head(10).to_string())
