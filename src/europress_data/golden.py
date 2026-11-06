"""Golden test cases (>= 100): financial unit cases, dataset-anchored financial cases,
data-quality/operational cases and decision cases. Public and private sets are written separately.

python -m europress_data.golden --profile competition
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import duckdb

from .config import ROOT
from .economics import price_event, summarize
from .reference_decimal import expected_lines, summary

BASE = dict(contract_version_id="GOLDEN-V1", pricing_model="HYBRID", lift_fee_cents=9850, per_km_cents=185, free_km=10, contract_km=34,
            remote_surcharge_cents=0, fuel_surcharge_bp=450, haul_fee_cents_per_t=0, processing_fee_cents_per_t=11825, min_charge_cents=0,
            credit_share_bp=7500, credit_floor_cents_per_t=0, contamination_penalty_cents=6500, rejection_fee_cents_per_t=14500,
            cancellation_fee_cents=4500, wasted_trip_fee_cents=8900, side_waste_fee_cents=7500, emergency_surcharge_cents=11000,
            rental_cents_per_month=0, default_weight_kg=2000, target_collection_cost_cents_per_t=6000)

VARIANTS = {
    "hybrid_mixed_waste": dict(),
    "fixed_per_lift_all_inclusive": dict(pricing_model="FIXED_PER_LIFT", lift_fee_cents=31275, processing_fee_cents_per_t=0),
    "per_tonne_with_minimum": dict(pricing_model="PER_TONNE", lift_fee_cents=0, haul_fee_cents_per_t=6740, min_charge_cents=21000),
    "hybrid_min_binding": dict(pricing_model="HYBRID_MIN", min_charge_cents=26000),
    "remote_region": dict(remote_surcharge_cents=3500, contract_km=170, free_km=30),
    "free_km_exceeds_route": dict(free_km=40),
    "odd_fuel_rounding": dict(fuel_surcharge_bp=333, lift_fee_cents=9851),
    "no_fuel": dict(fuel_surcharge_bp=0),
    "recyclable_rebate": dict(processing_fee_cents_per_t=0),
    "recyclable_no_rebate": dict(processing_fee_cents_per_t=0, credit_share_bp=0),
    "recyclable_with_floor": dict(processing_fee_cents_per_t=0, credit_floor_cents_per_t=2500),
}
SCEN = [  # (status, kg, grade, index_eur_per_t, emergency, side, notice, recyclable)
    ("COMPLETED", 2340, None, None, False, False, None, False),
    ("COMPLETED", 0, None, None, False, False, None, False),
    ("COMPLETED", None, None, None, False, False, None, False),
    ("COMPLETED", 125, None, None, False, False, None, False),
    ("PARTIAL", 1780, None, None, True, True, None, False),
    ("CANCELLED_BY_CUSTOMER", None, None, None, False, False, 23.9, False),
    ("CANCELLED_BY_CUSTOMER", None, None, None, False, False, 24.0, False),
    ("WASTED_TRIP", None, None, None, False, False, None, False),
    ("SKIPPED_LOW_FILL", None, None, None, False, False, 26.0, False),
    ("COMPLETED", 3115, "A", 96.40, False, False, None, True),
    ("COMPLETED", 3115, "B", 96.40, False, False, None, True),
    ("COMPLETED", 3115, "C", 96.40, False, False, None, True),
    ("COMPLETED", 3115, "R", 96.40, False, False, None, True),
    ("COMPLETED", 1505, "A", -12.30, False, False, None, True),
    ("COMPLETED", 1, "A", 96.41, False, False, None, True),
]


def _ver(**kw):
    v = dict(BASE)
    v.update(kw)
    return v


def unit_cases() -> list:
    cases = []
    for (vn, vk), sc in itertools.product(VARIANTS.items(), SCEN):
        st, kg, g, ix, em, side, notice, rec = sc
        if rec != vn.startswith("recyclable"):
            if not (vn == "hybrid_mixed_waste" and not rec):
                continue
        v = _ver(**vk)
        lines = expected_lines(v, st, kg, g, ix, em, side, notice, rec)
        exp = summary(lines, kg)
        cases.append({"case_id": f"G-FIN-U{len(cases) + 1:03d}", "category": "financial_unit", "variant": vn,
                      "inputs": {"version": v, "status": st, "billing_mass_kg": kg, "grade": g, "index_eur_per_t": ix,
                                 "emergency": em, "side_waste": side, "notice_hours": notice, "credit_eligible": rec},
                      "expected": {"lines": [[t, str(a)] for t, a in lines], **exp},
                      "computed_by": "reference_decimal (independent Decimal implementation)"})
    return cases


def check_unit_case(c: dict) -> list:
    """Return mismatches between the integer-cent engine and the golden expectation."""
    i = c["inputs"]
    ix = None if i["index_eur_per_t"] is None else int(round(i["index_eur_per_t"] * 100))
    r = price_event(i["version"], i["status"], i["billing_mass_kg"], i["grade"], ix, i["emergency"], i["side_waste"],
                    i["notice_hours"], i["credit_eligible"])
    s = summarize(r["lines"], i["billing_mass_kg"])
    bad = []
    got_lines = [[l["line_type"], f"{l['amount_cents'] / 100:.2f}"] for l in r["lines"]]
    exp_lines = [[t, f"{float(a):.2f}"] for t, a in c["expected"]["lines"]]
    if got_lines != exp_lines:
        bad.append(("lines", got_lines, exp_lines))
    for k in ("collection_cost_eur", "processing_cost_eur", "penalties_eur", "material_credit_eur", "net_material_contribution_eur"):
        if abs(s[k.replace("_eur", "_cents")] / 100 - float(c["expected"][k])) > 1e-9:
            bad.append((k, s[k.replace("_eur", "_cents")] / 100, c["expected"][k]))
    e = c["expected"]["collection_cost_eur_per_t"]
    if (e is None) != (s["collection_cost_eur_per_t"] is None) or (e is not None and abs(float(e) - s["collection_cost_eur_per_t"]) > 1e-9):
        bad.append(("per_t", s["collection_cost_eur_per_t"], e))
    return bad


def dataset_cases(d: Path) -> tuple[list, list]:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    pub, priv = d / "public", d / "private_evaluation"
    out_pub, out_priv = [], []

    def fin(src, n, tag, sink):
        rows = con.execute(f"""SELECT e.*, d.material_stream FROM '{src}' e JOIN '{pub / 'reference' / 'devices.parquet'}' d USING (device_id)
            WHERE e.status IN ('COMPLETED','PARTIAL') ORDER BY hash(e.collection_id) LIMIT {n}""").fetchdf()
        for r in rows.to_dict("records"):
            sink.append({"case_id": f"G-FIN-{tag}-{len(sink) + 1:03d}", "category": "financial_dataset", "collection_id": r["collection_id"],
                         "inputs": {"contract_version_id": r["contract_version_id"], "billing_mass_kg": r["billing_mass_kg"],
                                    "billing_mass_basis": r["billing_mass_basis"], "grade": r["grade_applied"], "index_eur_per_t": r["index_price_eur_per_t"]},
                         "expected": {k: r[k] for k in ("collection_cost_eur", "processing_cost_eur", "penalties_eur", "material_credit_eur",
                                                        "net_material_contribution_eur", "collection_cost_eur_per_t")}})
    fin(pub / "labels_dev" / "reference_economics.parquet", 30, "D", out_pub)
    fin(priv / "labels_test" / "reference_economics.parquet", 30, "T", out_priv)
    te = f"read_parquet('{pub}/telemetry/telemetry_hourly/*/*.parquet', hive_partitioning=false)"
    ce = pub / "operations" / "collection_events.parquet"
    wb = pub / "operations" / "weighbridge_tickets.parquet"

    def dq(desc, sql, expect_fn, n=3, private=False):
        for row in con.execute(sql + f" LIMIT {n}").fetchdf().to_dict("records"):
            (out_priv if private else out_pub).append({"case_id": f"G-DQ-{len(out_pub) + len(out_priv) + 1:03d}", "category": "data_quality",
                                                       "description": desc, "inputs": {k: str(v) for k, v in row.items()}, "expected": expect_fn(row)})
    dq("Duplicated telemetry delivery: same message_id twice with identical payload; count once after dedup",
       f"SELECT message_id, count(*) n FROM {te} GROUP BY 1 HAVING n > 1 ORDER BY message_id", lambda r: {"deliveries": int(r["n"]), "unique_measurements": 1})
    dq("Buffered delivery arrives after a newer message (out-of-order); order by measured_at, not received_at",
       f"SELECT message_id, device_id, measured_at, received_at FROM {te} WHERE delivery_mode='BUFFERED' ORDER BY message_id",
       lambda r: {"delivery_mode": "BUFFERED", "received_after_measured": True})
    dq("Weight sensor fault: mass_kg is NULL and must not be imputed",
       f"SELECT message_id, quality_flag FROM {te} WHERE quality_flag='SENSOR_FAULT' ORDER BY message_id", lambda r: {"mass_kg": None})
    dq("Device without weight measurement: all mass_kg NULL; use weighbridge or invoice tonnage instead",
       f"SELECT device_id FROM '{pub / 'reference' / 'devices.parquet'}' WHERE NOT has_weight_measurement ORDER BY device_id",
       lambda r: {"telemetry_mass_non_null_rows": 0})
    dq("Lift with missing after-reading: device estimate is NULL (never filled)",
       f"SELECT collection_id FROM '{ce}' WHERE status='COMPLETED' AND device_mass_kg_before IS NOT NULL AND device_mass_kg_after IS NULL ORDER BY collection_id",
       lambda r: {"device_estimated_collected_kg": None})
    dq("Operator does not share weighbridge data: no public ticket for the job",
       f"SELECT collection_id, operator_job_ref FROM '{ce}' WHERE operator_id='OP-D' AND status='COMPLETED' ORDER BY collection_id",
       lambda r: {"public_weighbridge_ticket": None, "weight_reconciliation_status": "WEIGHBRIDGE_NOT_AVAILABLE"})
    dq("Combined load: allocated nets of one weighing event sum to the event net",
       f"SELECT weighing_event_id, any_value(net_kg) net, sum(allocated_net_kg) s FROM '{wb}' WHERE loads_on_vehicle > 1 GROUP BY 1 HAVING count(*) = 2 ORDER BY 1",
       lambda r: {"sum_allocated_equals_net": True, "net_kg": int(r["net"])})
    dq("Skipped hybrid lift: no charge expected",
       f"SELECT collection_id FROM '{ce}' WHERE status='SKIPPED_LOW_FILL' ORDER BY collection_id", lambda r: {"expected_invoice_amount_eur": 0.0})
    dq("Contract amendment: an event on the effective date uses the new version",
       f"SELECT contract_version_id, contract_id, effective_from FROM '{pub / 'reference' / 'contract_versions.parquet'}' WHERE change_reason LIKE 'AMENDMENT%' ORDER BY 1",
       lambda r: {"version_applies_from_local_date": str(r["effective_from"])[:10]})
    lab = priv / "truth" / "invoice_line_labels.parquet"
    for fam in ("DUPLICATE_LINE", "OUTDATED_TARIFF", "WRONG_SURCHARGE:FUEL_RATE", "UNMATCHED_LINE", "WEIGHT_BASIS_MISMATCH"):
        dq(f"Invoice discrepancy {fam}", f"SELECT invoice_line_id, delta_cents FROM '{lab}' WHERE discrepancy_type='{fam}' AND invoice_line_id IS NOT NULL ORDER BY 1",
           lambda r, fam=fam: {"discrepancy_type": fam, "delta_eur": int(r["delta_cents"]) / 100}, n=2, private=True)
    dq("Uninvoiced completed collection", f"SELECT collection_id, delta_cents FROM '{lab}' WHERE discrepancy_type='UNINVOICED_COLLECTION' ORDER BY 1",
       lambda r: {"discrepancy_type": "UNINVOICED_COLLECTION", "delta_eur": int(r["delta_cents"]) / 100}, n=2, private=True)
    for src, sink, tag in ((pub / "labels_dev" / "decision_truth.parquet", out_pub, "D"), (priv / "labels_test" / "decision_truth.parquet", out_priv, "T")):
        if not src.exists():
            continue
        for q in ("best_action = 'NO_ACTION'", "best_action <> 'NO_ACTION' AND NOT near_threshold", "constraint_conflict", "hidden_cost_trap_present"):
            for r in con.execute(f"SELECT * FROM '{src}' WHERE {q} ORDER BY hash(case_id) LIMIT 3").fetchdf().to_dict("records"):
                sink.append({"case_id": f"G-DEC-{tag}-{len(sink) + 1:03d}", "category": "decision", "decision_case_id": r["case_id"],
                             "condition": q, "expected": {"best_action": r["best_action"], "acceptable_actions": r["acceptable_actions"].split(","),
                                                          "best_benefit_eur": r["best_benefit_cents"] / 100}})
    con.close()
    return out_pub, out_priv


def write(profile: str, d: Path | None = None) -> dict:
    d = Path(d) if d else ROOT / "data" / profile
    units = unit_cases()
    pub_d, priv_d = dataset_cases(d)
    pub = units[: int(len(units) * 0.6)] + pub_d
    priv = units[int(len(units) * 0.6):] + priv_d
    (d / "public" / "benchmark").mkdir(parents=True, exist_ok=True)
    (d / "private_evaluation" / "benchmark").mkdir(parents=True, exist_ok=True)
    json.dump({"profile": profile, "n_cases": len(pub), "cases": pub}, open(d / "public" / "benchmark" / "golden_cases_public.json", "w"), indent=1, default=str)
    json.dump({"profile": profile, "n_cases": len(priv), "cases": priv}, open(d / "private_evaluation" / "benchmark" / "golden_cases_private.json", "w"), indent=1, default=str)
    return {"public": len(pub), "private": len(priv), "unit_financial": len(units)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="quickstart")
    print(write(ap.parse_args(argv).profile))


if __name__ == "__main__":
    main()
