"""Chunk pipeline: simulate a group of organisations end-to-end and return table fragments."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import numpy as np
import pandas as pd

from .decisions import candidate_actions, evaluate_case, label_case
from .labels import collection_labels, device_period_labels
from .operator_records import build_invoices, expected_charges, weighbridge_and_quality
from .rng import KeyedRandom, rng_for
from .scenarios import assign_episodes
from .simulate import Ctx, prepare, run_policy
from .telemetry import build_telemetry
from .world import INDEX_ID

H = 3_600_000


def closures_from_calendar(world) -> dict:
    tb = world.tb
    out = {}
    for sid, (od, oh, ch, reason, act) in world.site_open.items():
        runs, i = [], 0
        while i < tb.n_days:
            if reason[i] in ("PLANNED_CLOSURE", "SUMMER_SHUTDOWN"):
                j = i
                while j < tb.n_days and reason[j] == reason[i]:
                    j += 1
                runs.append((i, j, reason[i]))
                i = j
            else:
                i += 1
        out[sid] = runs
    return out


def make_ctx(cfg, world, weather) -> Ctx:
    vers = defaultdict(list)
    for r in world.contract_versions.sort_values(["contract_id", "version_no"]).to_dict("records"):
        vers[r["contract_id"]].append(r)
    idx = {(r["index_id"], r["month"]): int(round(r["price_eur_per_t"] * 100)) for r in world.price_index.to_dict("records")}
    return Ctx(world.tb, cfg.assumptions, cfg.seed, cfg.profile, world.site_open, weather, dict(vers), idx,
               world.tb.month_key_d(), closures_from_calendar(world))


def decision_hours(tb, profile, split: str) -> list:
    """Return list of (hour_index, split_label)."""
    every = int(profile["decision_case_every_days"])
    H_d = int(profile["decision_horizon_days"])
    lp = profile["label_periods"]
    out = []
    if split == "holdout":
        cut = profile.get("private_decision_cutoff")
        if cut:
            d = tb.day_of_date(cut)
            if 0 <= d and d + H_d <= tb.n_days:
                out.append((int(tb.day_start_h[d] + 6), "test_private"))
        return out
    first = every if profile["profile"] == "quickstart" else 2 * every
    val_end = tb.day_of_date(lp["validation"][1])
    train_end = tb.day_of_date(lp["train"][1])
    d = first
    while d + H_d <= tb.n_days:
        if d < train_end:
            lab = "train"
        elif d < val_end:
            lab = "validation"
        else:
            if profile["profile"] != "quickstart" or profile.get("private_decision_cutoff"):
                break
            lab = "test"
        out.append((int(tb.day_start_h[d] + 6), lab))
        d += every
    return out


def period_of(ms: int, bounds) -> str:
    for name, (a, b) in bounds.items():
        if a <= ms < b:
            return name
    return "outside"


def _public_trigger(t):
    """The operator/customer record shows that the customer called; the precautionary motive is not recorded."""
    return "CUSTOMER_REQUEST" if t == "CUSTOMER_PRECAUTIONARY" else t


def run_chunk(cfg, world, ctx: Ctx, device_ids: list, split_of: dict, extraction_ms: int, bounds_ms: dict) -> dict:
    tb = world.tb
    A = cfg.assumptions
    N = tb.n_hours
    hours_ms = tb.hours_utc.as_unit("ms").asi8
    prof = cfg.profile
    seed = cfg.seed
    T = defaultdict(list)
    all_events = []
    completed = []
    dev_obs_of = {}
    sens_active_of = {}
    vehicles = defaultdict(list)
    for v in world.vehicles.to_dict("records"):
        vehicles[v["operator_id"]].append(v)
    facilities = {}
    for f in world.facilities.to_dict("records"):
        facilities[(f["operator_id"], f["region_code"])] = f["facility_id"]
        facilities.setdefault(f["operator_id"], []).append(f["facility_id"])
    intensity = float(prof.get("scenario_intensity", 1.0))
    for dev in device_ids:
        spec = world.specs[dev]
        spec["index_id"] = INDEX_ID.get(spec["material"])
        spec["episodes"] = assign_episodes(spec, tb, seed, intensity)
        arr = prepare(spec, ctx)
        res = run_policy(spec, arr, ctx, spec["policy"], 0, N, {}, KeyedRandom(seed, "ops", dev))
        tel = build_telemetry(spec, arr, res, ctx)
        H_h = int(prof["decision_horizon_days"]) * 24
        for dh, lab in decision_hours(tb, prof, split_of[dev]):
            if not (res["h0"] + 24 <= dh < res["h1"] - H_h):
                continue
            case_id = f"DC-{spec['device_num']:05d}-{dh:05d}"
            outs = evaluate_case(spec, arr, res, ctx, dh, H_h, case_id, int(prof.get("decision_replications", 1)))
            lc = label_case(outs)
            sens = [k for (k, s_, e_, v_) in arr["sensor_events"] if s_ <= dh < e_ and k in ("DRIFT", "CALIBRATION_OFFSET", "CALIBRATION_GAIN", "FAULT", "DEGRADED", "FAULT_BEFORE_REPLACEMENT")]
            T["decision_cases"].append({"case_id": case_id, "device_id": dev, "decision_ms": int(hours_ms[dh]),
                                        "horizon_days": int(prof["decision_horizon_days"]), "split": lab,
                                        "candidate_actions": ",".join(candidate_actions(spec)),
                                        "diagnostic_actions": "VERIFY_WEIGHT_SENSOR,REVIEW_INVOICES"})
            T["decision_truth"].append({"case_id": case_id, "split": lab, **lc,
                                        "truth_sensor_issue_active": ",".join(sens) if sens else None,
                                        "truth_invoice_overcharge_90d_eur": 0.0})
            for o in outs:
                T["decision_outcomes"].append({**o, "split": lab})
        h0, h1 = res["h0"], res["h1"]
        dn = spec["device_num"]
        op = spec["operator_id"]
        # ---------- truth hourly ----------
        if h1 > h0 and not prof.get("skip_truth_hourly", False):
            sl = slice(h0, h1)
            T["truth_hourly_state"].append(pd.DataFrame({
                "device_id": pd.Series([dev] * (h1 - h0), dtype="string").astype("category"), "hour_start_ms": hours_ms[sl],
                "true_container_mass_kg": res["m_true"].astype(np.float32),
                "true_fill_pct": res["fill_true"].astype(np.float32),
                "true_inflow_kg": arr["inflow"][sl].astype(np.float32),
                "true_side_stock_kg": res["side_stock"].astype(np.float32),
                "true_container_full": res["full"], "true_compactor_down": arr["down"][sl],
                "true_sensor_gain": arr["gain"][sl].astype(np.float32),
                "true_sensor_offset_kg": arr["offset"][sl].astype(np.float32)}))
        if tel["rows"] is not None:
            tdf = pd.DataFrame(tel["rows"])
            for c in ("device_id", "sensor_id", "operational_state", "sensor_status", "quality_flag", "delivery_mode"):
                tdf[c] = tdf[c].astype("string").astype("category")
            T["telemetry_hourly"].append(tdf)
        # ---------- events ----------
        sens_ev = arr["sensor_events"]
        for ev in res["events"]:
            ev["device_id"] = dev
            ev["collection_id"] = f"COL-{dn:05d}-{ev['seq']:04d}"
            ev["operator_job_ref"] = f"{op}-{dn:05d}{ev['seq']:04d}"
            if ev["trigger"] == "RESCHEDULED":
                ev["orig_trigger"] = ev.get("orig_trigger") or "SCHEDULED"
            ah = ev.get("actual_h")
            ev["actual_ms"] = int(hours_ms[ah] + rng_for(seed, "min", ev["collection_id"]).integers(0, 3600) * 1000) if ah is not None else None
            ev["actual_day"] = int(tb.day_idx[ah]) if ah is not None else None
            ev["sched_ms"] = int(hours_ms[min(ev["sched_h"], N - 1)])
            ev["order_ms"] = int(hours_ms[min(max(ev["order_h"], 0), N - 1)]) if ev.get("order_h") is not None else None
            ev["order_day"] = int(tb.day_idx[min(max(ev["order_h"], 0), N - 1)]) if ev.get("order_h") is not None else None
            obs = {"fill_b": None, "fill_a": None, "mass_b": None, "mass_a": None, "est": None}
            if ev["status"] in ("COMPLETED", "PARTIAL"):
                ib, ia = ah - 1 - h0, ah - h0
                if 0 <= ib < len(tel["obs_fill"]):
                    obs["fill_b"] = None if np.isnan(tel["obs_fill"][ib]) else float(tel["obs_fill"][ib])
                    obs["mass_b"] = None if np.isnan(tel["obs_mass"][ib]) else float(tel["obs_mass"][ib])
                if 0 <= ia < len(tel["obs_fill"]):
                    obs["fill_a"] = None if np.isnan(tel["obs_fill"][ia]) else float(tel["obs_fill"][ia])
                    obs["mass_a"] = None if np.isnan(tel["obs_mass"][ia]) else float(tel["obs_mass"][ia])
                if obs["mass_b"] is not None and obs["mass_a"] is not None:
                    obs["est"] = round(obs["mass_b"] - obs["mass_a"], 1)
                completed.append(ev)
                sens_active_of[ev["collection_id"]] = [k for (k, s, e, v) in sens_ev if s <= ah < e and k in
                                                       ("DRIFT", "CALIBRATION_OFFSET", "CALIBRATION_GAIN", "DEGRADED")]
            dev_obs_of[ev["collection_id"]] = obs
            all_events.append(ev)
        # ---------- maintenance, sensors ----------
        for wo in arr["work_orders"]:
            T["maintenance_work_orders"].append({
                "work_order_id": wo["work_order_id"], "device_id": dev, "work_order_type": wo["work_order_type"],
                "reported_ms": int(hours_ms[wo["reported_h"]]), "started_ms": int(hours_ms[wo["start_h"]]),
                "completed_ms": int(hours_ms[min(wo["end_h"], N - 1)]), "downtime_hours": wo["downtime_hours"],
                "description_code": wo["description_code"]})
        if spec["has_weight_sensor"]:
            repl = [s for (k, s, e, v) in sens_ev if k == "REPLACEMENT"]
            inst0 = world.devices.set_index("device_id").loc[dev, "commissioned_on"]
            T["sensor_registry"].append({"sensor_id": f"WS-{dn:05d}-1", "device_id": dev, "sensor_type": "GENERIC_INTEGRATED_WEIGHT (simulated)",
                                         "installed_ms": int(pd.Timestamp(inst0).tz_localize("UTC").value // 10 ** 6),
                                         "removed_ms": int(hours_ms[repl[0]]) if repl else None,
                                         "nominal_sigma_kg": A["telemetry"]["mass_sigma_abs_kg"],
                                         "nominal_sigma_rel": A["telemetry"]["mass_sigma_rel"]})
            if repl:
                T["sensor_registry"].append({"sensor_id": f"WS-{dn:05d}-2", "device_id": dev, "sensor_type": "GENERIC_INTEGRATED_WEIGHT (simulated)",
                                             "installed_ms": int(hours_ms[repl[0]]), "removed_ms": None,
                                             "nominal_sigma_kg": A["telemetry"]["mass_sigma_abs_kg"],
                                             "nominal_sigma_rel": A["telemetry"]["mass_sigma_rel"]})
        for (k, s, e, v) in sens_ev:
            T["truth_sensor_episodes"].append({"device_id": dev, "episode_type": k, "start_ms": int(hours_ms[min(s, N - 1)]),
                                               "end_ms": int(hours_ms[min(e, N - 1)]) if e < N else None, "parameter": float(v)})
        T["anomaly_labels"].extend(device_period_labels(spec, arr, tb, hours_ms))
        T["truth_device"].append({"device_id": dev, "true_mean_density_kg_m3": round(spec["density"], 1),
                                  "true_daily_generation_kg": round(spec["daily_kg"], 1), "true_capacity_mass_kg": round(spec["cap_mass_kg"], 1),
                                  "true_contamination_base": round(spec["contam_base"], 4), "true_misallocated_recyclable_share": round(spec["misalloc_share"], 4),
                                  "split": split_of[dev], "n_messages_lost": tel.get("n_lost", 0), "n_duplicates": tel.get("n_dup", 0),
                                  "true_total_inflow_kg": round(float(arr["inflow"][h0:h1].sum()), 3),
                                  "true_end_container_kg": round(float(res["m_true"][-1]) if h1 > h0 else 0.0, 3),
                                  "true_end_side_stock_kg": round(float(res["side_stock"][-1]) if h1 > h0 else 0.0, 3),
                                  "episodes": str({k: v for k, v in spec["episodes"].items() if v})})

    # ---------- operator side ----------
    tickets, quality, by_job = weighbridge_and_quality(completed, world.specs, ctx, vehicles, facilities, extraction_ms)
    charges = expected_charges(all_events, world.specs, ctx, by_job)
    specs_by_contract = {world.specs[d]["contract_id"]: world.specs[d] for d in device_ids}
    invoices, lines, line_labels, coll_inv_labels = build_invoices(charges, specs_by_contract, ctx, ctx.versions, extraction_ms)
    charge_of = {c["collection_id"]: c for c in charges}
    invoiced_refs = {l["operator_job_ref"] for l in lines if l["operator_job_ref"]}
    tonnage_refs = {l["operator_job_ref"] for l in lines if l["operator_job_ref"] and l["unit"] == "t"}

    for ev in all_events:
        s = world.specs[ev["device_id"]]
        obs = dev_obs_of[ev["collection_id"]]
        t = by_job.get(ev["collection_id"])
        st = ev["status"]
        if st in ("COMPLETED", "PARTIAL"):
            if t is None or not t["public"]:
                wrs = "WEIGHBRIDGE_NOT_AVAILABLE"
            elif obs["est"] is None:
                wrs = "DEVICE_ESTIMATE_MISSING"
            elif t["allocated_net_kg"] > 0 and abs(obs["est"] - t["allocated_net_kg"]) <= 0.10 * t["allocated_net_kg"]:
                wrs = "WITHIN_10PCT"
            else:
                wrs = "DIFFERENCE_GT_10PCT"
        else:
            wrs = "NOT_APPLICABLE"
        has_charge = bool(charge_of[ev["collection_id"]]["lines"])
        inv = "MATCHED_BY_JOB_REF" if ev["operator_job_ref"] in invoiced_refs else ("NO_CHARGE_EXPECTED" if not has_charge else "NOT_FOUND_ON_INVOICES")
        T["collection_events"].append({
            "collection_id": ev["collection_id"], "device_id": ev["device_id"], "site_id": s["site_id"],
            "customer_id": s["customer_id"], "contract_id": s["contract_id"], "operator_id": s["operator_id"],
            "operator_job_ref": ev["operator_job_ref"], "trigger_type": _public_trigger(ev["trigger"]),
            "original_trigger_type": _public_trigger((ev.get("orig_trigger") or "SCHEDULED") if ev["trigger"] == "RESCHEDULED" else ev["trigger"]),
            "order_placed_ms": ev["order_ms"], "scheduled_ms": ev["sched_ms"], "actual_ms": ev["actual_ms"],
            "status": st, "cancellation_notice_hours": None if ev.get("notice_h") is None else round(ev["notice_h"], 1),
            "wasted_trip_reason": ev.get("wasted_reason") or ("ACCESS_BLOCKED" if st == "WASTED_TRIP" else None),
            "vehicle_id": t["vehicle_id"] if t is not None else None,
            "driver_reported_side_waste": bool(ev.get("true_side_waste_collected_kg", 0) > 0) if st in ("COMPLETED", "PARTIAL") else None,
            "driver_reported_partial": st == "PARTIAL",
            "device_fill_pct_before": obs["fill_b"], "device_fill_pct_after": obs["fill_a"],
            "device_mass_kg_before": obs["mass_b"], "device_mass_kg_after": obs["mass_a"],
            "device_estimated_collected_kg": obs["est"],
            "weight_reconciliation_status": wrs, "invoice_match_status": inv})
        if st in ("COMPLETED", "PARTIAL"):
            T["truth_collections"].append({k: ev.get(k) for k in (
                "collection_id", "device_id", "true_mass_before_kg", "true_fill_before_pct", "true_collected_kg",
                "true_residual_kg", "true_side_waste_collected_kg", "true_side_stock_before_kg", "true_contamination",
                "true_moisture_extra", "hours_since_last", "cycle_overflow_kg", "cycle_full_hours", "delay_h")})
            T["anomaly_labels"].extend(collection_labels(ev, s, charge_of[ev["collection_id"]], t, obs,
                                                         sens_active_of.get(ev["collection_id"], [])))
        c = charge_of[ev["collection_id"]]
        T["reference_economics"].append({
            "collection_id": c["collection_id"], "device_id": c["device_id"], "contract_id": c["contract_id"],
            "contract_version_id": c["contract_version_id"], "service_date": c["service_date"], "status": c["status"],
            "billing_mass_kg": c["billing_mass_kg"], "billing_mass_basis": c["billing_mass_basis"], "grade_applied": c["grade_applied"],
            "index_price_eur_per_t": None if c["index_price_cents_per_t"] is None else c["index_price_cents_per_t"] / 100,
            "collection_cost_eur": c["collection_cost_cents"] / 100, "processing_cost_eur": c["processing_cost_cents"] / 100,
            "penalties_eur": c["penalties_cents"] / 100, "material_credit_eur": c["material_credit_cents"] / 100,
            "net_material_contribution_eur": c["net_material_contribution_cents"] / 100,
            "total_customer_cost_eur": c["total_customer_cost_cents"] / 100,
            "expected_invoice_amount_eur": c["invoice_amount_cents"] / 100,
            "collection_cost_eur_per_t": c["collection_cost_eur_per_t"], "total_cost_eur_per_t": c["total_cost_eur_per_t"],
            "observable_mass_source": (None if c["status"] not in ("COMPLETED", "PARTIAL") else
                                       "WEIGHBRIDGE_PUBLISHED" if (t is not None and t["public"]) else
                                       "INVOICE_TONNAGE" if ev["operator_job_ref"] in tonnage_refs else
                                       "DEVICE_ESTIMATE_ONLY" if obs["est"] is not None else "NONE"),
            "event_ms": ev["actual_ms"] if ev["actual_ms"] is not None else ev["sched_ms"]})
        for k, ln in enumerate(c["lines"]):
            T["reference_charge_lines"].append({"collection_id": c["collection_id"], "line_no": k + 1, "line_type": ln["line_type"],
                                                "quantity": float(ln["quantity"]), "unit": ln["unit"],
                                                "unit_price_eur": ln["unit_price_cents"] / 100, "amount_eur": ln["amount_cents"] / 100})
    for t in tickets:
        T["weighbridge_all"].append(t)
    T["quality_all"].extend(quality)
    T["invoices"].extend(invoices)
    T["invoice_lines"].extend(lines)
    inv_ms = {i["invoice_id"]: i["issued_ms"] for i in invoices}
    dev_of_contract = {world.specs[d]["contract_id"]: d for d in device_ids}
    dev_of_coll = {e["collection_id"]: e["device_id"] for e in all_events}
    act_ms_of = {e["collection_id"]: (e["actual_ms"] or e["sched_ms"]) for e in all_events}
    for ll in line_labels:
        fam = ll["discrepancy_type"]
        dev = dev_of_contract.get("CTR-" + ll["invoice_id"][4:9])
        T["invoice_line_labels"].append(ll)
        T["anomaly_labels"].append({"entity_type": "invoice_line", "entity_id": ll["invoice_line_id"], "device_id": dev,
                                    "label_family": fam.split(":")[0], "severity": "clear" if abs(ll["delta_cents"]) >= 2000 else "borderline",
                                    "is_actionable": True, "explanation_code": fam, "value_at_stake_eur": ll["delta_cents"] / 100,
                                    "event_ms": inv_ms[ll["invoice_id"]], "end_ms": None, "scenario_id": None})
    for cl in coll_inv_labels:
        dev = dev_of_coll.get(cl["collection_id"])
        T["invoice_line_labels"].append({"invoice_line_id": None, **cl})
        T["anomaly_labels"].append({"entity_type": "collection", "entity_id": cl["collection_id"], "device_id": dev,
                                    "label_family": cl["discrepancy_type"].split(":")[0], "severity": "clear" if abs(cl["delta_cents"]) >= 2000 else "borderline",
                                    "is_actionable": True, "explanation_code": cl["discrepancy_type"], "value_at_stake_eur": cl["delta_cents"] / 100,
                                    "event_ms": act_ms_of.get(cl["collection_id"]) or inv_ms.get(cl["invoice_id"], 0), "end_ms": None, "scenario_id": None})

    # ---------- decision cases ----------
    over_by_contract = defaultdict(list)
    for ll in line_labels:
        over_by_contract["CTR-" + ll["invoice_id"][4:9]].append((inv_ms[ll["invoice_id"]], ll["delta_cents"]))
    for cl in coll_inv_labels:
        over_by_contract["CTR-" + cl["invoice_id"][4:9]].append((inv_ms.get(cl["invoice_id"], 0), cl["delta_cents"]))
    for dt_row, dc in zip(T["decision_truth"], T["decision_cases"]):
        dms = dc["decision_ms"]
        cid = world.specs[dc["device_id"]]["contract_id"]
        over = sum(max(0, d) for (t_, d) in over_by_contract.get(cid, []) if dms - 90 * 24 * H <= t_ < dms)
        dt_row["truth_invoice_overcharge_90d_eur"] = over / 100
    return T
