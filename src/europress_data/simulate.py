"""Stateful, event-driven device simulation.

For each compactor we simulate, hour by hour:
  material inflow  ->  compacted volume / mass in container  ->  collection policy decisions
  ->  collection events (delays, cancellations, partial lifts, wasted trips)  ->  state resets.
Sensor and connectivity models are generated up-front so that the *observed* fill/mass used by
fill- or weight-triggered policies is exactly what appears in the published telemetry.

The physical truth is mass-conserving:
  sum(inflow) == sum(collected) + sum(side collected) + end container mass + end side stock
(validated in validate.py and tests).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np

from .economics import grade_from_contamination, price_event, summarize
from .rng import rng_for

RETAIL = ("grocery_retail", "nonfood_retail", "shopping_center")
FREQ_OPTIONS = [5.0, 3.0, 2.0, 1.0, 0.5, 0.25]
LEGIT_EARLY_TRIGGERS = ("MAX_INTERVAL_RULE", "CUSTOMER_REQUEST_PRE_CLOSURE", "DECOMMISSION", "CUSTOMER_REQUEST")


def hour_profile(sector: str) -> np.ndarray:
    h = np.arange(24)
    if sector in RETAIL:
        w = np.where((h >= 7) & (h < 12), 2.0, np.where((h >= 12) & (h < 17), 1.2, 0.7))
    elif sector == "hospitality_hotel":
        w = np.full(24, 0.25)
        w[7:10] = 1.3
        w[11:14] = 1.6
        w[17:21] = 1.6
    elif sector == "office_services":
        w = np.where((h >= 8) & (h < 16), 1.0, 0.3)
    else:
        w = np.where((h >= 10) & (h < 14), 1.2, 1.0)
    return w.astype(float)


@dataclass
class Ctx:
    tb: object
    A: dict
    seed: int
    profile: dict
    site_open: dict
    weather: dict
    versions: dict          # contract_id -> list of version dicts (sorted)
    index_cents: dict       # (index_id, 'YYYY-MM') -> cents/t
    month_key_d: np.ndarray
    closures: dict = field(default_factory=dict)   # site_id -> list of (start_day, end_day, reason)


# ----------------------------------------------------------------------------------------------
# Preparation of exogenous hourly arrays
# ----------------------------------------------------------------------------------------------

def prepare(spec: dict, ctx: Ctx) -> dict:
    tb = ctx.tb
    A = ctx.A
    N, nd = tb.n_hours, tb.n_days
    dev = spec["device_id"]
    ep = spec["episodes"]
    rin = rng_for(ctx.seed, "inflow", dev)
    open_d, oh, ch, reason, activity = ctx.site_open[spec["site_id"]]
    a0, a1 = spec["act_from_day"], spec["act_to_day"]

    season = np.array(spec["season"])[tb.month_d - 1]
    wk = np.array(spec["weekday"])[tb.weekday_d]
    s = spec["lsig"] * 0.45
    eps = rin.normal(0, 1, nd)
    ar = np.empty(nd)
    phi = 0.55
    ar[0] = eps[0] * s
    k = np.sqrt(1 - phi ** 2) * s
    for i in range(1, nd):
        ar[i] = phi * ar[i - 1] + k * eps[i]
    daily = spec["daily_kg"] * season * wk * activity * np.exp(ar - s * s / 2)
    sector = spec["sector"]
    for i, d in enumerate(tb.dates):
        if sector in RETAIL and d.month == 12 and 17 <= d.day <= 23:
            daily[i] *= 1.35
        if sector in RETAIL and d.month == 12 and 27 <= d.day <= 31:
            daily[i] *= 1.25
        if sector == "grocery_retail" and i + 1 < nd and tb.holiday_d[i + 1]:
            daily[i] *= 1.2
    for d0, d1, mult in ep["campaigns"]:
        daily[d0:d1] *= mult
    daily[~open_d] = 0.0
    daily[:a0] = 0.0
    daily[a1:] = 0.0

    prof = hour_profile(sector)
    hl = tb.hour_local.astype(int)
    di = tb.day_idx
    in_hours = (hl >= oh[di]) & (hl < ch[di]) & open_d[di]
    w = np.where(in_hours, prof[hl], 0.0)
    daysum = np.bincount(di, weights=w, minlength=nd)
    mu = np.where(daysum[di] > 0, daily[di] * w / np.maximum(daysum[di], 1e-9), 0.0)
    ev_kg = spec["input_event_kg"]
    n_ev = rin.poisson(mu / ev_kg)
    dry = np.where(n_ev > 0, rin.gamma(np.maximum(n_ev * 3, 1), ev_kg / 3.0), 0.0)

    # moisture (S28)
    extra_d = np.zeros(nd)
    if spec["moisture_sensitive"] and spec["outdoor"]:
        extra_d = np.minimum(0.35, 0.015 * ctx.weather[spec["region"]])
    water = dry * extra_d[di]
    inflow = dry + water

    # density
    m = A["materials"]
    rho_d = spec["density"] * np.exp(rin.normal(0, spec["daily_density_cv"], nd)) * (1 + 0.6 * extra_d)
    if spec["misalloc_share"] > 0:
        sh = spec["misalloc_share"]
        rho_cb = m["cardboard"]["compacted_density"]
        rho_d = 1.0 / ((1 - sh) / rho_d + sh / rho_cb)
    if ep["density_shift"] is not None:
        d0, kind, mult = ep["density_shift"]
        rho_d[d0:] *= mult
    rho = rho_d[di]

    # contamination (recyclables) — share of non-target material in the load
    contam_d = np.zeros(nd)
    if spec["credit_eligible"]:
        contam_d = spec["contam_base"] * np.exp(rin.normal(0, 0.35, nd))
        for d0, d1, add in ep["contam_incidents"]:
            contam_d[d0:d1] += add
        if spec["material"] in ("cardboard", "paper"):
            contam_d += 0.3 * extra_d
        contam_d = np.clip(contam_d, 0, 0.6)
    contam = contam_d[di]

    active = (di >= a0) & (di < a1)

    # ---------------- maintenance and sensor episodes ----------------
    rm = rng_for(ctx.seed, "maintenance", dev)
    down = np.zeros(N, dtype=bool)
    wos = []
    wo_n = [0]

    def add_wo(kind, start_h, dur_h, desc, downtime=True):
        wo_n[0] += 1
        start_h = int(min(max(start_h, 0), N - 1))
        end_h = int(min(N - 1, start_h + max(1, int(round(dur_h)))))
        if downtime:
            down[start_h:end_h] = True
        rep = start_h - (int(rm.integers(1, 30)) if kind == "PREVENTIVE" else 0)
        if kind == "CORRECTIVE":
            rep = start_h + int(rm.integers(0, 6))
        wos.append({"work_order_id": f"WO-{dev[4:]}-{wo_n[0]:03d}", "device_id": dev, "work_order_type": kind,
                    "reported_h": max(0, min(rep, N - 1)), "start_h": start_h, "end_h": end_h,
                    "downtime_hours": float(end_h - start_h) if downtime else 0.0, "description_code": desc})
        return start_h

    def biz_hour_on_or_after(d):
        d = int(min(max(d, 0), nd - 1))
        while d < nd - 1 and not tb.business_d[d]:
            d += 1
        return int(tb.day_start_h[d] + int(rm.integers(8, 14)))

    # preventive every ~182 days
    first = int(rm.integers(10, 182))
    pm_hours = []
    d = max(first, a0 + 5)
    while d < a1 - 1:
        pm_hours.append(add_wo("PREVENTIVE", biz_hour_on_or_after(d), rm.uniform(2, 4), "PM_INSPECTION_LUBRICATION"))
        d += int(rm.integers(160, 200))
    for st, dur in ep["breakdowns"]:
        if a0 * 24 <= st < a1 * 24:
            add_wo("CORRECTIVE", st, dur, str(rm.choice(["HYDRAULIC_LEAK", "PRESS_JAM", "ELECTRICAL_FAULT", "DOOR_INTERLOCK"])))
    if ep["density_shift"] is not None and ep["density_shift"][1] == "CONFIG_CHANGE":
        add_wo("CONFIG_CHANGE", biz_hour_on_or_after(ep["density_shift"][0]) - 4, 1, "COMPACTION_FORCE_SETTING_INCREASED")

    # sensor model
    rs = rng_for(ctx.seed, "sensor", dev)
    g0 = 1 + rs.normal(0, 0.004)          # installation calibration (normal state; total error ~1.5 % with noise)
    o0 = rs.normal(0, 6)
    gain = np.full(N, g0)
    offset = np.full(N, o0)
    status = np.zeros(N, dtype=np.int8)        # 0 OK, 1 DEGRADED, 2 FAULT, 3 NO SENSOR
    sensor_idx = np.zeros(N, dtype=np.int8)
    sens_events = []
    if not spec["has_weight_sensor"]:
        status[:] = 3
    else:
        hours_day = np.arange(N) / 24.0
        repl_h = None
        if ep["replacement"] is not None:
            d0, fault_days, gn, on = ep["replacement"]
            repl_h = biz_hour_on_or_after(d0)
        if ep["drift"] is not None:
            d0, d1, rate = ep["drift"]
            s_h = int(tb.day_start_h[min(d0, nd - 1)])
            e_h = biz_hour_on_or_after(d1) if d1 is not None else N
            if repl_h is not None and s_h < repl_h:
                e_h = min(e_h, repl_h)
            if e_h > s_h:
                f = np.clip(1 + rate * (hours_day[s_h:e_h] - hours_day[s_h]), 0.65, 1.35)
                gain[s_h:e_h] *= f
                sens_events.append(("DRIFT", s_h, e_h, rate))
                if d1 is not None and e_h < N and (repl_h is None or e_h < repl_h):
                    add_wo("SENSOR_RECALIBRATION", e_h, 1, "WEIGHT_RECALIBRATION", downtime=False)
        if ep["calib_error"] is not None:
            d0, d1, kind, val = ep["calib_error"]
            cands = [h for h in pm_hours if h >= tb.day_start_h[min(d0, nd - 1)]]
            s_h = cands[0] if cands else add_wo("PREVENTIVE", biz_hour_on_or_after(d0), 2, "PM_INSPECTION_LUBRICATION")
            e_h = biz_hour_on_or_after(d1) if d1 is not None else N
            if repl_h is not None and s_h < repl_h:
                e_h = min(e_h, repl_h)
            if e_h > s_h:
                if kind == "OFFSET":
                    offset[s_h:e_h] += val
                else:
                    gain[s_h:e_h] *= val
                sens_events.append(("CALIBRATION_" + kind, s_h, e_h, val))
                if d1 is not None and e_h < N and (repl_h is None or e_h < repl_h):
                    add_wo("SENSOR_RECALIBRATION", e_h, 1, "WEIGHT_RECALIBRATION", downtime=False)
        if repl_h is not None:
            d0, fault_days, gn, on = ep["replacement"]
            if fault_days:
                fs = max(0, repl_h - fault_days * 24)
                status[fs:repl_h] = 2
                sens_events.append(("FAULT_BEFORE_REPLACEMENT", fs, repl_h, fault_days))
            gain[repl_h:] = 1 + gn
            offset[repl_h:] = on
            sensor_idx[repl_h:] = 1
            add_wo("SENSOR_REPLACEMENT", repl_h, 2, "WEIGHT_SENSOR_REPLACED")
            sens_events.append(("REPLACEMENT", repl_h, repl_h + 1, 0))
        for st, dur in ep["offline"]:
            st = int(min(st, N - 1))
            en = int(min(N, st + dur))
            status[st:en] = np.maximum(status[st:en], 2)
            sens_events.append(("FAULT", st, en, dur))
        for d0, d1 in ep["degraded"]:
            s_h, e_h = int(tb.day_start_h[min(d0, nd - 1)]), int(tb.day_start_h[min(d1, nd - 1)])
            status[s_h:e_h] = np.where(status[s_h:e_h] == 0, 1, status[s_h:e_h])
            sens_events.append(("DEGRADED", s_h, e_h, 3.0))
    # routine recalibration at clean times (no active episode)
    if spec["has_weight_sensor"] and rm.random() < 0.25:
        h = biz_hour_on_or_after(int(rm.integers(a0 + 5, max(a0 + 6, a1 - 5))))
        if not any(e[1] <= h < e[2] for e in sens_events):
            add_wo("SENSOR_RECALIBRATION", h, 1, "WEIGHT_RECALIBRATION", downtime=False)

    # connectivity
    T = A["telemetry"]
    rt = rng_for(ctx.seed, "telemetry", dev)
    online = np.ones(N, dtype=bool)
    outages = []
    n_out = rt.poisson(T["outage_rate_per_30d"] * nd / 30)
    for _ in range(n_out):
        st = int(rt.integers(0, N))
        dur = int(min(24 * 14, max(1, rt.lognormal(np.log(T["outage_median_h"]), T["outage_sigma"]))))
        en = min(N, st + dur)
        online[st:en] = False
        outages.append((st, en, bool(rt.random() < T["buffered_delivery_prob"])))
    fz = rt.normal(0, 1, N)
    fill_z = np.empty(N)
    fill_z[0] = fz[0]
    for i in range(1, N):
        fill_z[i] = 0.6 * fill_z[i - 1] + 0.8 * fz[i]
    fill_z *= T["fill_sigma_pp"]
    # fill-estimate systematics (device level): material spring-back bias, gain error, rare miscalibration
    mat_bias = {"plastic_film": 5.0, "mixed_plastic": 4.0, "cardboard": 1.0, "paper": -1.0, "mixed_waste": -2.0, "biowaste": -4.0}
    fill_bias = mat_bias.get(spec["material"], 0.0) + rt.normal(0, T.get("fill_bias_sd_pp", 4.0))
    fill_gain = 1.0 + rt.normal(0, T.get("fill_gain_sd", 0.07))
    if rt.random() < 0.05:
        fill_gain *= float(rt.choice([0.8, 1.2]))
    mass_z = rt.normal(0, 1, N)
    fill_floor = np.zeros(N)
    for (d0, d1, lvl) in spec["episodes"].get("fill_false_high", []):
        fill_floor[int(tb.day_start_h[min(d0, tb.n_days - 1)]):int(tb.day_start_h[min(d1, tb.n_days - 1)])] = lvl

    return dict(inflow=inflow, water=water, n_ev=n_ev, rho=rho, contam=contam, active=active, down=down,
                gain=gain, offset=offset, status=status, sensor_idx=sensor_idx, online=online, outages=outages,
                fill_z=fill_z, fill_bias=float(fill_bias), fill_gain=float(fill_gain), fill_floor=fill_floor, mass_z=mass_z, work_orders=wos, sensor_events=sens_events, open_d=open_d,
                reason_d=reason, extra_d=extra_d, daily=daily, rt=rt)


def obs_fill_values(fill_true: np.ndarray, sl: slice, arr: dict) -> np.ndarray:
    """Assumed fill-level estimate: gain/bias systematics + correlated noise, saturating at 0..100."""
    v = np.clip(fill_true * arr["fill_gain"] + arr["fill_bias"] * np.minimum(1.0, fill_true / 20.0) + arr["fill_z"][sl], 0, 100)
    ff = arr.get("fill_floor")
    return v if ff is None else np.maximum(v, ff[sl])          # S40 false-high fill estimate


def obs_mass(m_true: np.ndarray, sl: slice, arr: dict, A: dict) -> np.ndarray:
    T = A["telemetry"]
    g = arr["gain"][sl]
    o = arr["offset"][sl]
    st = arr["status"][sl]
    sig = np.maximum(T["mass_sigma_abs_kg"], T["mass_sigma_rel"] * m_true) * np.where(st == 1, 3.0, 1.0)
    v = m_true * g + o + sig * arr["mass_z"][sl]
    res = T["mass_resolution_kg"]
    v = np.round(v / res) * res
    return np.where(st >= 2, np.nan, v)


# ----------------------------------------------------------------------------------------------
# Policy engine
# ----------------------------------------------------------------------------------------------

def fixed_slots(tb, policy: dict, a0: int, a1: int, rng) -> np.ndarray:
    wd = set(policy["weekdays"])
    freq = policy["freq_per_week"]
    par = policy["week_parity"]
    out = []
    nd = tb.n_days
    for d in range(max(0, a0), min(a1, nd)):
        if tb.weekday_d[d] not in wd:
            continue
        wkno = int(tb.isoweek_d[d])
        if freq == 0.5 and (wkno + par) % 2:
            continue
        if freq == 0.25 and (wkno + par) % 4:
            continue
        dd = d
        while dd < nd - 1 and tb.holiday_d[dd]:
            dd += 1
        out.append(int(tb.day_start_h[dd] + policy["route_hour"] + rng.integers(-1, 2, "slot", dd)))
    return np.unique(np.array(out, dtype=np.int64))


def operator_slot(tb, order_h: int, lead_days: int, rng) -> int:
    N = tb.n_hours
    if order_h >= N:
        return N + 1
    d = int(tb.day_idx[order_h]) + int(lead_days) + (1 if int(tb.hour_local[order_h]) >= 12 else 0)
    nd = tb.n_days
    while True:
        while d < nd and not tb.business_d[d]:
            d += 1
        if d >= nd:
            return N + 1
        t = int(tb.day_start_h[d] + rng.integers(7, 15, "opslot", order_h, lead_days, d))
        if t >= order_h + 2:          # never scheduled before (or right at) the order
            return t
        d += 1


def vol_from_W(W, C, c):
    return C / c * (np.sqrt(1 + 2 * c * W / C) - 1)


def W_from_vol(V, C, c):
    return V + c * V * V / (2 * C)


def _delay_hours(rng, ops, boosted: bool, ts: int, on_time_factor: float = 1.0) -> float:
    dm = ops["delay_mix"]
    p = np.array([dm["on_time"][0], dm["late_hours"][0], dm["next_day"][0], dm["multi_day"][0]])
    if boosted:
        p = np.array([0.40, 0.25, 0.23, 0.12])
    # operator-specific punctuality (fictional operators differ; needed for the scorecard task)
    p0 = min(0.95, p[0] * on_time_factor)
    p = np.concatenate([[p0], p[1:] / p[1:].sum() * (1 - p0)])
    p = p / p.sum()
    k = rng.choice_p(p, "delay_k", ts)
    lo, hi = [dm["on_time"], dm["late_hours"], dm["next_day"], dm["multi_day"]][k][1:]
    return float(rng.uniform(lo, hi, "delay", ts))


def run_policy(spec: dict, arr: dict, ctx: Ctx, policy: dict, h0: int, h1: int, init: dict, rng,
               overrides: dict | None = None, record_arrays: bool = True) -> dict:
    """Simulate container state and collection events from hour h0 to h1 (exclusive)."""
    tb, A = ctx.tb, ctx.A
    ops = A["operations"]
    op_cfg = A["operators"].get(spec["operator_id"], {})
    N = tb.n_hours
    C = spec["volume_m3"]
    c = spec["compressibility"]
    Wcap = W_from_vol(C, C, c)
    ov = overrides or {}
    inflow_all = arr["inflow"]
    water_all = arr["water"]
    rho_all = arr["rho"]
    contam_all = ov.get("contam", arr["contam"])
    downm = arr["down"] | ~arr["active"]
    a0h = int(tb.day_start_h[min(spec["act_from_day"], tb.n_days - 1)])
    a1h = N if spec["act_to_day"] >= tb.n_days else int(tb.day_start_h[spec["act_to_day"]])
    h0 = max(h0, a0h)
    h1 = min(h1, a1h)
    L = max(0, h1 - h0)
    m_true = np.zeros(L)
    fill_true = np.zeros(L)
    side_stock = np.zeros(L)
    cont_kg = np.zeros(L)
    water_kg = np.zeros(L)
    full_flag = np.zeros(L, dtype=bool)
    events = []
    ptype = policy["type"]
    slots = fixed_slots(tb, policy, spec["act_from_day"], spec["act_to_day"], rng) if ptype in ("FIXED_SCHEDULE", "HYBRID") else np.array([], dtype=np.int64)
    ep = spec["episodes"]
    delay_ep = ep.get("delay_episode")
    closures = ctx.closures.get(spec["site_id"], [])
    pre_closure = {}
    for (cs, ce, why) in closures:
        if ce - cs >= 4:
            pre_closure[cs] = bool(rng.random("preclose", cs) < 0.6)
    closure_cancel = {(cs, ce): bool(rng.random("closecancel", cs) < 0.55) for (cs, ce, why) in closures}
    cust_req = sorted(int(tb.day_start_h[min(d, tb.n_days - 1)] + 9) for d in ep.get("customer_requests", []))
    # S39: precautionary customer orders on on-call devices (before weekends / holidays), evaluated at 10:00 local
    prec_req = sorted(int(tb.day_start_h[min(d, tb.n_days - 1)] + 10) for d in ep.get("precautionary_days", []))

    Rm, Rw = float(init.get("Rm", 0.0)), float(init.get("Rw", 0.0))
    Rc, Rwater = float(init.get("Rc", 0.0)), float(init.get("Rwater", 0.0))
    side = float(init.get("side", 0.0))
    last_coll = int(init.get("last_coll", h0))
    cursor = h0
    pending = None          # dict(order_h, sched_h, trigger)
    forced = []             # list of dicts (sched_h, trigger, order_h, notice)
    used_req = set()
    used_pre = set()
    decom_done = spec["act_to_day"] >= tb.n_days or not ov.get("allow_decommission", True)
    adhoc_done = False
    h = h0
    seq = int(init.get("seq", 0))
    max_days = spec["max_days"]
    thr = policy.get("threshold_pct", 85.0)
    mass_target = policy.get("mass_target_kg")
    window = 60 * 24
    while h < h1:
        e = min(h1, h + window)
        sl = slice(h, e)
        dn = downm[sl]
        inc = inflow_all[sl]
        to_c = np.where(dn, 0.0, inc)
        to_side = np.where(dn, inc, 0.0)
        dW = to_c / rho_all[sl]
        cumW = Rw + np.cumsum(dW)
        cumM = Rm + np.cumsum(to_c)
        cumC = Rc + np.cumsum(to_c * contam_all[sl])
        cumH2O = Rwater + np.cumsum(np.where(dn, 0.0, water_all[sl]))
        over = np.zeros(e - h)
        fullidx = None
        hit = np.nonzero(cumW >= Wcap)[0]
        if hit.size:
            j = int(hit[0])
            fullidx = j
            prevW = Rw if j == 0 else cumW[j - 1]
            prevM = Rm if j == 0 else cumM[j - 1]
            prevC = Rc if j == 0 else cumC[j - 1]
            prevH = Rwater if j == 0 else cumH2O[j - 1]
            frac = float(np.clip((Wcap - prevW) / dW[j], 0, 1)) if dW[j] > 0 else 0.0
            mfull = prevM + frac * to_c[j]
            over[j] = (1 - frac) * to_c[j]
            over[j + 1:] = to_c[j + 1:]
            share_c = contam_all[h + j]
            cfull = prevC + frac * to_c[j] * share_c
            hfull = prevH + frac * (water_all[h + j] if not dn[j] else 0.0)
            cumM[j:] = mfull
            cumW[j:] = Wcap
            cumC[j:] = cfull
            cumH2O[j:] = hfull
        V = vol_from_W(cumW, C, c)
        fill = np.minimum(100.0, 100.0 * V / C)
        side_cum = side + np.cumsum(to_side + over)
        obs_fill = obs_fill_values(fill, sl, arr)
        onl = arr["online"][sl]

        # --------- candidate loop until a completion inside [h, e) ----------
        state_snapshot = (cursor, None if pending is None else dict(pending), [dict(f) for f in forced],
                          set(used_req), set(used_pre), decom_done, seq, adhoc_done, last_coll)
        new_events = []
        completed = None
        need_extend = False
        while True:
            cands = []
            if ptype in ("FIXED_SCHEDULE", "HYBRID"):
                k = int(np.searchsorted(slots, cursor))
                if k < len(slots):
                    cands.append({"sched_h": int(slots[k]), "trigger": "SCHEDULED", "order_h": None, "kind": "slot"})
            if ptype in ("ON_CALL", "MASS_TRIGGER"):
                if pending is None:
                    st_i = max(cursor, h) - h
                    if st_i < e - h:
                        if ptype == "ON_CALL":
                            trig = (obs_fill[st_i:] >= thr) & onl[st_i:]
                        else:
                            om = obs_mass(cumM[st_i:], slice(h + st_i, e), arr, A)
                            trig = (((om >= mass_target) | (np.isnan(om) & (obs_fill[st_i:] >= 90))) & onl[st_i:])
                        maxd = (np.arange(h + st_i, e) - last_coll) >= (max_days - 1.5) * 24
                        tt = np.nonzero(trig | maxd)[0]
                        if tt.size:
                            i = int(tt[0]) + st_i
                            why = "ON_CALL_ORDER" if trig[i - st_i] else "MAX_INTERVAL_RULE"
                            if ptype == "MASS_TRIGGER" and why == "ON_CALL_ORDER":
                                why = "MASS_TARGET_ORDER"
                            lead = int(rng.poisson(A["policies"]["lead_business_days_mean"], "lead", h + i))
                            pending = {"order_h": h + i, "sched_h": operator_slot(tb, h + i, lead, rng), "trigger": why,
                                       "kind": "pending"}
                if pending is not None:
                    cands.append(pending)
            for f in forced:
                cands.append(f)
            # ad-hoc customer call after the container has been full for a while
            if fullidx is not None and not adhoc_done:
                order = h + fullidx + int(policy.get("adhoc_after_full_h", 18))
                if order < e and order >= cursor:
                    cands.append({"sched_h": order + rng.integers(4, 25, "adhoc", order), "trigger": "AD_HOC_CUSTOMER",
                                  "order_h": order, "kind": "adhoc"})
            # pre-closure customer request
            for cs, want in pre_closure.items():
                if not want or cs in used_pre:
                    continue
                d_last = cs - 1
                if d_last < 0:
                    continue
                t = int(tb.day_start_h[d_last] + 10)
                if h <= t < e and t >= cursor:
                    ii = t - h
                    if fill[max(ii - 1, 0)] >= 25:
                        cands.append({"sched_h": t, "trigger": "CUSTOMER_REQUEST_PRE_CLOSURE", "order_h": t - 30,
                                      "kind": "pre", "key": cs})
                    break
            for t in cust_req:
                if t in used_req:
                    continue
                if h <= t < e and t >= cursor:
                    cands.append({"sched_h": t, "trigger": "CUSTOMER_REQUEST", "order_h": t - 20, "kind": "req", "key": t})
                    break
            if ptype in ("ON_CALL", "MASS_TRIGGER"):
                # the customer sees a moderately full container in the app and orders "to be safe" before a
                # weekend/holiday, although the trigger has not fired (over-servicing on on-call devices)
                for t in prec_req:
                    if t in used_req or t < cursor or not (h <= t < e):
                        continue
                    if pending is not None and pending["order_h"] <= t:
                        break
                    jj = t - h
                    if onl[jj] and 15.0 <= obs_fill[jj] < thr - 5.0:
                        cands.append({"sched_h": t + 4, "trigger": "CUSTOMER_PRECAUTIONARY", "order_h": t, "kind": "req", "key": t})
                        break
            if not decom_done:
                t = a1h - 14
                if t >= cursor:
                    cands.append({"sched_h": max(t, h), "trigger": "DECOMMISSION", "order_h": t - 72, "kind": "decom"})
            if not cands:
                break
            cand = min(cands, key=lambda x: x["sched_h"])
            ts = int(cand["sched_h"])
            if ts >= e:
                if e < h1:
                    need_extend = True
                break
            # consume candidate
            kind = cand["kind"]
            if kind == "pending":
                pass
            elif kind == "pre":
                used_pre.add(cand["key"])
            elif kind == "req":
                used_req.add(cand["key"])
            elif kind == "decom":
                decom_done = True
            elif kind == "adhoc":
                adhoc_done = True
            elif kind == "forced":
                forced.remove(cand)
            seq += 1
            ev = {"seq": seq, "trigger": cand["trigger"], "order_h": cand["order_h"], "sched_h": ts,
                  "actual_h": None, "status": None, "notice_h": None, "delay_h": None, "orig_trigger": cand.get("orig")}
            dday = int(tb.day_idx[min(ts, N - 1)])
            site_closed_reason = arr["reason_d"][dday]
            boosted = delay_ep is not None and delay_ep[0] <= dday < delay_ep[1]
            ii = ts - h
            status = None
            if cand["trigger"] == "SCHEDULED":
                if site_closed_reason in ("PLANNED_CLOSURE", "SUMMER_SHUTDOWN"):
                    key = next(((cs, ce) for (cs, ce, why) in closures if cs <= dday < ce), None)
                    if key is not None and closure_cancel.get(key, False):
                        status, ev["notice_h"] = "CANCELLED_BY_CUSTOMER", 72.0
                if status is None and ptype == "HYBRID":
                    jj = ii - 26                       # decision ~26 h before the slot, on data visible then
                    if jj >= 0 and onl[jj] and obs_fill[jj] < policy["skip_below_pct"] and (ts - last_coll) < (max_days - 2) * 24:
                        status, ev["notice_h"] = "SKIPPED_LOW_FILL", 26.0
                if status is None and rng.random("cancel", ts) < ops["random_cancel_prob"]:
                    status, ev["notice_h"] = "CANCELLED_BY_CUSTOMER", float(rng.uniform(2, 72, "notice", ts))
            if status is None:
                u = rng.random("status", ts)
                pmiss = ops["missed_prob"] * (3 if boosted else 1) * op_cfg.get("missed_factor", 1.0)
                if u < pmiss:
                    status = "MISSED_BY_OPERATOR"
                elif u < pmiss + ops["wasted_trip_prob"]:
                    status = "WASTED_TRIP"
            if status in ("MISSED_BY_OPERATOR", "WASTED_TRIP"):
                ev["status"] = status
                if status == "WASTED_TRIP":
                    ev["actual_h"] = ts
                nxt = operator_slot(tb, ts, 1, rng)
                if kind == "pending":
                    pending["sched_h"] = nxt
                    pending["trigger"] = pending["trigger"]
                else:
                    forced.append({"sched_h": nxt, "trigger": "RESCHEDULED", "order_h": ts, "kind": "forced",
                                   "orig": cand.get("orig") or cand["trigger"]})
                if kind == "slot":
                    cursor = max(cursor, ts + 1)
                new_events.append(ev)
                continue
            if status is not None:      # cancelled / skipped
                ev["status"] = status
                new_events.append(ev)
                cursor = ts + 1
                continue
            # executes: actual time with delay
            dl = _delay_hours(rng, ops, boosted, ts, op_cfg.get("on_time_factor", 1.0))
            act = int(round(ts + dl))
            lh = int(tb.hour_local[min(act, N - 1)])
            if lh < 5:
                act += 7 - lh
            elif lh > 20:
                act += 24 - lh + 7
            act = max(act, h, (cand["order_h"] or h) + 1)
            if act >= e:
                if e < h1:
                    need_extend = True
                    break
                # executes beyond the simulation horizon: not part of this history
                break
            ev["actual_h"] = act
            ev["delay_h"] = float(act - ts)
            k = act - h
            m_b = Rm if k == 0 else float(cumM[k - 1])
            if 100.0 * (vol_from_W(Rw if k == 0 else cumW[k - 1], C, c)) / C < 3.0 and cand["trigger"] != "DECOMMISSION":
                ev["status"] = "WASTED_TRIP"
                ev["wasted_reason"] = "NOTHING_TO_COLLECT"
                new_events.append(ev)
                last_coll = max(last_coll, act)      # emptiness verified: the max-interval clock restarts
                if kind == "pending":
                    pending = None
                cursor = ts + 1
                continue
            completed = (ev, k, kind)
            break

        if need_extend:
            (cursor, pending, forced, used_req, used_pre, decom_done, seq, adhoc_done, last_coll) = state_snapshot
            window = window * 2
            continue
        events.extend(new_events)
        window = 60 * 24
        if completed is None:
            # no completion until e (== h1): write trajectory to the end
            if record_arrays or True:
                o = h - h0
                m_true[o:o + (e - h)] = cumM
                fill_true[o:o + (e - h)] = fill
                side_stock[o:o + (e - h)] = side_cum
                cont_kg[o:o + (e - h)] = cumC
                water_kg[o:o + (e - h)] = cumH2O
                if fullidx is not None:
                    full_flag[o + fullidx:o + (e - h)] = True
            Rm, Rw, Rc, Rwater, side = float(cumM[-1]), float(cumW[-1]), float(cumC[-1]), float(cumH2O[-1]), float(side_cum[-1])
            h = e
            continue
        ev, k, kind = completed
        o = h - h0
        if k > 0:
            m_true[o:o + k] = cumM[:k]
            fill_true[o:o + k] = fill[:k]
            side_stock[o:o + k] = side_cum[:k]
            cont_kg[o:o + k] = cumC[:k]
            water_kg[o:o + k] = cumH2O[:k]
            if fullidx is not None and fullidx < k:
                full_flag[o + fullidx:o + k] = True
        m_b = Rm if k == 0 else float(cumM[k - 1])
        W_b = Rw if k == 0 else float(cumW[k - 1])
        C_b = Rc if k == 0 else float(cumC[k - 1])
        H_b = Rwater if k == 0 else float(cumH2O[k - 1])
        s_b = side if k == 0 else float(side_cum[k - 1])
        fill_b = 100.0 * min(1.0, vol_from_W(W_b, C, c) / C)
        act = ev["actual_h"]
        aday = int(tb.day_idx[act])
        winter = tb.month_d[aday] in (12, 1, 2, 3)
        pp = ops["partial_prob_biowaste_winter"] if (spec["material"] == "biowaste" and winter) else ops["partial_prob_default"]
        r = float(rng.uniform(*ops["partial_residual"], "resid", act)) if rng.random("partial", act) < pp * ctx.profile.get("scenario_intensity", 1.0) else 0.0
        side_coll = s_b if (s_b > 1.0 and rng.random("side", act) < 0.85) else 0.0
        ev.update({
            "status": "PARTIAL" if r > 0 else "COMPLETED",
            "true_mass_before_kg": m_b, "true_fill_before_pct": fill_b,
            "true_collected_kg": m_b * (1 - r), "true_residual_kg": m_b * r,
            "true_side_waste_collected_kg": side_coll, "true_side_stock_before_kg": s_b,
            "true_contamination": (C_b / m_b) if m_b > 0 else 0.0,
            "true_moisture_extra": (H_b / max(m_b - H_b, 1e-9)) if m_b > 0 else 0.0,
            "cycle_start_h": last_coll, "hours_since_last": act - last_coll,
            "cycle_overflow_kg": float(np.sum(over[:k])) if k > 0 else 0.0,
            "cycle_full_hours": int(np.sum(cumW[:k] >= Wcap)) if k > 0 else 0,
            "kind": kind,
        })
        events.append(ev)
        Rm, Rw, Rc, Rwater = m_b * r, W_b * r, C_b * r, H_b * r
        side = s_b - side_coll
        last_coll = act
        h = act
        cursor = max(cursor, h, ev["sched_h"] + 1 if kind == "slot" else h)
        pending = None                      # any completion satisfies an open on-call order
        adhoc_done = False
        forced = [f for f in forced if f["sched_h"] > act]
        # an ad-hoc / request collection does not cancel later fixed slots (realistic over-servicing)
    return {"events": events, "m_true": m_true, "fill_true": fill_true, "side_stock": side_stock,
            "cont_kg": cont_kg, "water_kg": water_kg, "full": full_flag, "h0": h0, "h1": h1,
            "end_state": {"Rm": Rm, "Rw": Rw, "Rc": Rc, "Rwater": Rwater, "side": side, "last_coll": last_coll}}


# ----------------------------------------------------------------------------------------------
# Cost of a simulated event list (used for counterfactual evaluation)
# ----------------------------------------------------------------------------------------------

def version_at(versions: list, date: dt.date) -> dict:
    v = versions[0]
    for vv in versions:
        if vv["effective_from"] <= date:
            v = vv
    return v


def event_cost_cents(spec, ev, ctx: Ctx, grades: dict) -> tuple:
    tb = ctx.tb
    t_h = ev.get("actual_h") if ev.get("actual_h") is not None else ev["sched_h"]
    t_h = min(int(t_h), tb.n_hours - 1)
    d = tb.dates[int(tb.day_idx[t_h])]
    v = version_at(ctx.versions[spec["contract_id"]], d)
    st = ev["status"]
    if st in ("COMPLETED", "PARTIAL"):
        kg = int(round(ev["true_collected_kg"] + ev["true_side_waste_collected_kg"]))
        g = grade_from_contamination(ev["true_contamination"], grades) if spec["credit_eligible"] else None
        idx = ctx.index_cents.get((spec.get("index_id"), ctx.month_key_d[int(tb.day_idx[t_h])]))
        r = price_event(v, st, kg, g, idx, emergency=(ev.get("orig_trigger") if ev["trigger"] == "RESCHEDULED" else ev["trigger"]) == "AD_HOC_CUSTOMER",
                        side_waste=ev["true_side_waste_collected_kg"] > 0, credit_eligible=spec["credit_eligible"])
        s = summarize(r["lines"], kg)
        return s["total_customer_cost_cents"], kg
    if st in ("CANCELLED_BY_CUSTOMER", "WASTED_TRIP"):
        r = price_event(v, st, None, notice_hours=ev.get("notice_h"))
        return sum(l["amount_cents"] for l in r["lines"]), 0
    return 0, 0
