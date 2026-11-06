"""Ground-truth labels derived from simulator truth (never from the public tables alone)."""
from __future__ import annotations

from .economics import price_event, summarize
from .simulate import FREQ_OPTIONS

SCEN_OF = {
    "PREMATURE_UNJUSTIFIED": "S01", "EARLY_JUSTIFIED": "S32", "COST_PER_T_HIGH": "S03", "DELAYED_COLLECTION": "S02",
    "CONTAMINATION_VALUE_LOSS": "S07", "REJECTED_LOAD": "S38", "WEIGHT_DISCREPANCY": "S20",
    "OUTDATED_TARIFF": "S23", "DUPLICATE_LINE": "S25", "WRONG_SURCHARGE": "S24", "MISSING_LINE": "S26",
    "WEIGHT_BASIS_MISMATCH": "S26", "UNMATCHED_LINE": "S26", "UNINVOICED_COLLECTION": "S26",
    "SENSOR_DRIFT": "S13", "CALIBRATION_ERROR": "S15", "SENSOR_FAULT": "S12", "SENSOR_REPLACEMENT": "S14",
    "SENSOR_DEGRADED": "S12", "DENSITY_SHIFT": "S29", "HIGH_GENERATION": "S08", "CONTAMINATION_INCIDENT": "S07",
    "OPERATOR_DELAY_EPISODE": "S02", "TELEMETRY_LATENCY": "S16", "DUPLICATE_BURST": "S17", "BREAKDOWN": "S27",
    "OVER_SERVICING": "S01", "RECYCLABLES_IN_MIXED": "S30", "NO_CREDIT_SHARE": "S35", "MASKED_OPPORTUNITY": "S33",
    "MOISTURE_HEAVY_LOAD": "S28", "FILL_SENSOR_FALSE_HIGH": "S40",
}


def _lab(entity_type, entity_id, device_id, family, severity, actionable, explanation, value_eur, t_ms, end_ms=None, extra=None):
    d = {"entity_type": entity_type, "entity_id": entity_id, "device_id": device_id, "label_family": family,
         "severity": severity, "is_actionable": bool(actionable), "explanation_code": explanation,
         "value_at_stake_eur": None if value_eur is None else round(float(value_eur), 2),
         "event_ms": int(t_ms), "end_ms": None if end_ms is None else int(end_ms), "scenario_id": SCEN_OF.get(family.split(":")[0])}
    if extra:
        d.update(extra)
    return d


def collection_labels(ev: dict, spec: dict, charge: dict, ticket: dict | None, dev_obs: dict, sens_active: list) -> list:
    out = []
    cid = ev["collection_id"]
    dev = spec["device_id"]
    t = ev["actual_ms"]
    fill = ev["true_fill_before_pct"]
    pol = spec["policy"]
    v = charge["version"]
    bench = v["target_collection_cost_cents_per_t"] / 100
    min_f = 7.0 / spec["max_days"]
    at_min_freq = pol["type"] in ("FIXED_SCHEDULE", "HYBRID") and not any(
        f >= min_f - 1e-9 and f < pol["freq_per_week"] for f in FREQ_OPTIONS)
    reason = None
    trig = ev["trigger"] if ev["trigger"] != "RESCHEDULED" else ev.get("orig_trigger", "SCHEDULED")
    if trig in ("MAX_INTERVAL_RULE", "DECOMMISSION", "CUSTOMER_REQUEST_PRE_CLOSURE", "CUSTOMER_REQUEST"):
        reason = trig
    elif at_min_freq:
        reason = "MIN_FREQUENCY_REQUIRED"
    elif trig == "AD_HOC_CUSTOMER":
        reason = "AD_HOC_AFTER_OVERFLOW"
    cpt = charge["collection_cost_eur_per_t"]
    if fill < 40:
        sev = "clear" if fill < 25 else "borderline"
        if reason:
            out.append(_lab("collection", cid, dev, "EARLY_JUSTIFIED", sev, False, reason, None, t))
        else:
            # value at stake: logistics cost that a fuller container would have avoided (illustrative)
            val = None
            if cpt is not None:
                val = charge["collection_cost_cents"] / 100 * (1 - fill / 85.0)
            od = ev.get("order_day")
            in_ff = trig == "ON_CALL_ORDER" and od is not None and any(
                d0 <= od < d1 for (d0, d1, _) in spec["episodes"].get("fill_false_high", []))
            expl_code = ("PRECAUTIONARY_ORDER" if trig == "CUSTOMER_PRECAUTIONARY" else
                         "FILL_SENSOR_FALSE_HIGH" if in_ff else "OVER_SERVICING")
            lab_ = _lab("collection", cid, dev, "PREMATURE_UNJUSTIFIED", sev, True, expl_code, val, t)
            if trig == "CUSTOMER_PRECAUTIONARY":
                lab_["scenario_id"] = "S39"
            elif in_ff:
                lab_["scenario_id"] = "S40"
            out.append(lab_)
    if cpt is not None and bench > 0 and cpt > 2.0 * bench:
        lines = {l["line_type"] for l in charge["lines"]}
        if fill < 40 and not reason:
            expl, act = "PREMATURE_UNJUSTIFIED", True
        elif reason:
            expl, act = reason, False
        elif ev["status"] == "PARTIAL":
            expl, act = "PARTIAL_COLLECTION", False
        elif "MIN_CHARGE_TOPUP" in lines:
            expl, act = "CONTRACT_MINIMUM_CHARGE", False
        elif "EMERGENCY_SURCHARGE" in lines:
            expl, act = "EMERGENCY_AFTER_OVERFLOW", True
        elif ev["true_side_waste_collected_kg"] > 0:
            expl, act = "SIDE_WASTE_HANDLING", True
        else:
            expl, act = "LOW_DENSITY_OR_SMALL_LOAD", False
        sev = "clear" if cpt > 3.0 * bench else "borderline"
        out.append(_lab("collection", cid, dev, "COST_PER_T_HIGH", sev, act, expl,
                        (cpt - bench) * (charge["billing_mass_kg"] or 0) / 1000, t,
                        extra={"benchmark_eur_per_t": bench, "reference_eur_per_t": cpt}))
    fh = ev["cycle_full_hours"]
    if fh >= 12 or (ev.get("delay_h") or 0) > 24:
        cause = "OPERATOR_DELAY" if (ev.get("delay_h") or 0) > 24 else (
            "POLICY_OR_CAPACITY" if pol["type"] != "ON_CALL" else "THRESHOLD_TOO_HIGH_OR_LEAD_TIME")
        sev = "clear" if (fh > 48 or (ev.get("delay_h") or 0) > 48) else "borderline"
        out.append(_lab("collection", cid, dev, "DELAYED_COLLECTION", sev, True, cause, None, t,
                        extra={"full_hours_before_collection": fh}))
    g = charge["grade_applied"]
    if spec["credit_eligible"] and g in ("B", "C", "R"):
        rA = price_event(v, ev["status"], charge["billing_mass_kg"], "A", charge["index_price_cents_per_t"],
                         emergency=(ev.get("orig_trigger") if ev["trigger"] == "RESCHEDULED" else ev["trigger"]) == "AD_HOC_CUSTOMER", side_waste=ev["true_side_waste_collected_kg"] > 0,
                         credit_eligible=True)
        sA = summarize(rA["lines"], charge["billing_mass_kg"])
        loss = (charge["total_customer_cost_cents"] - sA["total_customer_cost_cents"]) / 100
        fam = "REJECTED_LOAD" if g == "R" else "CONTAMINATION_VALUE_LOSS"
        if g == "B" and loss < 25:
            fam = None
        if fam:
            out.append(_lab("collection", cid, dev, fam, "borderline" if g == "B" else "clear", g != "B" or loss > 20,
                        f"GRADE_{g}", loss, t, extra={"true_contamination_pct": round(ev["true_contamination"] * 100, 1)}))
    if ev["true_moisture_extra"] > 0.12:
        out.append(_lab("collection", cid, dev, "MOISTURE_HEAVY_LOAD", "borderline" if ev["true_moisture_extra"] < 0.2 else "clear",
                        False, "RAIN_ON_OUTDOOR_STAGING", None, t, extra={"true_moisture_extra_pct": round(ev["true_moisture_extra"] * 100, 1)}))
    est = dev_obs.get("est")
    if ticket is not None and ticket.get("public") and est is not None:      # only discrepancies a customer can observe
        net = ticket["allocated_net_kg"]
        diff = est - net
        if net > 0 and abs(diff) > 100 and abs(diff) / net > 0.10:
            if ticket["loads_on_vehicle"] > 1:
                cause = "COMBINED_LOAD_ALLOCATION"
            elif ev["true_side_waste_collected_kg"] > 0.08 * max(net, 1):
                cause = "SIDE_WASTE_ON_SAME_TRUCK"
            elif abs(ticket["tare_error_kg"]) > 100:
                cause = "WEIGHBRIDGE_TARE_ERROR"
            elif sens_active:
                cause = "DEVICE_SENSOR_" + sens_active[0]
            else:
                cause = "MEASUREMENT_NOISE_OR_TIMING"
            sev = "clear" if abs(diff) / net > 0.2 else "borderline"
            out.append(_lab("collection", cid, dev, "WEIGHT_DISCREPANCY", sev, cause.startswith("DEVICE_SENSOR") or cause == "WEIGHBRIDGE_TARE_ERROR",
                            cause, None, t, extra={"device_minus_weighbridge_kg": round(diff, 1)}))
    return out


def device_period_labels(spec: dict, arr: dict, tb, hours_ms) -> list:
    dev = spec["device_id"]
    ep = spec["episodes"]
    out = []
    N = tb.n_hours

    def ms(h):
        return int(hours_ms[min(max(int(h), 0), N - 1)])

    for j, (kind, s_h, e_h, val) in enumerate(arr["sensor_events"]):
        fam = {"DRIFT": "SENSOR_DRIFT", "CALIBRATION_OFFSET": "CALIBRATION_ERROR", "CALIBRATION_GAIN": "CALIBRATION_ERROR",
               "FAULT": "SENSOR_FAULT", "FAULT_BEFORE_REPLACEMENT": "SENSOR_FAULT", "REPLACEMENT": "SENSOR_REPLACEMENT",
               "DEGRADED": "SENSOR_DEGRADED"}[kind]
        observable = fam in ("SENSOR_FAULT", "SENSOR_REPLACEMENT", "SENSOR_DEGRADED")
        out.append(_lab("device_period", f"{dev}:{fam}:{s_h}:{j}", dev, fam, "clear", not observable, kind, None, ms(s_h), ms(e_h),
                        extra={"parameter": float(val)}))
    for k, (d0, d1, mult) in enumerate(ep["campaigns"]):
        out.append(_lab("device_period", f"{dev}:HIGH_GENERATION:{d0}:{k}", dev, "HIGH_GENERATION", "clear" if mult > 2 else "borderline",
                        False, "CAMPAIGN_OR_INVENTORY", None, ms(tb.day_start_h[min(d0, tb.n_days - 1)]),
                        ms(tb.day_start_h[min(d1, tb.n_days - 1)]), extra={"parameter": mult}))
    for k, (d0, d1, add) in enumerate(ep["contam_incidents"]):
        out.append(_lab("device_period", f"{dev}:CONTAMINATION_INCIDENT:{d0}:{k}", dev, "CONTAMINATION_INCIDENT",
                        "clear" if add > 0.15 else "borderline", True, "SORTING_FAILURE", None,
                        ms(tb.day_start_h[min(d0, tb.n_days - 1)]), ms(tb.day_start_h[min(d1, tb.n_days - 1)]), extra={"parameter": add}))
    if ep["density_shift"] is not None:
        d0, kind, mult = ep["density_shift"]
        out.append(_lab("device_period", f"{dev}:DENSITY_SHIFT:{d0}", dev, "DENSITY_SHIFT", "clear", kind == "MIX_CHANGE", kind, None,
                        ms(tb.day_start_h[min(d0, tb.n_days - 1)]), None, extra={"parameter": mult}))
    if ep.get("delay_episode"):
        d0, d1 = ep["delay_episode"]
        out.append(_lab("device_period", f"{dev}:OPERATOR_DELAY_EPISODE:{d0}", dev, "OPERATOR_DELAY_EPISODE", "clear", True,
                        "OPERATOR_CAPACITY", None, ms(tb.day_start_h[min(d0, tb.n_days - 1)]), ms(tb.day_start_h[min(d1, tb.n_days - 1)])))
    for k, (d0, d1) in enumerate(ep.get("latency", [])):
        out.append(_lab("device_period", f"{dev}:TELEMETRY_LATENCY:{d0}:{k}", dev, "TELEMETRY_LATENCY", "clear", False, "NETWORK", None,
                        ms(tb.day_start_h[min(d0, tb.n_days - 1)]), ms(tb.day_start_h[min(d1, tb.n_days - 1)])))
    if ep.get("dup_burst"):
        d0, d1 = ep["dup_burst"]
        out.append(_lab("device_period", f"{dev}:DUPLICATE_BURST:{d0}", dev, "DUPLICATE_BURST", "clear", False, "GATEWAY_RETRY", None,
                        ms(tb.day_start_h[min(d0, tb.n_days - 1)]), ms(tb.day_start_h[min(d1, tb.n_days - 1)])))
    for k, (st, dur) in enumerate(ep["breakdowns"]):
        out.append(_lab("device_period", f"{dev}:BREAKDOWN:{st}:{k}", dev, "BREAKDOWN", "clear", False, "EQUIPMENT", None, ms(st), ms(st + dur)))
    for k, (d0, d1, lvl) in enumerate(ep.get("fill_false_high", [])):
        out.append(_lab("device_period", f"{dev}:FILL_SENSOR_FALSE_HIGH:{d0}:{k}", dev, "FILL_SENSOR_FALSE_HIGH", "clear", True,
                        "BRIDGING_OR_OBSTRUCTION", None, ms(tb.day_start_h[min(d0, tb.n_days - 1)]),
                        ms(tb.day_start_h[min(d1, tb.n_days - 1)]), extra={"parameter": lvl}))
    if spec["misalloc_share"] > 0:
        sh = spec["misalloc_share"]
        out.append(_lab("device", f"{dev}:RECYCLABLES_IN_MIXED", dev, "RECYCLABLES_IN_MIXED", "clear" if sh >= 0.1 else "borderline",
                        True, "MIS_SORTING", None, ms(tb.day_start_h[0]), None, extra={"parameter": sh}))
    return out
