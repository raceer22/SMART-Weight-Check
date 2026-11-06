"""Independent reference implementation of the tariff rules using decimal.Decimal.

Written separately from economics.py (which uses integer-cent arithmetic) directly from
docs/ECONOMIC_MODEL.md, so the two implementations can cross-check each other in tests and
golden cases. Inputs use EUR (Decimal) and percentages; outputs are EUR rounded half-up to cents.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal as D

CENT = D("0.01")
QUALITY = {"A": D("1"), "B": D("0.85"), "C": D("0.60"), "R": D("0")}


def r2(x: D) -> D:
    """Round half away from zero to cents."""
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def eur(cents) -> D:
    return D(int(cents)) / 100


def expected_lines(v: dict, status: str, kg, grade=None, index_eur_per_t=None, emergency=False, side_waste=False,
                   notice_hours=None, credit_eligible=False) -> list:
    out = []
    if status in ("COMPLETED", "PARTIAL"):
        lift = eur(v["lift_fee_cents"])
        km = max(0, int(v["contract_km"]) - int(v["free_km"]))
        transport = km * eur(v["per_km_cents"])
        remote = eur(v["remote_surcharge_cents"])
        if lift:
            out.append(("LIFT_FEE", lift))
        if transport:
            out.append(("TRANSPORT", r2(transport)))
        if remote:
            out.append(("REMOTE_SURCHARGE", remote))
        base = lift + transport + remote
        fuel = r2(base * D(int(v["fuel_surcharge_bp"])) / D(10000))
        if fuel:
            out.append(("FUEL_SURCHARGE", fuel))
        haul = proc = rej = D(0)
        rejected = credit_eligible and grade == "R"
        if kg is not None:
            t = D(int(kg)) / D(1000)
            haul = r2(t * eur(v["haul_fee_cents_per_t"]))
            if haul:
                out.append(("HAUL_PER_TONNE", haul))
            if rejected:
                rej = r2(t * eur(v["rejection_fee_cents_per_t"]))
                if rej:
                    out.append(("REJECTION_REPROCESSING", rej))
            else:
                proc = r2(t * eur(v["processing_fee_cents_per_t"]))
                if proc:
                    out.append(("PROCESSING", proc))
            mn = eur(v["min_charge_cents"])
            if mn:
                sub = base + fuel + haul + proc + rej
                if sub < mn:
                    out.append(("MIN_CHARGE_TOPUP", mn - sub))
            if credit_eligible and not rejected and int(v["credit_share_bp"]) > 0 and index_eur_per_t is not None:
                share = r2(D(str(index_eur_per_t)) * D(int(v["credit_share_bp"])) / D(10000))
                price = max(eur(v["credit_floor_cents_per_t"]), share)
                price = r2(price * QUALITY.get(grade or "A"))
                if price:
                    out.append(("MATERIAL_CREDIT", -r2(t * price)))
        if credit_eligible and grade == "C" and int(v["contamination_penalty_cents"]):
            out.append(("CONTAMINATION_PENALTY", eur(v["contamination_penalty_cents"])))
        if side_waste and int(v["side_waste_fee_cents"]):
            out.append(("SIDE_WASTE_FEE", eur(v["side_waste_fee_cents"])))
        if emergency and int(v["emergency_surcharge_cents"]):
            out.append(("EMERGENCY_SURCHARGE", eur(v["emergency_surcharge_cents"])))
    elif status == "CANCELLED_BY_CUSTOMER":
        if notice_hours is not None and notice_hours < 24 and int(v["cancellation_fee_cents"]):
            out.append(("CANCELLATION_FEE", eur(v["cancellation_fee_cents"])))
    elif status == "WASTED_TRIP":
        out.append(("WASTED_TRIP_FEE", eur(v["wasted_trip_fee_cents"])))
    return out


def summary(lines: list, kg) -> dict:
    coll = sum((a for t, a in lines if t in ("LIFT_FEE", "TRANSPORT", "REMOTE_SURCHARGE", "FUEL_SURCHARGE", "HAUL_PER_TONNE",
                                             "MIN_CHARGE_TOPUP", "SIDE_WASTE_FEE", "EMERGENCY_SURCHARGE")), D(0))
    proc = sum((a for t, a in lines if t in ("PROCESSING", "REJECTION_REPROCESSING")), D(0))
    pen = sum((a for t, a in lines if t in ("CONTAMINATION_PENALTY", "CANCELLATION_FEE", "WASTED_TRIP_FEE")), D(0))
    cred = -sum((a for t, a in lines if t == "MATERIAL_CREDIT"), D(0))
    net = cred - coll - proc - pen
    out = {"collection_cost_eur": str(coll), "processing_cost_eur": str(proc), "penalties_eur": str(pen),
           "material_credit_eur": str(cred), "net_material_contribution_eur": str(net), "total_customer_cost_eur": str(-net)}
    if kg is not None and int(kg) > 0:
        t = D(int(kg)) / D(1000)
        out["collection_cost_eur_per_t"] = str(r2(coll / t))
    else:
        out["collection_cost_eur_per_t"] = None
    return out
