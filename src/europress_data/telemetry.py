"""Observation model: simulator truth -> published hourly telemetry messages.

Separates (1) simulator ground truth, (2) assumed sensor measurements, (3) delivery artefacts.
Nothing in the published telemetry is copied from the truth without passing through the
measurement model (noise, drift, calibration, faults, spikes, resolution, connectivity).
"""
from __future__ import annotations

import numpy as np

from .simulate import obs_fill_values, obs_mass

STATUS_NAMES = np.array(["OK", "DEGRADED", "FAULT", "NOT_INSTALLED"])
STATE_NAMES = np.array(["IDLE", "ACTIVE", "FULL", "DOWN"])


def build_telemetry(spec: dict, arr: dict, res: dict, ctx) -> dict:
    tb, A = ctx.tb, ctx.A
    T = A["telemetry"]
    h0, h1 = res["h0"], res["h1"]
    L = h1 - h0
    if L <= 0:
        return {"rows": None, "obs_fill": np.array([]), "obs_mass": np.array([]), "delivered": np.array([], bool)}
    rt = arr["rt"]
    dev = spec["device_id"]
    dn = spec["device_num"]
    sl = slice(h0, h1)
    hours = np.arange(h0, h1)
    m_true = res["m_true"]
    fill_true = res["fill_true"]
    status = arr["status"][sl].copy()

    # ---- measurements ----
    fill_obs = np.round(obs_fill_values(fill_true, sl, arr), 1)
    mass = obs_mass(m_true, sl, arr, A)
    spike = rt.random(L) < T["spike_prob"]
    spike_flagged = spike & (rt.random(L) < 0.6)
    mass = np.where(spike & ~np.isnan(mass), mass + rt.choice([-1, 1], L) * rt.uniform(500, 2500, L), mass)
    sig = np.maximum(T["mass_sigma_abs_kg"], T["mass_sigma_rel"] * np.nan_to_num(np.abs(mass))) * np.where(status == 1, 3.0, 1.0)
    unc = np.where(np.isnan(mass), np.nan, np.round(sig, 0))
    n_ev = arr["n_ev"][sl]
    down = arr["down"][sl]
    cycles = np.where(down, 0, rt.binomial(n_ev, 0.85) + (rt.random(L) < 0.02)).astype(np.int16)
    # press load responds to the compacted state as the device itself senses it (same systematics as fill_pct)
    press = np.where(cycles > 0, np.clip(100 * (np.clip(fill_obs, 0, 100) / 100) ** 1.4 * (1 + rt.normal(0, 0.06, L)) + rt.normal(0, 2, L), 0, 100), np.nan)
    press = np.round(press, 1)
    # FULL is what the device can observe: its own fill estimate at the top of the range, or a press that
    # can no longer compact (true full) while the site keeps loading
    full_obs = (fill_obs >= 97.5) | (res["full"] & (n_ev > 0) & (rt.random(L) < 0.7))
    state = np.where(down, 3, np.where(full_obs, 2, np.where(cycles > 0, 1, 0)))
    qf = np.full(L, "VALID", dtype=object)
    qf[status == 1] = "LOW_CONFIDENCE"
    qf[(mass < 0) & ~np.isnan(mass)] = "NEGATIVE_READING"
    qf[spike_flagged & ~np.isnan(mass)] = "SUSPECT_SPIKE"
    qf[status == 2] = "SENSOR_FAULT"
    qf[status == 3] = "NO_WEIGHT_SENSOR"

    # ---- delivery ----
    t_meas = tb.hours_utc[h0:h1].as_unit("ms").asi8 + 3600_000 - (rt.uniform(0, 240, L) * 1000).astype(np.int64)
    lat = rt.lognormal(np.log(T["latency_median_s"]), 1.0, L)
    tail = rt.random(L) < 0.01
    lat = lat + np.where(tail, rt.uniform(300, 7200, L), 0)
    ep = spec["episodes"]
    for d0, d1 in ep.get("latency", []):
        s_h, e_h = int(tb.day_start_h[min(d0, tb.n_days - 1)]), int(tb.day_start_h[min(d1, tb.n_days - 1)])
        msk = (hours >= s_h) & (hours < e_h)
        lat[msk] = rt.lognormal(np.log(7200), 0.8, int(msk.sum()))
    t_recv = t_meas + (lat * 1000).astype(np.int64)
    delivered = rt.random(L) >= T["isolated_drop_prob"]
    buffered = np.zeros(L, dtype=bool)
    for st, en, buf in arr["outages"]:
        a, b = max(st, h0), min(en, h1)
        if a >= b:
            continue
        idx = np.arange(a - h0, b - h0)
        end_ms = int(tb.hours_utc[0].value // 10 ** 6) + int(en) * 3_600_000
        if buf:
            keep = (en - hours[idx]) <= 72
            delivered[idx[~keep]] = False
            k = idx[keep]
            t_recv[k] = end_ms + (rt.uniform(0, 1800, k.size) * 1000).astype(np.int64)
            buffered[k] = True
        else:
            delivered[idx] = False
    t_recv = np.maximum(t_recv, t_meas + 500)
    dup_p = np.full(L, T["duplicate_prob"])
    if ep.get("dup_burst"):
        d0, d1 = ep["dup_burst"]
        s_h, e_h = int(tb.day_start_h[min(d0, tb.n_days - 1)]), int(tb.day_start_h[min(d1, tb.n_days - 1)])
        dup_p[(hours >= s_h) & (hours < e_h)] = 0.06
    dup = delivered & (rt.random(L) < dup_p)

    sid = np.where(arr["sensor_idx"][sl] == 0, f"WS-{dn:05d}-1", f"WS-{dn:05d}-2")
    if not spec["has_weight_sensor"]:
        sid = np.full(L, None, dtype=object)
    base_idx = np.nonzero(delivered)[0]
    dup_idx = np.nonzero(dup)[0]
    take = np.concatenate([base_idx, dup_idx])
    recv = np.concatenate([t_recv[base_idx], t_recv[dup_idx] + (rt.uniform(5, 900, dup_idx.size) * 1000).astype(np.int64)])
    order = np.lexsort((take, recv))
    take, recv = take[order], recv[order]
    rows = {
        "message_id": (np.int64(dn) * 1_000_000 + hours[take]).astype(np.int64),
        "device_id": np.full(take.size, dev, dtype=object),
        "sensor_id": sid[take],
        "measured_at": t_meas[take],
        "received_at": recv,
        "fill_pct": fill_obs[take].astype(np.float32),
        "mass_kg": mass[take].astype(np.float32),
        "mass_uncertainty_kg": unc[take].astype(np.float32),
        "compaction_cycles": cycles[take],
        "press_load_index": press[take].astype(np.float32),
        "operational_state": STATE_NAMES[state[take]],
        "sensor_status": STATUS_NAMES[status[take]],
        "quality_flag": qf[take],
        "delivery_mode": np.where(buffered[take], "BUFFERED", "LIVE"),
    }
    rows["ingest_seq"] = np.arange(1, take.size + 1, dtype=np.int64)
    rows["delivery_id"] = np.int64(dn) * 10_000_000 + rows["ingest_seq"]
    return {"rows": rows, "obs_fill": np.where(delivered, fill_obs, np.nan),
            "obs_mass": np.where(delivered & np.isin(qf, ["VALID", "LOW_CONFIDENCE", "NEGATIVE_READING"]), mass, np.nan),
            "obs_mass_any": np.where(delivered, mass, np.nan), "delivered": delivered, "qf": qf,
            "spike": spike, "n_dup": int(dup.sum()), "n_lost": int((~delivered).sum())}
