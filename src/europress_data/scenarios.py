"""Scenario catalogue (38 families) and per-device episode assignment.

Mechanism types:
  injected  — parameters placed into the simulation before it runs (they cause downstream effects)
  emergent  — arise from the simulation itself (policy × demand × contract); labelled post hoc from truth
  derived   — data-quality or billing artefacts added by observation/invoicing models
"""
from __future__ import annotations

import numpy as np

from .rng import rng_for

SCENARIOS = [
    # id, name, mechanism, tables affected, label entity, description
    ("S01", "Premature collection", "emergent", "collection_events, invoice_lines", "collection",
     "Fixed schedules sized on a mis-estimate, closures not cancelled, extra lifts after ad-hoc pickups -> low true fill at pickup."),
    ("S02", "Excessively delayed collection", "injected", "collection_events, telemetry", "collection",
     "Operator delay episodes (driver shortage) and multi-day delays; container reaches 100 % and side waste accumulates."),
    ("S03", "Low tonnage, expensive transport", "emergent", "collection_events, invoice_lines", "collection",
     "Fixed lift and km fees spread over little mass -> high EUR/t."),
    ("S04", "Unusually expensive route", "injected", "sites, contract_versions", "site",
     "Remote regions (Lappi, Pohjois-Pohjanmaa) with long billable km and remote surcharges; structural, not an anomaly."),
    ("S05", "Material value collapse", "injected", "price_index_monthly", "month",
     "Cardboard index -48 % and paper -30 % for three months."),
    ("S06", "Temporary material price spike", "injected", "price_index_monthly", "month",
     "Plastic film index +55 % for one month, +25 % the next."),
    ("S07", "Contamination reducing recyclable value", "injected", "quality_assessments, invoice_lines", "collection",
     "Site contamination incidents of 2-6 days raise contamination by 8-30 percentage points."),
    ("S08", "Unusually high material generation", "injected", "telemetry, collection_events", "device_period",
     "Campaign/inventory periods multiply generation by 1.6-2.5 for 3-10 days."),
    ("S09", "Seasonal low-volume period", "emergent", "telemetry, collection_events", "device_period",
     "Manufacturing July shutdown, office summer lull, retail January trough."),
    ("S10", "Holiday peaks", "emergent", "telemetry, collection_events", "device_period",
     "Retail December peak, pre-Christmas and post-Christmas returns surges."),
    ("S11", "Site closure", "injected", "site_calendar, collection_events", "site_period",
     "Planned closures of 5-28 days; some customers forget to cancel fixed lifts (empty lifts)."),
    ("S12", "Missing weight observation", "injected", "telemetry", "device_period",
     "Weight sensor fault periods (mass NULL, status FAULT) and devices with no weight measurement."),
    ("S13", "Sensor drift", "injected", "telemetry", "device_period",
     "Gradual gain drift 0.1-0.4 %/day, not reported by the device; fixed only by recalibration/replacement."),
    ("S14", "Sensor replacement", "injected", "sensor_registry, maintenance_work_orders, telemetry", "device_period",
     "New sensor id, new calibration (step change), often preceded by a fault period."),
    ("S15", "Sensor calibration error", "injected", "telemetry, maintenance_work_orders", "device_period",
     "Offset/gain error introduced at a maintenance visit, persisting until next recalibration."),
    ("S16", "Delayed telemetry", "injected", "telemetry", "device_period",
     "Latency bursts (hours) and buffered delivery after connectivity outages."),
    ("S17", "Duplicate sensor events", "derived", "telemetry", "message",
     "Re-sent messages with identical message_id; bursts in some devices."),
    ("S18", "Out-of-order messages", "derived", "telemetry", "message",
     "Buffered flushes and latency jitter deliver older measurements after newer ones."),
    ("S19", "Delayed operator weighbridge records", "derived", "weighbridge_tickets", "ticket",
     "Operator-specific sharing lags (0-45 days), extra-late tickets, some still unpublished at extraction."),
    ("S20", "Compactor vs weighbridge discrepancy", "emergent", "collection_events, weighbridge_tickets", "collection",
     "Causes: sensor drift/calibration, side waste on same truck, combined loads split 50/50, outdated stored tare."),
    ("S21", "Collection cancellation", "injected", "collection_events, invoice_lines", "collection",
     "Customer cancellations (fee if <24 h notice), hybrid skips at low fill."),
    ("S22", "Partial collection", "injected", "collection_events, telemetry", "collection",
     "Container not fully emptied (frozen biowaste in winter, jams); residual mass remains."),
    ("S23", "Contract price changes", "injected", "contract_versions, invoice_lines", "contract_version",
     "Annual indexation on 1 January and mid-period amendments (lift fee, fuel, credit share, processing, minimum)."),
    ("S24", "Incorrect invoice surcharges", "derived", "invoice_lines", "invoice_line",
     "Wrong fuel surcharge rate, doubled km, remote surcharge on non-remote site."),
    ("S25", "Duplicate invoicing", "derived", "invoice_lines", "invoice_line",
     "Lift/transport line billed twice for one job."),
    ("S26", "Unmatched collection and invoice", "derived", "invoice_lines, collection_events", "invoice_line/collection",
     "Phantom job lines without a collection, completed collections never invoiced, job refs with typos."),
    ("S27", "Maintenance downtime", "injected", "maintenance_work_orders, telemetry", "device_period",
     "Breakdowns (4-96 h) and preventive maintenance; material during downtime becomes side waste."),
    ("S28", "Moisture increasing mass", "injected", "telemetry, weighbridge_tickets, quality_assessments", "collection",
     "Rain on outdoor-staged cardboard/paper adds water mass; heavier, denser loads, possible grade downgrade."),
    ("S29", "Change in material density", "injected", "telemetry, maintenance_work_orders", "device_period",
     "Material mix change (lower density) or compaction setting change (higher density, logged as CONFIG_CHANGE)."),
    ("S30", "Multiple fractions at one site", "injected", "devices, telemetry, invoice_lines", "device",
     "Sites with 2-5 streams; recyclables mis-sorted into mixed waste lower its density and waste credit value."),
    ("S31", "Near-threshold ambiguous decisions", "emergent", "decision_cases", "decision_case",
     "Actions whose simulated benefit is within +/- EUR 25 or 3 % of doing nothing."),
    ("S32", "False-positive cost anomalies", "emergent", "collection_events", "collection",
     "High EUR/t explained by hygiene max interval, pre-closure requests, decommissioning, partial lifts, minimum charges."),
    ("S33", "Economic opportunities masked by missing data", "emergent", "telemetry, weighbridge_tickets", "device_period",
     "Over-servicing on devices with no weight sensor and an operator that does not share weighbridge data."),
    ("S34", "Competing operational constraints", "emergent", "decision_cases", "decision_case",
     "Reducing frequency violates biowaste hygiene limits or causes overflow during peaks."),
    ("S35", "Apparent savings disappear after hidden costs", "emergent", "decision_cases", "decision_case",
     "Fewer lifts trigger emergency collections, side-waste fees and minimum charges."),
    ("S36", "No action is correct", "emergent", "decision_cases", "decision_case",
     "Well-tuned devices where every alternative is neutral or harmful."),
    ("S37", "Wasted trip", "injected", "collection_events, invoice_lines", "collection",
     "Blocked access: operator arrives, cannot lift, charges a wasted-trip fee and returns next day."),
    ("S38", "Rejected load", "emergent", "quality_assessments, invoice_lines", "collection",
     "Contamination above grade C threshold: no credit and reprocessing fee at mixed-waste rate."),
    ("S39", "Precautionary on-call order", "injected", "collection_events, invoice_lines", "collection",
     "On-call customers order a lift 'to be safe' before a weekend or holiday although the fill trigger has not fired; published as CUSTOMER_REQUEST."),
    ("S40", "Fill sensor reads falsely high", "injected", "telemetry_hourly, collection_events", "device_period",
     "Material bridging or an object near the fill sensor makes the fill estimate read 88-97 % for 1-4 days while true fill and mass are low; on-call orders follow. The mass reading reveals it. S40 and its frequency are synthetic assumptions and do not describe the performance of the SMART fill measurement."),
]

SCENARIO_IDS = [s[0] for s in SCENARIOS]


def build_weather(tb, regions: list, seed: int) -> dict:
    """Daily rain-intensity proxy (mm) per region, autocorrelated. Illustrative, not meteorological data."""
    p_month = np.array([0.32, 0.28, 0.28, 0.30, 0.35, 0.40, 0.45, 0.50, 0.50, 0.55, 0.55, 0.42])
    out = {}
    for r in regions:
        rng = rng_for(seed, "weather", r)
        wet = np.zeros(tb.n_days, dtype=bool)
        mm = np.zeros(tb.n_days)
        prev = False
        for i in range(tb.n_days):
            p = p_month[tb.month_d[i] - 1]
            p = min(0.9, p + (0.25 if prev else -0.05))
            wet[i] = rng.random() < p
            prev = wet[i]
            if wet[i]:
                mm[i] = float(rng.lognormal(np.log(4.0), 0.9))
        out[r] = mm
    return out


def assign_episodes(spec: dict, tb, seed: int, intensity: float) -> dict:
    """Draw device-level scenario episodes. Returned dict is stored in spec['episodes']."""
    rng = rng_for(seed, "episodes", spec["device_id"])
    n = tb.n_days
    yr = n / 365.0
    a0, a1 = spec["act_from_day"], spec["act_to_day"]
    span = max(1, a1 - a0)
    ep = {"campaigns": [], "contam_incidents": [], "density_shift": None, "drift": None,
          "calib_error": None, "replacement": None, "offline": [], "degraded": [], "latency": [],
          "dup_burst": None, "breakdowns": [], "delay_episode": None, "customer_requests": [],
          "precautionary_days": [], "fill_false_high": []}

    def day_in(lo=0, hi=None):
        hi = a1 - 3 if hi is None else hi
        lo = max(a0 + 1, lo)
        if hi <= lo:
            return lo
        return int(rng.integers(lo, hi))

    p = lambda base: min(0.95, base * intensity)
    if rng.random() < p(0.14 * yr ** 0.5):
        for _ in range(int(rng.integers(1, 3))):
            d0 = day_in()
            ep["campaigns"].append((d0, d0 + int(rng.integers(3, 11)), float(rng.uniform(1.6, 2.5))))
    if spec["credit_eligible"] and rng.random() < p(0.28):
        for _ in range(int(rng.integers(1, 1 + max(1, round(4 * yr))))):
            d0 = day_in()
            ep["contam_incidents"].append((d0, d0 + int(rng.integers(2, 7)), float(rng.uniform(0.08, 0.30))))
    if rng.random() < p(0.08):
        kind = "MIX_CHANGE" if rng.random() < 0.5 else "CONFIG_CHANGE"
        mult = float(rng.uniform(0.74, 0.86)) if kind == "MIX_CHANGE" else float(rng.uniform(1.10, 1.20))
        ep["density_shift"] = (day_in(), kind, mult)
    if spec["has_weight_sensor"]:
        if rng.random() < p(0.10):
            d0 = day_in(hi=a1 - 20)
            fixed = rng.random() < 0.6
            d1 = d0 + int(rng.integers(30, 130)) if fixed else None
            if d1 is not None and d1 >= a1 - 2:
                d1 = None                                   # would end beyond the horizon: stays unresolved
            ep["drift"] = (d0, d1, float(rng.uniform(0.001, 0.004)) * float(rng.choice([-1, 1, 1])))
        if rng.random() < p(0.07):
            d0 = day_in(hi=a1 - 10)
            fixed = rng.random() < 0.5
            d1 = d0 + int(rng.integers(20, 90)) if fixed else None
            if d1 is not None and d1 >= a1 - 2:
                d1 = None
            if rng.random() < 0.6:
                ep["calib_error"] = (d0, d1, "OFFSET", float(rng.choice([-1, 1]) * rng.uniform(120, 450)))
            else:
                ep["calib_error"] = (d0, d1, "GAIN", float(rng.choice([0.86, 0.9, 1.1, 1.15])))
        if rng.random() < p(0.06):
            d0 = day_in(lo=a0 + 15)
            fault_days = int(rng.integers(1, 11)) if rng.random() < 0.6 else 0
            ep["replacement"] = (d0, fault_days, float(rng.normal(0, 0.012)), float(rng.normal(0, 15)))
        if rng.random() < p(0.12):
            for _ in range(int(rng.integers(1, 4))):
                d0 = day_in()
                ep["offline"].append((d0 * 24 + int(rng.integers(0, 24)), float(rng.lognormal(np.log(36), 1.1))))
        if rng.random() < p(0.10):
            d0 = day_in()
            ep["degraded"].append((d0, d0 + int(rng.integers(3, 31))))
    if rng.random() < p(0.08):
        d0 = day_in()
        ep["latency"].append((d0, d0 + int(rng.integers(2, 11))))
    if rng.random() < p(0.05):
        d0 = day_in()
        ep["dup_burst"] = (d0, d0 + int(rng.integers(3, 15)))
    # breakdowns: Poisson ~1.2/year
    for _ in range(int(rng.poisson(1.2 * yr * (span / n)))):
        ep["breakdowns"].append((day_in() * 24 + int(rng.integers(0, 24)), float(np.clip(rng.lognormal(np.log(14), 0.9), 3, 120))))
    if rng.random() < p(0.06):
        d0 = day_in()
        ep["delay_episode"] = (d0, d0 + int(rng.integers(14, 43)))
    if rng.random() < 0.3:
        for _ in range(int(rng.integers(1, 3))):
            ep["customer_requests"].append(day_in())
    # S39 precautionary on-call orders: a habit of some customers (used only while the device is on call)
    if rng.random() < min(0.9, 0.40 * intensity ** 0.5):
        q = float(rng.uniform(0.12, 0.35))
        for d in range(a0 + 1, a1 - 1):
            if tb.weekday_d[d] == 4 or (d + 1 < tb.n_days and tb.holiday_d[d + 1] and tb.weekday_d[d] < 5):
                if rng.random() < q:
                    ep["precautionary_days"].append(d)
    # S40 fill-sensor false high: material bridging / an object near the fill sensor makes the fill estimate read
    # "full" for 1-4 days while the true fill (and mass) is low. On on-call devices this triggers unnecessary lifts.
    n_ff = int(rng.poisson(0.9 * yr * intensity))
    for _ in range(n_ff):
        d0 = day_in()
        ep["fill_false_high"].append((d0, min(a1 - 1, d0 + int(rng.integers(1, 5))), float(rng.uniform(88, 97))))
    return ep
