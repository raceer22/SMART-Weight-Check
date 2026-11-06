"""Reference financial model (integer-cent arithmetic, deterministic rounding).

Conventions
-----------
* All money is EUR excluding VAT, stored internally as integer cents.
* Line amounts are signed from the customer's perspective: charges > 0, credits < 0.
* Rounding: every line is rounded once to the cent, half away from zero ("half-up" for positives).
  Totals are sums of rounded lines (never re-rounded).
* Mass: integer kg. Tonnes shown as kg/1000 with 3 decimals; never imputed. If the billing mass is
  unknown, mass-based lines are not computed and the result carries ``mass_known = False``.
* Categories (no double counting — each line belongs to exactly one category):
    collection_cost = LIFT_FEE + TRANSPORT + REMOTE_SURCHARGE + FUEL_SURCHARGE + HAUL_PER_TONNE
                      + MIN_CHARGE_TOPUP + SIDE_WASTE_FEE + EMERGENCY_SURCHARGE
    processing_cost = PROCESSING + REJECTION_REPROCESSING
    penalties       = CONTAMINATION_PENALTY + CANCELLATION_FEE + WASTED_TRIP_FEE
    material_credit = -(MATERIAL_CREDIT)            (reported as a positive number)
    net_material_contribution = material_credit - collection_cost - processing_cost - penalties
    total_customer_cost       = collection_cost + processing_cost + penalties - material_credit
  RENTAL is a monthly contract line and is NOT allocated to collections.
"""
from __future__ import annotations

from typing import Optional

CATEGORY = {
    "LIFT_FEE": "collection_cost", "TRANSPORT": "collection_cost", "REMOTE_SURCHARGE": "collection_cost",
    "FUEL_SURCHARGE": "collection_cost", "HAUL_PER_TONNE": "collection_cost", "MIN_CHARGE_TOPUP": "collection_cost",
    "SIDE_WASTE_FEE": "collection_cost", "EMERGENCY_SURCHARGE": "collection_cost",
    "PROCESSING": "processing_cost", "REJECTION_REPROCESSING": "processing_cost",
    "CONTAMINATION_PENALTY": "penalties", "CANCELLATION_FEE": "penalties", "WASTED_TRIP_FEE": "penalties",
    "MATERIAL_CREDIT": "material_credit", "RENTAL": "monthly_fixed",
}
COMPLETED_STATUSES = ("COMPLETED", "PARTIAL")
GRADE_QUALITY_BP = {"A": 10000, "B": 8500, "C": 6000, "R": 0}


def rhu(num: int, den: int) -> int:
    """Round num/den to the nearest integer, halves away from zero. Exact integer arithmetic."""
    if den <= 0:
        raise ValueError("den must be positive")
    sign = -1 if num < 0 else 1
    q, r = divmod(abs(num), den)
    if 2 * r >= den:
        q += 1
    return sign * q


def credit_price_cents_per_t(version: dict, index_cents_per_t: Optional[int], grade: Optional[str]) -> int:
    """Effective credit price: max(floor, round(index * share)) then * quality factor."""
    share = int(version.get("credit_share_bp") or 0)
    if share <= 0 or index_cents_per_t is None:
        return 0
    base = max(int(version.get("credit_floor_cents_per_t") or 0), rhu(int(index_cents_per_t) * share, 10000))
    q = GRADE_QUALITY_BP.get(grade or "A", 10000)
    return rhu(base * q, 10000)


def price_event(version: dict, status: str, kg: Optional[int], grade: Optional[str] = None,
                index_cents_per_t: Optional[int] = None, emergency: bool = False,
                side_waste: bool = False, notice_hours: Optional[float] = None,
                credit_eligible: bool = False) -> dict:
    """Return the expected (correct) invoice lines for one collection event.

    version: a contract_versions row (dict) with integer-cent tariff fields.
    status: COMPLETED, PARTIAL, CANCELLED_BY_CUSTOMER, SKIPPED_LOW_FILL, WASTED_TRIP, MISSED_BY_OPERATOR
    kg: billing mass (operator weighbridge net or contractual default); None if unknown.
    """
    lines = []

    def add(t, qty, unit, unit_price, amount):
        lines.append({"line_type": t, "quantity": qty, "unit": unit, "unit_price_cents": unit_price,
                      "amount_cents": amount})

    mass_known = kg is not None
    if status in COMPLETED_STATUSES:
        lift = int(version["lift_fee_cents"])
        km = max(0, int(version["contract_km"]) - int(version["free_km"]))
        transport = km * int(version["per_km_cents"])
        remote = int(version["remote_surcharge_cents"])
        if lift:
            add("LIFT_FEE", 1, "lift", lift, lift)
        if transport:
            add("TRANSPORT", km, "km", int(version["per_km_cents"]), transport)
        if remote:
            add("REMOTE_SURCHARGE", 1, "lift", remote, remote)
        fuel_base = lift + transport + remote
        fuel = rhu(fuel_base * int(version["fuel_surcharge_bp"]), 10000)
        if fuel:
            add("FUEL_SURCHARGE", int(version["fuel_surcharge_bp"]) / 100, "pct_of_base", fuel_base, fuel)
        haul = proc = rej = None
        rejected = credit_eligible and grade == "R"
        if mass_known:
            t = kg / 1000
            haul = rhu(kg * int(version["haul_fee_cents_per_t"]), 1000)
            if haul:
                add("HAUL_PER_TONNE", t, "t", int(version["haul_fee_cents_per_t"]), haul)
            if rejected:
                rej = rhu(kg * int(version["rejection_fee_cents_per_t"]), 1000)
                if rej:
                    add("REJECTION_REPROCESSING", t, "t", int(version["rejection_fee_cents_per_t"]), rej)
            else:
                proc = rhu(kg * int(version["processing_fee_cents_per_t"]), 1000)
                if proc:
                    add("PROCESSING", t, "t", int(version["processing_fee_cents_per_t"]), proc)
            mn = int(version["min_charge_cents"])
            if mn:
                sub = fuel_base + fuel + (haul or 0) + (proc or 0) + (rej or 0)
                if sub < mn:
                    add("MIN_CHARGE_TOPUP", 1, "lift", mn - sub, mn - sub)
            if credit_eligible and not rejected:
                cp = credit_price_cents_per_t(version, index_cents_per_t, grade)
                if cp:
                    add("MATERIAL_CREDIT", t, "t", -cp, -rhu(kg * cp, 1000))
        if credit_eligible and grade == "C" and int(version["contamination_penalty_cents"]):
            p = int(version["contamination_penalty_cents"])
            add("CONTAMINATION_PENALTY", 1, "lift", p, p)
        if side_waste and int(version["side_waste_fee_cents"]):
            p = int(version["side_waste_fee_cents"])
            add("SIDE_WASTE_FEE", 1, "lift", p, p)
        if emergency and int(version["emergency_surcharge_cents"]):
            p = int(version["emergency_surcharge_cents"])
            add("EMERGENCY_SURCHARGE", 1, "lift", p, p)
    elif status == "CANCELLED_BY_CUSTOMER":
        if notice_hours is not None and notice_hours < 24 and int(version["cancellation_fee_cents"]):
            p = int(version["cancellation_fee_cents"])
            add("CANCELLATION_FEE", 1, "event", p, p)
    elif status == "WASTED_TRIP":
        p = int(version["wasted_trip_fee_cents"])
        add("WASTED_TRIP_FEE", 1, "event", p, p)
    return {"lines": lines, "mass_known": mass_known}


def summarize(lines: list, kg: Optional[int]) -> dict:
    cat = {"collection_cost": 0, "processing_cost": 0, "penalties": 0, "material_credit": 0}
    for ln in lines:
        c = CATEGORY[ln["line_type"]]
        if c == "material_credit":
            cat[c] += -ln["amount_cents"]
        elif c in cat:
            cat[c] += ln["amount_cents"]
    net = cat["material_credit"] - cat["collection_cost"] - cat["processing_cost"] - cat["penalties"]
    out = {f"{k}_cents": v for k, v in cat.items()}
    out["net_material_contribution_cents"] = net
    out["total_customer_cost_cents"] = -net
    out["invoice_amount_cents"] = sum(ln["amount_cents"] for ln in lines)
    if kg is not None and kg > 0:
        # exact: cents per tonne rounded half away from zero, then to EUR
        out["collection_cost_eur_per_t"] = rhu(cat["collection_cost"] * 1000, int(kg)) / 100
        out["total_cost_eur_per_t"] = rhu(-net * 1000, int(kg)) / 100
    else:
        out["collection_cost_eur_per_t"] = None   # never divide by zero / unknown mass
        out["total_cost_eur_per_t"] = None
    return out


def grade_from_contamination(c: float, grades: dict) -> str:
    for g in ("A", "B", "C"):
        if c <= grades[g]["max_contamination"]:
            return g
    return "R"
