"""Decision cases and counterfactual evaluation (Task C / D ground truth).

For a device at decision time t, each candidate action is re-simulated over the horizon with the
SAME exogenous inflow, density, contamination and sensor arrays (common random numbers) and the
same operations random stream, starting from the actual physical state at t.

The result is a *simulated counterfactual*: it is evidence only inside this synthetic world and
must never be presented as real-world causal evidence or as a guaranteed saving.
"""
from __future__ import annotations

import numpy as np

from .rng import KeyedRandom
from .simulate import FREQ_OPTIONS, W_from_vol, event_cost_cents, run_policy

ONE_OFF_COST_CENTS = {"SORTING_INTERVENTION": 25000}     # illustrative assumption: staff briefing + signage
DIAGNOSTIC_ACTIONS = ["VERIFY_WEIGHT_SENSOR", "REVIEW_INVOICES"]


def _weekdays_for(freq, current):
    first = current[0] if current else 0
    if freq >= 5:
        return [0, 1, 2, 3, 4]
    if freq >= 3:
        return [0, 2, 4]
    if freq >= 2:
        return sorted({first % 5, (first + 3) % 5})
    return [first % 5]


def candidate_actions(spec: dict) -> list:
    pol = spec["policy"]
    acts = ["NO_ACTION"]
    if pol["type"] in ("FIXED_SCHEDULE", "HYBRID"):
        i = FREQ_OPTIONS.index(pol["freq_per_week"])
        min_f = 7.0 / spec["max_days"]
        if i + 1 < len(FREQ_OPTIONS) and FREQ_OPTIONS[i + 1] >= min_f - 1e-9:
            acts.append("REDUCE_FREQUENCY")
        if i > 0:
            acts.append("INCREASE_FREQUENCY")
        acts.append("SWITCH_TO_ON_CALL")
    else:
        if pol["threshold_pct"] <= 88:
            acts.append("RAISE_THRESHOLD")
        acts.append("LOWER_THRESHOLD")
    if spec["has_weight_sensor"]:
        acts.append("MASS_TARGET_TRIGGER")
    if spec["credit_eligible"]:
        acts.append("SORTING_INTERVENTION")
    return acts


def policy_for(action: str, spec: dict) -> dict:
    p = dict(spec["policy"])
    if action in ("REDUCE_FREQUENCY", "INCREASE_FREQUENCY"):
        i = FREQ_OPTIONS.index(p["freq_per_week"]) + (1 if action == "REDUCE_FREQUENCY" else -1)
        p["freq_per_week"] = FREQ_OPTIONS[i]
        p["weekdays"] = _weekdays_for(p["freq_per_week"], p["weekdays"])
    elif action == "SWITCH_TO_ON_CALL":
        p["type"] = "ON_CALL"
        p["threshold_pct"] = 85.0
    elif action == "RAISE_THRESHOLD":
        p["threshold_pct"] = min(96.0, p["threshold_pct"] + 8)
    elif action == "LOWER_THRESHOLD":
        p["threshold_pct"] = max(50.0, p["threshold_pct"] - 10)
    elif action == "MASS_TARGET_TRIGGER":
        p["type"] = "MASS_TRIGGER"
        p["mass_target_kg"] = 0.8 * spec["cap_mass_kg"]
    return p


def _init_state(res: dict, spec: dict, dh: int) -> dict:
    h0 = res["h0"]
    i = dh - 1 - h0
    if i < 0:
        return {"Rm": 0.0, "Rw": 0.0, "Rc": 0.0, "Rwater": 0.0, "side": 0.0, "last_coll": dh}
    C, c = spec["volume_m3"], spec["compressibility"]
    V = res["fill_true"][i] / 100.0 * C
    last = h0
    for ev in res["events"]:
        if ev["status"] in ("COMPLETED", "PARTIAL") and ev["actual_h"] < dh:
            last = ev["actual_h"]
    return {"Rm": float(res["m_true"][i]), "Rw": float(W_from_vol(V, C, c)), "Rc": float(res["cont_kg"][i]),
            "Rwater": float(res["water_kg"][i]), "side": float(res["side_stock"][i]), "last_coll": int(last)}


def _simulate_action(spec, arr, ctx, act, dh, h1, init, salt, open_h):
    tb = ctx.tb
    pol = policy_for(act, spec)
    ov = {}
    if act == "SORTING_INTERVENTION":
        mult = np.ones(tb.n_hours)
        mult[min(tb.n_hours, dh + 7 * 24):] = 0.4
        ov["contam"] = arr["contam"] * mult
    rng = KeyedRandom(ctx.seed, salt, spec["device_id"])     # replication 0 = the realised history's stream (CRN)
    r = run_policy(spec, arr, ctx, pol, dh, h1, init, rng, overrides=ov)
    cost = kg = n_lifts = 0
    times = [init["last_coll"]]
    for ev in r["events"]:
        cc, k = event_cost_cents(spec, ev, ctx, ctx.A["quality_grades"])
        cost += cc
        kg += k
        if ev["status"] in ("COMPLETED", "PARTIAL"):
            n_lifts += 1
            times.append(ev["actual_h"])
    times.append(h1)
    viol = int(np.sum(np.diff(times) / 24.0 > spec["max_days"] + 1.0))
    overflow_h = int(np.sum(r["full"] & open_h[: len(r["full"])])) if len(r["full"]) else 0
    end_mass = float(r["m_true"][-1] + r["side_stock"][-1]) if len(r["m_true"]) else 0.0
    return cost + ONE_OFF_COST_CENTS.get(act, 0), kg, n_lifts, viol, overflow_h, end_mass


def evaluate_case(spec, arr, res, ctx, dh: int, horizon_h: int, case_id: str, replications: int = 1, rep_prefix: str = "rep") -> list:
    """Expected outcome of every candidate action over `replications` paired operational scenarios.

    Replication 0 reuses the realised history's random stream; the others use independent keyed streams.
    Within a replication every action sees identical random draws for identical events (paired comparison).
    """
    tb = ctx.tb
    h1 = min(tb.n_hours, dh + horizon_h)
    init = _init_state(res, spec, dh)
    open_h = arr["open_d"][tb.day_idx[dh:h1]]
    mcpk = marginal_cents_per_kg(spec, ctx, dh)        # contract-based value of leftover mass (not realised averages)
    acts = candidate_actions(spec)
    R = max(1, int(replications))
    sims = {a: [_simulate_action(spec, arr, ctx, a, dh, h1, init, "ops" if k == 0 else f"{rep_prefix}{k}", open_h) for k in range(R)] for a in acts}
    adj = {a: np.array([c + (e - b[5]) * mcpk for (c, _, _, _, _, e), b in zip(sims[a], sims["NO_ACTION"])]) for a in acts}
    base = sims["NO_ACTION"]
    out = []
    for a in acts:
        S = np.array([x[:5] + (x[5],) for x in sims[a]], dtype=float)
        o = {"case_id": case_id, "action": a, "n_replications": R,
             "sim_cost_cents": int(round(S[:, 0].mean())), "one_off_cost_cents": ONE_OFF_COST_CENTS.get(a, 0),
             "n_completed_lifts": float(round(S[:, 2].mean(), 2)), "collected_kg": int(round(S[:, 1].mean())),
             "overflow_open_hours": float(round(S[:, 4].mean(), 2)), "max_interval_violations": float(round(S[:, 3].mean(), 2)),
             "end_state_mass_kg": round(float(S[:, 5].mean()), 1), "terminal_value_cents_per_kg": round(mcpk, 4),
             "adjusted_cost_cents": int(round(adj[a].mean())),
             "adjusted_cost_sd_cents": int(round(adj[a].std(ddof=1))) if R > 1 else 0}
        d = adj["NO_ACTION"] - adj[a]
        o["benefit_vs_no_action_cents"] = int(round(d.mean()))
        o["benefit_se_cents"] = int(round(d.std(ddof=1) / np.sqrt(R))) if R > 1 else 0
        out.append(o)
    b = next(o for o in out if o["action"] == "NO_ACTION")
    base_cost_per_lift = b["sim_cost_cents"] / max(b["n_completed_lifts"], 1)
    for o in out:
        o["permissible"] = bool(o["max_interval_violations"] <= b["max_interval_violations"] + 1e-9 and
                                o["overflow_open_hours"] <= b["overflow_open_hours"] + 24)
        naive = (b["n_completed_lifts"] - o["n_completed_lifts"]) * base_cost_per_lift
        o["naive_lift_saving_cents"] = int(round(naive))
        o["hidden_cost_trap"] = bool(naive > 5000 and o["benefit_vs_no_action_cents"] < 0)
    # paired standard error of each action's difference to the best permissible action (for tolerance)
    perm = [o for o in out if o["permissible"]]
    best = min(perm, key=lambda o: o["adjusted_cost_cents"])
    for o in out:
        d = adj[o["action"]] - adj[best["action"]]
        o["diff_to_best_se_cents"] = int(round(d.std(ddof=1) / np.sqrt(R))) if R > 1 else 0
    return out


def marginal_cents_per_kg(spec, ctx, dh: int) -> float:
    """Expected contract cost of handling one more kg: per-load fixed fees spread over a typical 80 % load,
    plus per-tonne fees, minus the recyclable credit at the decision month's index."""
    from .simulate import version_at
    tb = ctx.tb
    di = int(tb.day_idx[min(dh, tb.n_hours - 1)])
    v = version_at(ctx.versions[spec["contract_id"]], tb.dates[di])
    km = max(0, int(v["contract_km"]) - int(v["free_km"]))
    fixed = (int(v["lift_fee_cents"]) + km * int(v["per_km_cents"]) + int(v["remote_surcharge_cents"])) * (1 + int(v["fuel_surcharge_bp"]) / 10000)
    load = max(0.8 * spec["cap_mass_kg"], 50.0)
    per_kg = fixed / load + (int(v["haul_fee_cents_per_t"]) + int(v["processing_fee_cents_per_t"])) / 1000
    if spec["credit_eligible"] and int(v["credit_share_bp"]):
        idx = ctx.index_cents.get((spec.get("index_id"), ctx.month_key_d[di])) or 0
        per_kg -= max(0, idx) * int(v["credit_share_bp"]) / 10000 / 1000
    return float(per_kg)


def label_case(outcomes: list) -> dict:
    perm = [o for o in outcomes if o["permissible"]]
    best = min(perm, key=lambda o: o["adjusted_cost_cents"])
    tol = max(2500, int(0.03 * abs(best["adjusted_cost_cents"])))
    # acceptable: within the economic tolerance, or statistically indistinguishable from the best (2 paired SE)
    acceptable = sorted(o["action"] for o in perm
                        if o["adjusted_cost_cents"] <= best["adjusted_cost_cents"] + max(tol, 2 * o.get("diff_to_best_se_cents", 0)))
    raw_best = min(outcomes, key=lambda o: o["adjusted_cost_cents"])
    near = best["action"] != "NO_ACTION" and best["benefit_vs_no_action_cents"] < tol
    return {"best_action": best["action"], "best_benefit_cents": best["benefit_vs_no_action_cents"],
            "acceptable_actions": ",".join(acceptable), "no_action_acceptable": "NO_ACTION" in acceptable,
            "near_threshold": bool(near),
            "constraint_conflict": bool(not raw_best["permissible"]),
            "hidden_cost_trap_present": any(o["hidden_cost_trap"] for o in outcomes),
            "tolerance_cents": tol}
