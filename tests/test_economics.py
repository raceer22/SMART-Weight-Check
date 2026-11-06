from decimal import Decimal

import pytest

from europress_data.economics import CATEGORY, price_event, rhu, summarize
from europress_data.golden import BASE, check_unit_case, unit_cases


def test_rhu_half_away_from_zero():
    assert rhu(5, 10) == 1 and rhu(4, 10) == 0 and rhu(-5, 10) == -1 and rhu(15, 10) == 2 and rhu(-14, 10) == -1


@pytest.mark.parametrize("case", unit_cases(), ids=lambda c: c["case_id"])
def test_golden_unit_cases_match_independent_decimal_reference(case):
    assert check_unit_case(case) == []


def test_at_least_100_golden_cases_overall(small_dataset):
    import json
    pub = json.load(open(small_dataset / "public" / "benchmark" / "golden_cases_public.json"))
    priv = json.load(open(small_dataset / "private_evaluation" / "benchmark" / "golden_cases_private.json"))
    assert pub["n_cases"] + priv["n_cases"] >= 100
    ids = [c["case_id"] for c in pub["cases"] + priv["cases"]]
    assert len(ids) == len(set(ids))


def test_unknown_mass_never_fabricated():
    r = price_event(BASE, "COMPLETED", None)
    s = summarize(r["lines"], None)
    assert r["mass_known"] is False
    assert s["collection_cost_eur_per_t"] is None and s["total_cost_eur_per_t"] is None
    assert not any(l["unit"] == "t" for l in r["lines"])


def test_zero_mass_no_division():
    s = summarize(price_event(BASE, "COMPLETED", 0)["lines"], 0)
    assert s["collection_cost_eur_per_t"] is None


def test_no_double_counting_and_identities():
    v = dict(BASE, min_charge_cents=40000, credit_share_bp=8000)
    r = price_event(v, "COMPLETED", 2875, "C", 10500, emergency=True, side_waste=True, credit_eligible=True)
    s = summarize(r["lines"], 2875)
    assert all(l["line_type"] in CATEGORY for l in r["lines"])
    assert len({l["line_type"] for l in r["lines"]}) == len(r["lines"])            # each line once
    assert s["invoice_amount_cents"] == s["total_customer_cost_cents"]
    assert s["net_material_contribution_cents"] == s["material_credit_cents"] - s["collection_cost_cents"] - s["processing_cost_cents"] - s["penalties_cents"]


def test_rejected_load_gets_no_credit_and_reprocessing_fee():
    r = price_event(BASE, "COMPLETED", 3000, "R", 9000, credit_eligible=True)
    types = {l["line_type"] for l in r["lines"]}
    assert "MATERIAL_CREDIT" not in types and "REJECTION_REPROCESSING" in types and "PROCESSING" not in types


def test_cancellation_fee_only_with_short_notice():
    assert price_event(BASE, "CANCELLED_BY_CUSTOMER", None, notice_hours=23.99)["lines"]
    assert not price_event(BASE, "CANCELLED_BY_CUSTOMER", None, notice_hours=24.0)["lines"]


def test_minimum_charge_topup_exact():
    v = dict(BASE, pricing_model="PER_TONNE", lift_fee_cents=0, haul_fee_cents_per_t=6740, min_charge_cents=21000, fuel_surcharge_bp=0,
             processing_fee_cents_per_t=0, free_km=34)
    lines = price_event(v, "COMPLETED", 400)["lines"]
    assert sum(l["amount_cents"] for l in lines) == 21000          # 0.4 t x 67.40 = 26.96 -> topped up to 210.00


def test_hand_worked_example():
    # docs/ECONOMIC_MODEL.md worked example 1
    v = dict(BASE, pricing_model="FIXED_PER_LIFT", lift_fee_cents=31275, processing_fee_cents_per_t=0)
    s = summarize(price_event(v, "COMPLETED", 2340)["lines"], 2340)
    assert s["collection_cost_cents"] == 37322 and s["collection_cost_eur_per_t"] == 159.50
