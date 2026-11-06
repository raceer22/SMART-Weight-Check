"""Operator-relationship ground truth (added after the Europress review of 30 Oct 2026).

Two benchmark components that put the customer in a stronger, better-informed position in the waste value
chain, using device data as an independent reference:

* Task B2 - operator performance scorecard: one row per operator x region x month with punctuality, missed
  visits, weighbridge-data sharing, billing accuracy and weight differences, computed from simulator truth.
* Task C2 - operator and contract actions: for every active contract, the value of DISPUTE_INVOICE,
  REQUEST_WEIGHBRIDGE_DATA, RENEGOTIATE_CONTRACT and TENDER_OR_SWITCH_OPERATOR under transparent, published
  valuation rules (configs/assumptions.yaml -> operator_actions).

Operators are fictional. Quality differences between them are synthetic and needed for the task; part of every
difference is explained by causes other than the operator (device sensors, combined loads, data gaps).
Europress is currently not a party to waste transport or treatment; all prices are hypothetical. The valuation
is a property of this synthetic world, not evidence of real savings.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .economics import price_event, summarize
from .export import write_parquet
from .rng import rng_for

COMPLETED = ("COMPLETED", "PARTIAL")
OPERATOR_STATUSES = ("COMPLETED", "PARTIAL", "MISSED_BY_OPERATOR", "WASTED_TRIP")
RECOVERABLE_TYPES = ("DUPLICATE_LINE", "WRONG_SURCHARGE", "WEIGHT_BASIS_MISMATCH", "OUTDATED_TARIFF", "UNMATCHED_LINE")
FEE_FIELDS = ["lift_fee_cents", "per_km_cents", "fuel_surcharge_bp", "haul_fee_cents_per_t", "processing_fee_cents_per_t",
              "min_charge_cents", "rental_cents_per_month", "contamination_penalty_cents", "rejection_fee_cents_per_t",
              "cancellation_fee_cents", "wasted_trip_fee_cents", "side_waste_fee_cents", "emergency_surcharge_cents"]
C2_ACTIONS = ["DISPUTE_INVOICE", "REQUEST_WEIGHBRIDGE_DATA", "RENEGOTIATE_CONTRACT", "TENDER_OR_SWITCH_OPERATOR"]
SCORECARD_METRICS = ["on_time_rate", "missed_visit_rate", "weighbridge_shared_7d_rate", "median_share_lag_days",
                     "billing_overcharge_pct", "billing_undercharge_pct", "discrepant_line_rate", "weight_bias_pct",
                     "median_order_to_lift_hours"]


def _read(p: Path, cols=None) -> pd.DataFrame:
    return pd.read_parquet(p, columns=cols) if p.exists() else pd.DataFrame(columns=cols or [])


def _local_month(ts: pd.Series, tz: str) -> pd.Series:
    return pd.to_datetime(ts, utc=True).dt.tz_convert(tz).dt.strftime("%Y-%m")


def _period_of_month(month: str, profile: dict) -> str:
    d = pd.Timestamp(month + "-01")
    for name, (a, b) in profile["label_periods"].items():
        if pd.Timestamp(a) <= d < pd.Timestamp(b):
            return name
    return "test"


# ---------------------------------------------------------------------------------------------- Task B2
def operator_scorecard(cfg, out: Path) -> pd.DataFrame:
    tz = cfg.assumptions["timezone"]
    pub, priv = out / "public", out / "private_evaluation"
    ce = _read(pub / "operations" / "collection_events.parquet")
    if ce.empty:
        return pd.DataFrame()
    sites = _read(pub / "reference" / "sites.parquet", ["site_id", "region_code"])
    ce = ce.merge(sites, on="site_id", how="left")
    jobs = ce[ce.status.isin(OPERATOR_STATUSES)].copy()
    jobs["month"] = _local_month(jobs.scheduled_at, tz)
    comp = jobs[jobs.status.isin(COMPLETED)].copy()
    comp["delay_h"] = (comp.actual_at - comp.scheduled_at).dt.total_seconds() / 3600
    comp["on_time"] = comp.delay_h.abs() <= 2.0
    comp["order_to_lift_h"] = (comp.actual_at - comp.order_placed_at).dt.total_seconds() / 3600
    key = ["operator_id", "region_code", "month"]
    g = jobs.groupby(key)
    sc = pd.DataFrame({"n_operator_jobs": g.size(),
                       "missed_visit_rate": g.status.apply(lambda s: float((s == "MISSED_BY_OPERATOR").mean()))})
    gc = comp.groupby(key)
    sc["n_completed_lifts"] = gc.size()
    sc["on_time_rate"] = gc.on_time.mean()
    sc["median_order_to_lift_hours"] = gc.order_to_lift_h.median()
    # weighbridge sharing and weight differences (truth: all tickets, shared or not)
    wb = _read(priv / "truth" / "weighbridge_all.parquet")
    if not wb.empty:
        w = comp[["collection_id"] + key].merge(wb[["collection_id", "shared_with_customer", "arrival_at", "published_at",
                                                    "allocated_net_kg", "true_net_kg"]], on="collection_id", how="left")
        lag = (w.published_at - w.arrival_at).dt.total_seconds() / 86400
        w["shared_7d"] = w.shared_with_customer.fillna(False).astype(bool) & (lag <= 7)
        w["lag_d"] = lag.where(w.shared_with_customer.fillna(False).astype(bool))
        gw = w.groupby(key)
        sc["weighbridge_shared_7d_rate"] = gw.shared_7d.mean()
        sc["median_share_lag_days"] = gw.lag_d.median()
        tk = w.dropna(subset=["allocated_net_kg", "true_net_kg"])
        gt = tk.groupby(key)
        sc["weight_bias_pct"] = 100 * (gt.allocated_net_kg.sum() - gt.true_net_kg.sum()) / gt.true_net_kg.sum().replace(0, np.nan)
    # billing accuracy per billing month
    inv = _read(pub / "finance" / "invoices.parquet", ["invoice_id", "contract_id", "operator_id", "billing_period", "total_eur", "n_lines"])
    ill = _read(priv / "truth" / "invoice_line_labels.parquet")
    ct = _read(pub / "reference" / "contracts.parquet", ["contract_id", "site_id"]).merge(sites, on="site_id")
    if not inv.empty:
        inv = inv.merge(ct[["contract_id", "region_code"]], on="contract_id").rename(columns={"billing_period": "month"})
        ill = ill[ill.invoice_id.isin(inv.invoice_id)].merge(inv[["invoice_id"] + key], on="invoice_id")
        gi = inv.groupby(key)
        billed = gi.total_eur.sum()
        delta = ill.groupby(key).delta_cents.sum() / 100
        over = ill[ill.delta_cents > 0].groupby(key).delta_cents.sum() / 100
        under = -ill[ill.delta_cents < 0].groupby(key).delta_cents.sum() / 100
        expected = billed - delta.reindex(billed.index).fillna(0)
        sc["billing_overcharge_pct"] = 100 * over.reindex(billed.index).fillna(0) / expected.where(expected.abs() > 1)
        sc["billing_undercharge_pct"] = 100 * under.reindex(billed.index).fillna(0) / expected.where(expected.abs() > 1)
        n_lab = ill.groupby(key).size().reindex(billed.index).fillna(0)
        n_missing = ill[ill.invoice_line_id.isna()].groupby(key).size().reindex(billed.index).fillna(0)
        sc["discrepant_line_rate"] = n_lab / (gi.n_lines.sum() + n_missing)
        sc["billed_eur"] = billed
    sc = sc.reset_index()
    sc = sc[sc.n_operator_jobs.fillna(0) > 0].copy()
    for c in SCORECARD_METRICS + ["n_completed_lifts", "billed_eur"]:
        if c not in sc:
            sc[c] = np.nan
    for c in SCORECARD_METRICS:
        sc[c] = sc[c].astype(float).round(4)
    sc["billed_eur"] = sc.billed_eur.astype(float).round(2)
    sc["n_completed_lifts"] = sc.n_completed_lifts.fillna(0).astype("int64")
    # a month is a dev month only if its jobs AND its invoices (issued by the 15th of the next month) lie before the end
    # of the validation period; otherwise its truth would carry test-period information
    val_end = pd.Timestamp(cfg.profile["label_periods"]["validation"][1])
    month_end = pd.to_datetime(sc.month + "-01") + pd.offsets.MonthBegin(1)
    sc["split"] = np.where(month_end + pd.Timedelta(days=15) <= val_end, sc.month.map(lambda m: _period_of_month(m, cfg.profile)), "test")
    cols = ["operator_id", "region_code", "month", "split", "n_operator_jobs", "n_completed_lifts", "billed_eur"] + SCORECARD_METRICS
    return sc[cols].sort_values(["month", "operator_id", "region_code"]).reset_index(drop=True)


# ---------------------------------------------------------------------------------------------- Task C2
def _bucket(v: float) -> str:
    return "S" if v <= 8 else ("M" if v <= 16 else "L")


def _peer_table(cv_last: pd.DataFrame) -> dict:
    """Peer medians of tariff fields for several grouping levels (computed from PUBLIC contract versions)."""
    levels = {"L1": ["region_code", "material_stream", "pricing_model", "bucket"],
              "L2": ["region_code", "material_stream", "pricing_model"],
              "L3": ["material_stream", "pricing_model", "bucket"],
              "L4": ["material_stream", "pricing_model"]}
    fields = FEE_FIELDS + ["credit_share_bp", "free_km"]
    return {lv: (cols, cv_last.groupby(cols)[fields].median(), cv_last.groupby(cols).size()) for lv, cols in levels.items()}


def _peer_version(row: pd.Series, peers: dict, extra_filter=None, min_n: int = 4):
    for lv in ("L1", "L2", "L3", "L4"):
        cols, med, n = peers[lv]
        k = tuple(row[c] for c in cols)
        if k in n.index and n[k] - 1 >= min_n:          # excluding the contract itself
            return med.loc[k], lv
    return None, None


def _reprice(events: pd.DataFrame, version: dict, credit_eligible: bool) -> int:
    tot = 0
    for e in events.itertuples(index=False):
        kg = None if pd.isna(e.billing_mass_kg) else int(e.billing_mass_kg)
        idx = None if pd.isna(e.index_price_eur_per_t) else int(round(e.index_price_eur_per_t * 100))
        grade = None if (e.grade_applied is None or (isinstance(e.grade_applied, float) and np.isnan(e.grade_applied))) else e.grade_applied
        r = price_event(version, e.status, kg, grade, idx, emergency=bool(e.emergency), side_waste=bool(e.side_waste),
                        notice_hours=0.0 if e.cancel_fee else 100.0, credit_eligible=credit_eligible)
        tot += summarize(r["lines"], kg)["invoice_amount_cents"]
    return int(tot)


def _dev_cutoff(cfg) -> pd.Timestamp:
    """Latest month start such that the previous month's invoices (issued by the 15th) fall before the end of the
    validation period: dev labels then never contain information from test-period invoices or collections."""
    val_end = pd.Timestamp(cfg.profile["label_periods"]["validation"][1])
    t = val_end - pd.Timedelta(days=15)
    return pd.Timestamp(year=t.year, month=t.month, day=1)


def operator_actions(cfg, world, split: dict, out: Path, extraction_ms: int):
    A = cfg.assumptions
    OA = A["operator_actions"]
    tz = A["timezone"]
    pub, priv = out / "public", out / "private_evaluation"
    dv = _read(pub / "reference" / "devices.parquet")
    if dv.empty:
        return pd.DataFrame(), pd.DataFrame()
    sites = _read(pub / "reference" / "sites.parquet", ["site_id", "region_code", "customer_id"])
    ct = _read(pub / "reference" / "contracts.parquet")
    cv = _read(pub / "reference" / "contract_versions.parquet")
    mat = _read(pub / "reference" / "material_classes.parquet", ["material_stream", "credit_eligible"])
    ops = A["operators"]
    tb = world.tb
    win_start_local = pd.Timestamp(tb.dates[0])
    win_end_local = pd.Timestamp(tb.dates[-1]) + pd.Timedelta(days=1)
    extraction = pd.Timestamp(extraction_ms, unit="ms", tz="UTC")
    dev_local = _dev_cutoff(cfg)
    dev_ts = dev_local.tz_localize(tz).tz_convert("UTC")
    # reference economics (correct contract charges) for public devices: dev + test parts
    re = pd.concat([_read(pub / "labels_dev" / "reference_economics.parquet"),
                    _read(priv / "labels_test" / "reference_economics.parquet")], ignore_index=True)
    re = re[re.device_id.isin(dv.device_id)].drop_duplicates("collection_id")
    re["service_date"] = pd.to_datetime(re.service_date)
    rcl = pd.concat([_read(pub / "labels_dev" / "reference_charge_lines.parquet"),
                     _read(priv / "labels_test" / "reference_charge_lines.parquet")], ignore_index=True)
    flags = rcl.assign(emergency=rcl.line_type == "EMERGENCY_SURCHARGE", side_waste=rcl.line_type == "SIDE_WASTE_FEE",
                       cancel_fee=rcl.line_type == "CANCELLATION_FEE").groupby("collection_id")[["emergency", "side_waste", "cancel_fee"]].any()
    re = re.merge(flags, left_on="collection_id", right_index=True, how="left").fillna({"emergency": False, "side_waste": False, "cancel_fee": False})
    cv["effective_from"] = pd.to_datetime(cv.effective_from)
    meta = ct[["contract_id", "device_id", "operator_id", "material_stream", "notice_period_days", "site_id"]] \
        .merge(sites[["site_id", "region_code", "customer_id"]], on="site_id") \
        .merge(dv[["device_id", "container_volume_m3", "lifecycle_status", "has_weight_measurement", "active_from"]], on="device_id")
    meta["bucket"] = meta.container_volume_m3.map(_bucket)
    ill_all = _read(priv / "truth" / "invoice_line_labels.parquet")
    inv = _read(pub / "finance" / "invoices.parquet", ["invoice_id", "contract_id", "operator_id", "issued_at", "dispute_status", "total_eur"])
    wb = _read(priv / "truth" / "weighbridge_all.parquet", ["collection_id", "public", "published_at", "allocated_net_kg", "true_net_kg"])
    ce = _read(pub / "operations" / "collection_events.parquet", ["collection_id", "contract_id", "status", "actual_at"])
    ill_all = ill_all.merge(inv[["invoice_id", "contract_id", "operator_id", "issued_at", "dispute_status"]], on="invoice_id")
    ce_ok = mat.set_index("material_stream").credit_eligible.to_dict()
    look = pd.Timedelta(days=int(OA["dispute_lookback_days"]))
    cust_split = {c: ("dev" if rng_for(cfg.seed, "c2split", c).random() < 0.4 else "test") for c in sorted(meta.customer_id.unique())}

    def context(as_of_ts, as_of_local):
        """Everything known (or true) up to the case date."""
        cv_k = cv[cv.effective_from < as_of_local].sort_values("version_no").groupby("contract_id").tail(1)
        cvx = cv_k.merge(meta, on="contract_id")
        inv_k = inv[inv.issued_at <= as_of_ts]
        ill = ill_all[ill_all.issued_at <= as_of_ts]
        billed = inv_k.groupby("operator_id").total_eur.sum()
        delta = ill.groupby("operator_id").delta_cents.sum() / 100
        over = ill[ill.delta_cents > 0].groupby("operator_id").delta_cents.sum() / 100
        expd = billed - delta.reindex(billed.index).fillna(0)
        over_rate = (over.reindex(expd.index).fillna(0) / expd.where(expd > 0)).fillna(0).to_dict()
        ce_k = ce[ce.status.isin(COMPLETED) & (ce.actual_at < as_of_ts)]
        pub_ticket = set(wb[wb.public.astype(bool) & (wb.published_at <= as_of_ts)].collection_id)
        share = ce_k.assign(p=ce_k.collection_id.isin(pub_ticket)).groupby("contract_id").p.mean()
        wbx = wb.merge(ce_k[["collection_id", "contract_id"]], on="collection_id")
        return dict(cvx=cvx, peers=_peer_table(cvx), peers_op={op: _peer_table(cvx[cvx.operator_id == op]) for op in ops},
                    ill=ill, over_rate=over_rate, pub_ticket=pub_ticket, share=share, wbx=wbx,
                    re=re[re.service_date < as_of_local], as_of_ts=as_of_ts, as_of_local=as_of_local)

    ctxs = {"dev": context(dev_ts, dev_local), "test": context(extraction, win_end_local)}
    rows, cases = [], []
    for sp, X in ctxs.items():
        cvx, ill, pub_ticket = X["cvx"], X["ill"], X["pub_ticket"]
        as_of_ts, as_of_local = X["as_of_ts"], X["as_of_local"]
        for r in cvx.itertuples(index=False):
            if cust_split[r.customer_id] != sp or r.lifecycle_status != "ACTIVE":
                continue
            ev = X["re"][X["re"].contract_id == r.contract_id]
            if ev.status.isin(COMPLETED).sum() == 0:
                continue
            cred = bool(ce_ok[r.material_stream])
            own = {c: getattr(r, c) for c in cv.columns if c not in ("effective_from",)}
            own["effective_from"] = r.effective_from
            a_from = pd.Timestamp(r.active_from) if pd.notna(r.active_from) else win_start_local
            days = max(30.0, (as_of_local - max(a_from, win_start_local)).days)
            ann = 365.0 / days
            months_active = days / 30.4375
            base_c = _reprice(ev, own, cred) + int(round(int(own["rental_cents_per_month"]) * months_active))
            # --- DISPUTE_INVOICE: documented overbilling on recent invoices that are not already disputed/credited
            il_c = ill[(ill.contract_id == r.contract_id) & (ill.issued_at > as_of_ts - look)
                       & ~ill.dispute_status.isin(["RESOLVED_CREDIT_NOTE", "OPEN"])]
            rec_c = 0
            for l in il_c.itertuples(index=False):
                t = str(l.discrepancy_type).split(":")[0]
                if t not in RECOVERABLE_TYPES or l.delta_cents <= 0:
                    continue
                if t == "WEIGHT_BASIS_MISMATCH" and not (bool(r.has_weight_measurement) or
                                                         (isinstance(l.collection_id, str) and l.collection_id in pub_ticket)):
                    continue          # no independent evidence for the tonnage claim
                rec_c += int(l.delta_cents)
            v_dispute = OA["dispute_recovery_rate"] * rec_c - OA["dispute_admin_cost_eur"] * 100
            # --- REQUEST_WEIGHBRIDGE_DATA: only when the contract's tickets are mostly not shared
            req_cand = float(X["share"].get(r.contract_id, 0.0)) < 0.8
            v_request = None
            if req_cand:
                rate_t = int(own["haul_fee_cents_per_t"]) + int(own["processing_fee_cents_per_t"])
                w_c = X["wbx"][X["wbx"].contract_id == r.contract_id]
                tare_over = max(0.0, float((w_c.allocated_net_kg - w_c.true_net_kg).sum())) / 1000 * rate_t
                wbm = ill[(ill.contract_id == r.contract_id) & ill.discrepancy_type.str.startswith("WEIGHT_BASIS_MISMATCH") & (ill.delta_cents > 0)]
                wbm_unver = 0 if bool(r.has_weight_measurement) else int(wbm[~wbm.collection_id.isin(pub_ticket)].delta_cents.sum())
                v_request = OA["request_weighbridge_comply_prob"] * (tare_over + wbm_unver) * ann - OA["request_admin_cost_eur"] * 100
            # --- RENEGOTIATE_CONTRACT: the operator agrees to peer-median terms only if the contract is clearly above
            #     its peers (gap >= renegotiation_min_gap_pct of the current cost); otherwise only the effort is spent
            rowd = pd.Series(dict(region_code=r.region_code, material_stream=r.material_stream, pricing_model=own["pricing_model"], bucket=r.bucket))
            peer, lvl = _peer_version(rowd, X["peers"])
            v_reneg = reneg_c = None
            if peer is not None:
                nv = dict(own)
                for f in FEE_FIELDS:
                    nv[f] = int(round(peer[f]))
                nv["credit_share_bp"] = int(round(peer["credit_share_bp"] / 100) * 100) if cred else 0
                reneg_c = _reprice(ev, nv, cred) + int(round(int(nv["rental_cents_per_month"]) * months_active))
                gap = base_c - reneg_c
                ok = base_c > 0 and gap >= OA["renegotiation_min_gap_pct"] / 100 * base_c
                v_reneg = (OA["renegotiation_success_prob"] * gap * ann if ok else 0.0) - OA["renegotiation_effort_eur"] * 100
            # --- TENDER_OR_SWITCH_OPERATOR: best alternative operator serving the region (its typical terms and its
            #     billing accuracy); the benefit starts after the notice period
            best_t = best_op = None
            months_benefit = max(0.0, OA["valuation_horizon_months"] - int(r.notice_period_days) / 30.4375)
            for op, o in ops.items():
                if op == r.operator_id or r.region_code not in o["regions"]:
                    continue
                pv, _ = _peer_version(rowd, X["peers_op"][op], min_n=2)
                if pv is None:
                    continue
                av = dict(own)
                for f in FEE_FIELDS + ["free_km"]:
                    av[f] = int(round(pv[f]))
                av["credit_share_bp"] = int(round(pv["credit_share_bp"] / 100) * 100) if cred else 0
                alt_c = _reprice(ev, av, cred) + int(round(int(av["rental_cents_per_month"]) * months_active))
                cur_tot = base_c * (1 + X["over_rate"].get(r.operator_id, 0.0))
                alt_tot = alt_c * (1 + X["over_rate"].get(op, 0.0))
                gap_t = cur_tot - alt_tot
                ok_t = cur_tot > 0 and gap_t >= OA["tender_min_gap_pct"] / 100 * cur_tot
                v = (OA["tender_success_prob"] * gap_t * ann * months_benefit / 12 if ok_t else 0.0) - OA["tender_switch_cost_eur"] * 100
                if best_t is None or v > best_t:
                    best_t, best_op = v, op
            case_id = f"OC-{r.contract_id[4:]}"
            cands = ["DISPUTE_INVOICE"] + (["REQUEST_WEIGHBRIDGE_DATA"] if req_cand else []) + \
                    (["RENEGOTIATE_CONTRACT"] if v_reneg is not None else []) + (["TENDER_OR_SWITCH_OPERATOR"] if best_t is not None else [])
            cases.append({"case_id": case_id, "contract_id": r.contract_id, "device_id": r.device_id, "customer_id": r.customer_id,
                          "operator_id": r.operator_id, "region_code": r.region_code, "as_of_ms": int(as_of_ts.value // 10 ** 6),
                          "split": sp, "candidate_actions": ",".join(cands), "notice_period_days": int(r.notice_period_days)})
            vals = {"DISPUTE_INVOICE": v_dispute, "REQUEST_WEIGHBRIDGE_DATA": v_request, "RENEGOTIATE_CONTRACT": v_reneg,
                    "TENDER_OR_SWITCH_OPERATOR": best_t}
            best_set = max(0.0, v_dispute) + max(0.0, v_request or 0.0) + max(0.0, v_reneg or 0.0, best_t or 0.0)
            for a in C2_ACTIONS:
                v = vals[a]
                if v is None:
                    continue
                rows.append({"case_id": case_id, "split": sp, "action": a, "value_eur": round(v / 100, 2), "positive": bool(v > 0),
                             "annual_contract_cost_eur": round(base_c * ann / 100, 2),
                             "recoverable_overbilling_eur": round(rec_c / 100, 2) if a == "DISPUTE_INVOICE" else None,
                             "renegotiated_annual_cost_eur": round(reneg_c * ann / 100, 2) if (a == "RENEGOTIATE_CONTRACT" and reneg_c is not None) else None,
                             "peer_level": lvl if a == "RENEGOTIATE_CONTRACT" else None,
                             "best_alternative_operator": best_op if a == "TENDER_OR_SWITCH_OPERATOR" else None,
                             "best_set_value_eur": round(best_set / 100, 2)})
    return pd.DataFrame(cases), pd.DataFrame(rows)


def write_all(cfg, world, split: dict, out: Path, extraction_ms: int) -> dict:
    """Compute B2 + C2 truth from the finished public/private outputs and write the tables."""
    pub, priv = out / "public", out / "private_evaluation"
    counts = {}
    sc = operator_scorecard(cfg, out)
    if not sc.empty:
        for sp, where, base in (("dev", sc.split.isin(["train", "validation"]), pub / "labels_dev"),
                                ("test", sc.split == "test", priv / "labels_test")):
            part = sc[where].reset_index(drop=True)
            write_parquet(part, base / "operator_scorecard.parquet")
            counts[str((base / "operator_scorecard.parquet").relative_to(out))] = len(part)
        keys = sc[sc.split == "test"][["operator_id", "region_code", "month", "n_operator_jobs"]].reset_index(drop=True)
        write_parquet(keys, pub / "benchmark" / "task_b2_scorecard_rows.parquet")
        counts["public/benchmark/task_b2_scorecard_rows.parquet"] = len(keys)
    cases, vals = operator_actions(cfg, world, split, out, extraction_ms)
    if not cases.empty:
        cases["as_of_at"] = pd.to_datetime(cases.pop("as_of_ms"), unit="ms", utc=True)
        write_parquet(cases, pub / "benchmark" / "operator_action_cases.parquet")
        counts["public/benchmark/operator_action_cases.parquet"] = len(cases)
        for sp, base in (("dev", pub / "labels_dev"), ("test", priv / "labels_test")):
            part = vals[vals.split == sp].reset_index(drop=True)
            write_parquet(part, base / "operator_action_values.parquet")
            counts[str((base / "operator_action_values.parquet").relative_to(out))] = len(part)
    return counts
