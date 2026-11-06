"""Operator-side records: weighbridge tickets, quality assessments, expected charges and invoices.

Billing basis follows the (fictional) contracts: per-tonne lines use the operator's weighbridge net
weight allocated to the job; if the operator has no ticket, the contractual default weight is used.
Invoices are generated from expected charges and then perturbed with labelled discrepancies.
Discrepancy labels are descriptive (e.g. DUPLICATE_LINE); none implies intent or fraud.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np
import pandas as pd

from .economics import price_event, summarize, rhu
from .rng import rng_for
from .simulate import version_at

H = 3_600_000  # ms per hour
INVOICE_NOTE = "SYNTHETIC invoice from a fictional waste operator to a fictional customer; not a real invoice"


def weighbridge_and_quality(events: list, specs: dict, ctx, vehicles: dict, facilities: dict, extraction_ms: int):
    """events: completed collection dicts (with collection_id, device_id, actual_ms, true kg ...)."""
    A = ctx.A
    ops = A["operations"]
    grades = A["quality_grades"]
    intensity = ctx.profile.get("scenario_intensity", 1.0)
    tickets, quality = [], []
    by_job = {}
    # combined loads: same customer, operator, material, local date
    groups = defaultdict(list)
    for e in events:
        s = specs[e["device_id"]]
        groups[(s["customer_id"], s["operator_id"], s["material"], e["actual_day"])].append(e)
    paired = {}
    for key, g in groups.items():
        if len(g) >= 2:
            r = rng_for(ctx.seed, "combined", *map(str, key))
            if r.random() < ops["combined_load_prob"] * 3 * intensity:
                a, b = g[0], g[1]
                paired[a["collection_id"]] = b
                paired[b["collection_id"]] = a
    done = set()
    for e in events:
        if e["collection_id"] in done:
            continue
        s = specs[e["device_id"]]
        op = s["operator_id"]
        oc = A["operators"][op]
        r = rng_for(ctx.seed, "ticket", e["collection_id"])
        members = [e]
        if e["collection_id"] in paired:
            members.append(paired[e["collection_id"]])
        for m in members:
            done.add(m["collection_id"])
        fleet = vehicles[op]
        veh = fleet[int(r.integers(len(fleet)))]
        if r.random() < 0.006:        # operator scale outage: no ticket at all
            for m in members:
                by_job[m["collection_id"]] = None
            continue
        net_true = sum(m["true_collected_kg"] + m["true_side_waste_collected_kg"] for m in members)
        res = ops["weighbridge_resolution_kg"]
        gross = veh["true_tare_kg"] + net_true + r.normal(0, ops["weighbridge_sigma_kg"])
        gross = int(round(gross / res) * res)
        stored = r.random() < ops["stored_tare_prob"]
        tare = veh["stored_tare_kg"] if stored else veh["true_tare_kg"] + r.normal(0, 8)
        tare = int(round(tare / res) * res)
        net = gross - tare
        km = s["billable_km"]
        arrival = max(m["actual_ms"] for m in members) + int((km / 2 / 45 + r.uniform(0.2, 1.5)) * H)
        share = r.random() < oc["weighbridge_share_prob"]
        lag_d = r.uniform(*oc["share_lag_days"]) if share else None
        if share and r.random() < 0.05 * intensity:
            lag_d += r.uniform(20, 90)                     # S19 extra-late records
        published = arrival + int(lag_d * 24 * H) if share else None
        fac = facilities[(op, s["region"])] if (op, s["region"]) in facilities else facilities[op][0]
        tid = f"WB-{op}-{e['collection_id'][4:]}"
        if len(members) > 1:
            alloc = [int(round(net / len(members) / res) * res)] * len(members)
            alloc[-1] = net - sum(alloc[:-1])
            method = "EQUAL_SPLIT_COMBINED_LOAD"
        else:
            alloc = [net]
            method = "SINGLE_LOAD"
        for m, an in zip(members, alloc):
            t = {"ticket_id": tid if len(members) == 1 else f"{tid}-{members.index(m) + 1}",
                 "weighing_event_id": tid, "operator_id": op, "operator_job_ref": m["operator_job_ref"],
                 "collection_id": m["collection_id"], "vehicle_id": veh["vehicle_id"], "facility_id": fac,
                 "arrival_ms": arrival, "gross_kg": gross, "tare_kg": tare,
                 "tare_method": "STORED" if stored else "WEIGHED", "net_kg": net, "allocated_net_kg": int(an),
                 "allocation_method": method, "loads_on_vehicle": len(members),
                 "material_declared": s["material"], "shared_with_customer": bool(share), "published_ms": published,
                 "public": bool(share and published is not None and published <= extraction_ms),
                 "true_net_kg": round(m["true_collected_kg"] + m["true_side_waste_collected_kg"], 1),
                 "tare_error_kg": tare - veh["true_tare_kg"]}
            tickets.append(t)
            by_job[m["collection_id"]] = t
            if s["credit_eligible"]:
                rq = rng_for(ctx.seed, "quality", m["collection_id"])
                est = float(np.clip(m["true_contamination"] + rq.normal(0, 0.02), 0, 1))
                est = round(est, 2)
                g = "A" if est <= grades["A"]["max_contamination"] else "B" if est <= grades["B"]["max_contamination"] \
                    else "C" if est <= grades["C"]["max_contamination"] else "R"
                downgraded = False
                if s["material"] in ("cardboard", "paper") and m["true_moisture_extra"] > 0.15 and rq.random() < 0.5 and g != "R":
                    g = {"A": "B", "B": "C", "C": "R"}[g]
                    downgraded = True
                qpub = published + int(rq.uniform(0, 72) * H) if published is not None else None
                quality.append({"quality_assessment_id": f"QA-{m['collection_id'][4:]}", "collection_id": m["collection_id"],
                                "ticket_id": t["ticket_id"], "operator_id": op, "assessed_ms": arrival + int(rq.uniform(1, 30) * H),
                                "published_ms": qpub, "public": bool(qpub is not None and qpub <= extraction_ms),
                                "material_declared": s["material"], "contamination_pct_est": round(est * 100, 0),
                                "grade": g, "rejected": g == "R",
                                "remark_code": "WET_MATERIAL" if downgraded else ("REJECTED_CONTAMINATION" if g == "R" else None)})
                m["assessed_grade"] = g
    return tickets, quality, by_job


def expected_charges(all_events: list, specs: dict, ctx, by_job: dict):
    """Correct (reference) charges per event, using operator billing basis. Returns list of dicts."""
    tb = ctx.tb
    out = []
    for e in all_events:
        s = specs[e["device_id"]]
        versions = ctx.versions[s["contract_id"]]
        t_h = e["actual_h"] if e.get("actual_h") is not None else e["sched_h"]
        t_h = min(int(t_h), tb.n_hours - 1)
        di = int(tb.day_idx[t_h])
        d = tb.dates[di]
        v = version_at(versions, d)
        st = e["status"]
        kg = None
        basis = None
        grade = None
        idx = None
        if st in ("COMPLETED", "PARTIAL"):
            t = by_job.get(e["collection_id"])
            if t is None:
                kg = int(v["default_weight_kg"])
                basis = "CONTRACT_DEFAULT_WEIGHT"
            else:
                kg = max(0, int(t["allocated_net_kg"]))
                basis = "WEIGHBRIDGE_NET"
            grade = e.get("assessed_grade") if s["credit_eligible"] else None
            if s["credit_eligible"] and grade is None:
                grade = "A" if t is None else grade
            idx = ctx.index_cents.get((s.get("index_id"), ctx.month_key_d[di]))
        r = price_event(v, st, kg, grade, idx, emergency=(e.get("orig_trigger") if e["trigger"] == "RESCHEDULED" else e["trigger"]) == "AD_HOC_CUSTOMER",
                        side_waste=e.get("true_side_waste_collected_kg", 0) > 0, notice_hours=e.get("notice_h"),
                        credit_eligible=s["credit_eligible"])
        summ = summarize(r["lines"], kg)
        out.append({"collection_id": e["collection_id"], "device_id": e["device_id"], "contract_id": s["contract_id"],
                    "contract_version_id": v["contract_version_id"], "service_date": d, "service_month": ctx.month_key_d[di],
                    "status": st, "billing_mass_kg": kg, "billing_mass_basis": basis, "grade_applied": grade,
                    "index_price_cents_per_t": idx, "lines": r["lines"], **summ,
                    "operator_job_ref": e["operator_job_ref"], "version": v})
    return out


def _typo(ref: str, rng) -> str:
    digits = [i for i, ch in enumerate(ref) if ch.isdigit()]
    if len(digits) < 2:
        return ref + "X"
    i = digits[int(rng.integers(len(digits) - 1))]
    lst = list(ref)
    j = i + 1 if lst[i + 1].isdigit() else i
    lst[i], lst[j] = lst[j], lst[i]
    if lst == list(ref):
        lst[i] = str((int(lst[i]) + 1) % 10)
    return "".join(lst)


def build_invoices(charges: list, specs_by_contract: dict, ctx, contracts_versions: dict, extraction_ms: int):
    """Monthly invoice per contract. Returns invoices, lines, line_labels, collection_labels."""
    A = ctx.A
    tb = ctx.tb
    intensity = ctx.profile.get("scenario_intensity", 1.0)
    by_cm = defaultdict(list)
    for c in charges:
        by_cm[(c["contract_id"], c["service_month"])].append(c)
    # include rental-only months for contracts with rental
    months = tb.month_keys
    for cid, s in specs_by_contract.items():
        v0 = contracts_versions[cid][0]
        if v0["rental_cents_per_month"]:
            for mk in months:
                y, mo = map(int, mk.split("-"))
                d = dt.date(y, mo, 1)
                a_from = tb.dates[min(s["act_from_day"], tb.n_days - 1)]
                a_to = tb.dates[min(s["act_to_day"], tb.n_days) - 1]
                if a_from <= dt.date(y, mo, 28) and d <= a_to:
                    by_cm.setdefault((cid, mk), [])
    invoices, lines, line_labels, coll_labels = [], [], [], []
    all_refs = {c["operator_job_ref"] for c in charges}
    for (cid, mk), evs in sorted(by_cm.items()):
        s = specs_by_contract[cid]
        op = s["operator_id"]
        err_rate = A["operators"][op]["invoice_error_rate"] * 2.2 * intensity
        r = rng_for(ctx.seed, "invoice", cid, mk)
        y, mo = map(int, mk.split("-"))
        nm = dt.date(y + (mo == 12), mo % 12 + 1, 1)
        issued = dt.datetime(nm.year, nm.month, 1) + dt.timedelta(days=int(r.integers(3, 12)), hours=int(r.integers(7, 16)))
        issued_ms = int(pd.Timestamp(issued).tz_localize(tb.tz).value // 10 ** 6)      # local business hours
        if issued_ms > extraction_ms:
            continue      # not yet issued at extraction time
        inv_id = f"INV-{cid[4:]}-{y:04d}{mo:02d}"
        vers = contracts_versions[cid]
        # outdated tariff: a version became effective this month or last month
        month_start = dt.date(y, mo, 1)
        prev_month = (month_start - dt.timedelta(days=1)).replace(day=1)
        changed = [v for v in vers if v["version_no"] > 1 and month_start <= v["effective_from"] < nm]
        outdated = bool(changed) and r.random() < 0.12 * intensity ** 0.5
        inv_lines = []

        def push(c, ln, label=None, expected=None, ref=None):
            inv_lines.append({"_c": c, "ln": dict(ln), "label": label, "expected": expected,
                              "ref": ref if ref is not None else (c["operator_job_ref"] if c else None)})

        for c in sorted(evs, key=lambda x: (x["service_date"], x["collection_id"])):
            exp_lines = c["lines"]
            billed = [dict(l) for l in exp_lines]
            labels = [None] * len(billed)
            if outdated and c["version"]["version_no"] > 1 and c["version"] in changed and billed:
                old = next(v for v in vers if v["version_no"] == c["version"]["version_no"] - 1)
                rr = price_event(old, c["status"], c["billing_mass_kg"], c["grade_applied"], c["index_price_cents_per_t"],
                                 emergency=any(l["line_type"] == "EMERGENCY_SURCHARGE" for l in exp_lines),
                                 side_waste=any(l["line_type"] == "SIDE_WASTE_FEE" for l in exp_lines),
                                 notice_hours=None if c["status"] != "CANCELLED_BY_CUSTOMER" else 0.0,
                                 credit_eligible=specs_by_contract[cid]["credit_eligible"])
                old_by = {l["line_type"]: l for l in rr["lines"]}
                for i, l in enumerate(billed):
                    o = old_by.get(l["line_type"])
                    if o is not None and o["amount_cents"] != l["amount_cents"]:
                        billed[i] = dict(o)
                        labels[i] = "OUTDATED_TARIFF"
            u = r.random()
            etype = None
            if billed and u < err_rate:
                etype = r.choice(["DUPLICATE_LINE", "MISSING_LINE", "WRONG_SURCHARGE", "WEIGHT_BASIS_MISMATCH", "UNINVOICED_COLLECTION"],
                                 p=[0.24, 0.2, 0.24, 0.2, 0.12])
            if etype == "UNINVOICED_COLLECTION" and c["status"] in ("COMPLETED", "PARTIAL"):
                coll_labels.append({"collection_id": c["collection_id"], "invoice_id": inv_id, "discrepancy_type": "UNINVOICED_COLLECTION",
                                    "expected_amount_cents": c["invoice_amount_cents"], "billed_amount_cents": 0,
                                    "delta_cents": -c["invoice_amount_cents"]})
                continue
            if etype == "MISSING_LINE":
                cand = [i for i, l in enumerate(billed) if l["line_type"] == "MATERIAL_CREDIT"] or \
                       [i for i, l in enumerate(billed) if l["line_type"] in ("LIFT_FEE", "TRANSPORT")]
                if cand:
                    i = cand[0]
                    coll_labels.append({"collection_id": c["collection_id"], "invoice_id": inv_id,
                                        "discrepancy_type": f"MISSING_LINE:{billed[i]['line_type']}",
                                        "expected_amount_cents": exp_lines[i]["amount_cents"], "billed_amount_cents": 0,
                                        "delta_cents": -exp_lines[i]["amount_cents"]})
                    billed.pop(i)
                    labels.pop(i)
                    exp_lines = exp_lines[:i] + exp_lines[i + 1:]
            elif etype == "WRONG_SURCHARGE":
                fi = [i for i, l in enumerate(billed) if l["line_type"] == "FUEL_SURCHARGE"]
                ti = [i for i, l in enumerate(billed) if l["line_type"] == "TRANSPORT"]
                if fi:
                    i = fi[0]
                    bp = int(round(billed[i]["quantity"] * 100))
                    new_bp = bp * 2 if bp else 600
                    billed[i]["quantity"] = new_bp / 100
                    billed[i]["amount_cents"] = rhu(billed[i]["unit_price_cents"] * new_bp, 10000)
                    labels[i] = "WRONG_SURCHARGE:FUEL_RATE"
                elif ti:
                    i = ti[0]
                    billed[i]["quantity"] = billed[i]["quantity"] * 2
                    billed[i]["amount_cents"] = billed[i]["amount_cents"] * 2
                    labels[i] = "WRONG_SURCHARGE:KM_DOUBLED"
                elif c["status"] in ("COMPLETED", "PARTIAL"):
                    billed.append({"line_type": "REMOTE_SURCHARGE", "quantity": 1, "unit": "lift", "unit_price_cents": 2500, "amount_cents": 2500})
                    labels.append("WRONG_SURCHARGE:REMOTE_NOT_APPLICABLE")
                    exp_lines = exp_lines + [None]
            elif etype == "WEIGHT_BASIS_MISMATCH":
                ti = [i for i, l in enumerate(billed) if l["unit"] == "t"]
                if ti:
                    f = r.uniform(1.08, 1.25)
                    for i in ti:
                        q = round(billed[i]["quantity"] * f, 3)
                        billed[i]["quantity"] = q
                        billed[i]["amount_cents"] = rhu(int(round(q * 1000)) * billed[i]["unit_price_cents"], 1000)
                        labels[i] = "WEIGHT_BASIS_MISMATCH"
            dup_after = None
            if etype == "DUPLICATE_LINE":
                di_ = [i for i, l in enumerate(billed) if l["line_type"] in ("LIFT_FEE", "TRANSPORT", "HAUL_PER_TONNE", "WASTED_TRIP_FEE")]
                if di_:
                    dup_after = di_[0]
            ref = c["operator_job_ref"]
            if r.random() < 0.012:
                ref = _typo(ref, r)
                while ref in all_refs:                 # a typo must not collide with another real job
                    ref = ref + "X"
            for i, l in enumerate(billed):
                exp_amt = exp_lines[i]["amount_cents"] if i < len(exp_lines) and exp_lines[i] is not None else 0
                push(c, l, labels[i], exp_amt, ref)
                if dup_after == i:
                    push(c, l, "DUPLICATE_LINE", 0, ref)
        # phantom (unmatched) jobs
        if evs and r.random() < err_rate * 0.6:
            c0 = evs[0]
            v = c0["version"]
            fake_day = int(r.integers(1, 28))
            fake = {"collection_id": None, "service_date": dt.date(y, mo, fake_day), "operator_job_ref": f"{op}-P{y % 100:02d}{mo:02d}{int(r.integers(10000, 99999))}"}
            if v["lift_fee_cents"]:
                push(fake, {"line_type": "LIFT_FEE", "quantity": 1, "unit": "lift", "unit_price_cents": v["lift_fee_cents"],
                            "amount_cents": v["lift_fee_cents"]}, "UNMATCHED_LINE", 0)
            km = max(0, v["contract_km"] - v["free_km"])
            if km:
                push(fake, {"line_type": "TRANSPORT", "quantity": km, "unit": "km", "unit_price_cents": v["per_km_cents"],
                            "amount_cents": km * v["per_km_cents"]}, "UNMATCHED_LINE", 0)
        # rental
        v_m = version_at(vers, dt.date(y, mo, 15))
        if v_m["rental_cents_per_month"]:
            push(None, {"line_type": "RENTAL", "quantity": 1, "unit": "month", "unit_price_cents": v_m["rental_cents_per_month"],
                        "amount_cents": v_m["rental_cents_per_month"]}, None, v_m["rental_cents_per_month"], ref="")
        if not inv_lines:
            continue
        total = 0
        for k, il in enumerate(inv_lines):
            lid = f"{inv_id}-L{k + 1:03d}"
            ln = il["ln"]
            c = il["_c"]
            total += ln["amount_cents"]
            lines.append({"invoice_line_id": lid, "invoice_id": inv_id, "line_no": k + 1, "line_type": ln["line_type"],
                          "service_date": (c["service_date"] if c else dt.date(y, mo, 1)),
                          "operator_job_ref": il["ref"] or None, "quantity": float(ln["quantity"]), "unit": ln["unit"],
                          "unit_price_eur": ln["unit_price_cents"] / 100, "amount_eur": ln["amount_cents"] / 100,
                          "synthetic": True, "_collection_id": c["collection_id"] if c else None})
            if il["label"]:
                line_labels.append({"invoice_line_id": lid, "invoice_id": inv_id, "collection_id": c["collection_id"] if c else None,
                                    "discrepancy_type": il["label"], "expected_amount_cents": il["expected"],
                                    "billed_amount_cents": ln["amount_cents"], "delta_cents": ln["amount_cents"] - (il["expected"] or 0)})
        inv_err = sum(ll["delta_cents"] for ll in line_labels if ll["invoice_id"] == inv_id) + \
            sum(cl["delta_cents"] for cl in coll_labels if cl["invoice_id"] == inv_id)
        disp = "NONE"
        if abs(inv_err) > 5000 and inv_err > 0 and r.random() < 0.4:
            disp = "RESOLVED_CREDIT_NOTE" if r.random() < 0.7 else "OPEN"
        elif r.random() < 0.05:
            disp = "RESOLVED_NO_CHANGE" if r.random() < 0.6 else "OPEN"      # unfounded or pending disputes exist too
        invoices.append({"invoice_id": inv_id, "contract_id": cid, "customer_id": s["customer_id"], "operator_id": op,
                         "billing_period": mk, "issued_ms": issued_ms, "currency": "EUR", "vat_excluded": True,
                         "total_eur": total / 100, "n_lines": len(inv_lines), "dispute_status": disp,
                         "record_note": INVOICE_NOTE, "synthetic": True})
    return invoices, lines, line_labels, coll_labels
