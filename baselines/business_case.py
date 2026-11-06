"""Business-case CALCULATOR for a new service or business model built on device data (Task D).

    python baselines/business_case.py competition --params my_params.yaml --out my_business_case

The calculator takes YOUR parameters (prices, cost to serve, adoption, value realisation, future business models)
from a YAML file shaped like configs/commercial_assumptions.yaml. It ships no prices of its own: with the empty
template it stops and tells you which parameters are missing. configs/business_case_example_params.yaml is a
filled-in CALCULATION EXAMPLE, not a price estimate.

Value per customer is estimated from PUBLIC data with the transparent baselines (B1, B2, B6). Every output is a
hypothesis about a synthetic world, not evidence of market demand or real savings. Europress is currently not a
party to waste transport or treatment; tariffs, processing fees and credits are agreed between the customer and
the waste operator; all prices in this dataset are hypothetical.

Value levers (annualised, per customer, before realisation shares):
  billing_review        flagged invoice lines: billed - contract-expected (positive part)
  over_servicing        flagged premature lifts x logistics cost x unused share of an 80 % target fill
  contamination         material credit lost vs grade A on B/C/R loads
  contract_review       credit-eligible tonnes on 0 % credit-share contracts x mean index x 75 %
  operator_performance  emergency, side-waste and wasted-trip charges (service-level costs a scorecard can contest)
  operator_tendering    Baseline-6 renegotiation / tender gap x annual contract cost
Future hypotheses (enabled per file; they differ from today's role of Europress):
  transport_procurement     logistics spend x discount (Europress procures transport for the customer)
  tonne_based_full_service  customer spend x margin (one per-tonne price, Europress in the middle)
  materials_marketplace     credit-eligible tonnes x uplift per tonne
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from b1_economic_calculator import compute  # noqa: E402
from b2_rules_anomaly import run as run_rules  # noqa: E402

LEVERS = ["billing_review", "over_servicing", "contamination", "contract_review", "operator_performance", "operator_tendering"]
LOGISTICS_LINES = ("LIFT_FEE", "TRANSPORT", "REMOTE_SURCHARGE", "FUEL_SURCHARGE", "HAUL_PER_TONNE", "MIN_CHARGE_TOPUP")
SERVICE_LEVEL_LINES = ("EMERGENCY_SURCHARGE", "SIDE_WASTE_FEE", "WASTED_TRIP_FEE")


def check_params(P: dict) -> list:
    missing = []
    if not P.get("pricing", {}).get("price_per_device_month_eur") and not P["pricing"].get("price_per_site_month_eur") \
            and P["pricing"].get("share_of_verified_savings_pct") is None:
        missing.append("pricing: at least one of price_per_device_month_eur / price_per_site_month_eur / share_of_verified_savings_pct")
    for k, v in P.get("costs", {}).items():
        if v is None:
            missing.append(f"costs.{k}")
    if not P.get("adoption", {}).get("adoption_share_of_eligible_pct"):
        missing.append("adoption.adoption_share_of_eligible_pct")
    if P.get("adoption", {}).get("purchase_condition_value_multiple") is None:
        missing.append("adoption.purchase_condition_value_multiple")
    for k in LEVERS:
        if P.get("value_realisation", {}).get(k) is None:
            missing.append(f"value_realisation.{k}")
    for name, fm in P.get("future_models", {}).items():
        if fm.get("enabled"):
            for k, v in fm.items():
                if v is None:
                    missing.append(f"future_models.{name}.{k}")
    return missing


def customer_value(pub: Path) -> pd.DataFrame:
    pred, f, b1 = run_rules(pub)
    _, b1l = compute(pub)
    dv = pd.read_parquet(pub / "reference" / "devices.parquet")
    inv = pd.read_parquet(pub / "finance" / "invoices.parquet")
    il = pd.read_parquet(pub / "finance" / "invoice_lines.parquet").merge(inv[["invoice_id", "customer_id", "contract_id"]], on="invoice_id")
    cv = pd.read_parquet(pub / "reference" / "contract_versions.parquet")
    pi = pd.read_parquet(pub / "reference" / "price_index_monthly.parquet")
    mat = pd.read_parquet(pub / "reference" / "material_classes.parquet")
    months = inv.billing_period.nunique()
    ann = 12 / max(months, 1)
    spend = inv.groupby("customer_id").total_eur.sum() * ann
    # over-servicing
    pm = f[f.collection_id.isin(pred[pred.label_family == "PREMATURE_UNJUSTIFIED"].entity_id)]
    pm = pm.assign(v=pm.collection_cost_eur * (1 - pm.device_fill_pct_before.clip(0, 80) / 80))
    over = pm.groupby("customer_id").v.sum() * ann
    # billing review
    fl = pred[pred.entity_type == "invoice_line"].entity_id
    lines = il[il.invoice_line_id.isin(fl)].copy()
    exp = b1l.groupby(["operator_job_ref", "line_type"]).amount_eur.sum().rename("exp").reset_index()
    lines = lines.merge(exp, on=["operator_job_ref", "line_type"], how="left").fillna({"exp": 0})
    dup = lines.duplicated(["operator_job_ref", "line_type"], keep="first")
    lines["delta"] = np.where(dup, lines.amount_eur, lines.amount_eur - lines.exp)
    bill = lines[lines.delta > 0].groupby("customer_id").delta.sum() * ann
    # contamination
    cm = f[f.grade.isin(["B", "C", "R"])]
    cm = cm.assign(v=cm.material_credit_eur.fillna(0) * np.where(cm.grade == "B", 0.15 / 0.85, np.where(cm.grade == "C", 0.4 / 0.6, 0)))
    cont = cm.groupby("customer_id").v.sum() * ann
    # contract review: credit-eligible streams where the operator keeps all material value
    last = cv.sort_values("version_no").groupby("contract_id").tail(1)
    nocredit = last[last.credit_share_bp == 0].contract_id
    dvx = dv.merge(mat, on="material_stream")
    rec = dvx[dvx.credit_eligible & dvx.contract_id.isin(nocredit)]
    idx = pi.groupby("index_id").price_eur_per_t.mean()
    t = b1[b1.mass_known & b1.status.isin(["COMPLETED", "PARTIAL"])].groupby("device_id").mass_kg.sum() / 1000 * ann
    rec = rec.assign(v=rec.device_id.map(t).fillna(0) * rec.price_index_id.map(idx).clip(lower=0) * 0.75)
    contract = rec.groupby("customer_id").v.sum()
    # operator performance: service-level charges a scorecard can contest
    perf = il[il.line_type.isin(SERVICE_LEVEL_LINES)].groupby("customer_id").amount_eur.sum() * ann
    # operator tendering / renegotiation: Baseline 6 gap estimates
    tend = pd.Series(dtype=float)
    cases_p = pub / "benchmark" / "operator_action_cases.parquet"
    if cases_p.exists():
        from b6_operator_actions import decide
        from b2_rules_anomaly import detect_invoices
        flags = detect_invoices(pub, b1, b1l)
        d = decide(pub, b1, b1l, flags)
        cases = pd.read_parquet(cases_p)
        d = d.merge(cases[["case_id", "contract_id", "customer_id"]], on="case_id")
        contract_cost = il.groupby("contract_id").amount_eur.sum() * ann
        d = d[d.actions.str.contains("RENEGOTIATE|TENDER", regex=True)]
        tend = (d.contract_id.map(contract_cost).fillna(0) * 0.12).groupby(d.customer_id).sum()     # 12 % = B6 decision gap
    logistics = il[il.line_type.isin(LOGISTICS_LINES)].groupby("customer_id").amount_eur.sum() * ann
    cred_t = b1[b1.mass_known & b1.status.isin(["COMPLETED", "PARTIAL"])].merge(dvx[["device_id", "customer_id", "credit_eligible"]], on="device_id")
    cred_t = cred_t[cred_t.credit_eligible].groupby("customer_id").mass_kg.sum() / 1000 * ann
    out = pd.DataFrame({"annual_spend_eur": spend, "billing_review_eur": bill, "over_servicing_eur": over, "contamination_eur": cont,
                        "contract_review_eur": contract, "operator_performance_eur": perf, "operator_tendering_eur": tend,
                        "logistics_spend_eur": logistics, "credit_eligible_tonnes": cred_t}).fillna(0)
    out["n_devices"] = dv.groupby("customer_id").size()
    out["n_sites"] = dv.groupby("customer_id").site_id.nunique()
    out["share_devices_without_weight"] = 1 - dv.groupby("customer_id").has_weight_measurement.mean()
    out["dominant_material"] = dv.groupby("customer_id").material_stream.agg(lambda s: s.value_counts().index[0])
    out["segment"] = pd.cut(out.n_devices, [0, 1, 5, 15, 10 ** 6], labels=["1 device", "2-5", "6-15", "16+"]).astype(str)
    return out.reset_index(names="customer_id").fillna(0)


def scenarios(cv: pd.DataFrame, P: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    h = P["value_realisation"]
    cv = cv.copy()
    cv["identified_value_eur"] = cv[[f"{k}_eur" for k in LEVERS]].sum(axis=1)
    cv["realisable_value_eur"] = sum(cv[f"{k}_eur"] * float(h[k]) for k in LEVERS)
    fm = P.get("future_models", {})
    if fm.get("transport_procurement", {}).get("enabled"):
        x = fm["transport_procurement"]
        cv["future_transport_procurement_eur"] = cv.logistics_spend_eur * x["discount_on_logistics_pct"] / 100 * x["realisation"]
        cv["realisable_value_eur"] += cv.future_transport_procurement_eur
    if fm.get("materials_marketplace", {}).get("enabled"):
        x = fm["materials_marketplace"]
        cv["future_marketplace_eur"] = cv.credit_eligible_tonnes * x["credit_uplift_eur_per_t"] * x["realisation"]
        cv["realisable_value_eur"] += cv.future_marketplace_eur
    if fm.get("tonne_based_full_service", {}).get("enabled"):
        cv["future_tonne_service_margin_eur"] = cv.annual_spend_eur * fm["tonne_based_full_service"]["margin_on_customer_spend_pct"] / 100
    rows = []
    c = P["costs"]
    mult = float(P["adoption"]["purchase_condition_value_multiple"])
    prices = list(P["pricing"].get("price_per_device_month_eur") or [])
    site_p = P["pricing"].get("price_per_site_month_eur")
    for p in prices or [None]:
        fee = cv.n_devices * (p or 0) * 12 + cv.n_sites * (site_p or 0) * 12
        if p is not None:
            cv[f"value_multiple_at_{p}"] = (cv.realisable_value_eur / fee.where(fee > 0)).round(2)
        eligible = cv.realisable_value_eur >= mult * fee
        for a in P["adoption"]["adoption_share_of_eligible_pct"]:
            share = a / 100
            n_cust = eligible.sum() * share
            dev = (cv.n_devices[eligible] * share).sum()
            rev = (fee[eligible] * share).sum()
            if fm.get("tonne_based_full_service", {}).get("enabled"):
                rev += (cv.future_tonne_service_margin_eur[eligible] * share).sum()
            opex = dev * c["operating_cost_per_device_month_eur"] * 12 + n_cust * c["customer_support_per_customer_month_eur"] * 12
            onb = n_cust * c["onboarding_per_customer_eur"] + dev * c["onboarding_per_device_eur"]
            rows.append({"price_per_device_month_eur": p, "price_per_site_month_eur": site_p, "adoption_pct_of_eligible": a,
                         "eligible_customers": int(eligible.sum()), "adopting_customers_expected": round(n_cust, 1),
                         "devices_expected": round(dev, 1), "annual_revenue_eur": round(rev, 0), "annual_operating_cost_eur": round(opex, 0),
                         "one_off_onboarding_eur": round(onb, 0), "year1_contribution_eur": round(rev - opex - onb, 0)})
    gs = P["pricing"].get("share_of_verified_savings_pct")
    if gs is not None:
        cv["outcome_fee_eur"] = (cv.realisable_value_eur * gs / 100).round(0)
    return cv, pd.DataFrame(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("profile", nargs="?", default="competition")
    ap.add_argument("--params", default=str(ROOT / "configs" / "commercial_assumptions.yaml"))
    ap.add_argument("--data", default=None, help="public data folder (default data/<profile>/public)")
    ap.add_argument("--out", default="my_business_case")
    a = ap.parse_args(argv)
    P = yaml.safe_load(open(a.params))
    miss = check_params(P)
    if miss:
        print("The business case needs YOUR parameters (Europress review: no prices or costs are given).\n"
              f"Missing in {a.params}:\n  - " + "\n  - ".join(miss) +
              "\nCopy configs/commercial_assumptions.yaml, fill it in and pass --params. "
              "configs/business_case_example_params.yaml is a calculation example.")
        return 2
    pub = Path(a.data) if a.data else ROOT / "data" / a.profile / "public"
    cv, sc = scenarios(customer_value(pub), P)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    seg = cv.groupby("segment").agg(customers=("customer_id", "count"), devices=("n_devices", "sum"),
                                    median_spend=("annual_spend_eur", "median"), median_identified=("identified_value_eur", "median"),
                                    median_realisable=("realisable_value_eur", "median")).reset_index()
    cv.round(2).to_csv(out / "business_case_customers.csv", index=False)
    sc.to_csv(out / "business_case_scenarios.csv", index=False)
    md = ["# Business case (team parameters)", "",
          f"Data: `{pub}`. Parameters: `{a.params}` (status: {P.get('status', 'n/a')}).",
          "**Every number is a synthetic-world estimate under the team's own hypothetical parameters; it is not market evidence, "
          "not a Europress price or cost and not a demonstrated saving.** Europress is currently not a party to waste transport or "
          "treatment; tariffs, processing fees and material credits are agreed between the customer and the waste operator.", "",
          "## Identified value by lever (sum over customers, annualised, before realisation)", "",
          pd.DataFrame({"lever": LEVERS, "identified_eur": [round(cv[f"{k}_eur"].sum(), 0) for k in LEVERS],
                        "realisation_share": [P["value_realisation"][k] for k in LEVERS]}).to_markdown(index=False), "",
          "## By fleet segment", "", seg.round(1).to_markdown(index=False), "",
          "## Portfolio scenarios (price x adoption)", "", sc.to_markdown(index=False) if len(sc) else "(no per-device price given)", "",
          "## What remains unproven", "",
          "* Willingness to pay at any price (no customer research was done).",
          "* That unnecessary-lift savings are realisable within hygiene, access and peak constraints (Task C shows some savings are harmful).",
          "* That operators would share weighbridge data, accept renegotiation or that a tender succeeds.",
          "* Future models assume a role Europress does not have today (transport procurement, tonne-based service, marketplace).",
          "* That affordable integrated weighing exists at the assumed accuracy (a challenge assumption, not a finding)."]
    (out / "business_case.md").write_text("\n".join(md))
    print(seg.to_string(), "\n", sc.head(9).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
