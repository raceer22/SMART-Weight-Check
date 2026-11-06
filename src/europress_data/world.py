"""Synthetic world: organisations, sites, devices, operators, vehicles, contracts, price indices.

Everything here is invented. Identifiers are deliberately generic (ORG-0001, SITE-00001, CMP-00001)
so they cannot be mistaken for real Europress customers or products.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .rng import rng_for
from .timebase import TimeBase

CITIES = {
    "FI-02": ["Turku", "Raisio", "Kaarina", "Salo", "Naantali", "Lieto", "Uusikaupunki"],
    "FI-01": ["Helsinki", "Espoo", "Vantaa", "Kerava", "Porvoo", "Lohja", "Hyvinkää"],
    "FI-11": ["Tampere", "Nokia", "Ylöjärvi", "Kangasala", "Lempäälä", "Valkeakoski"],
    "FI-08": ["Jyväskylä", "Äänekoski", "Jämsä", "Laukaa"],
    "FI-17": ["Oulu", "Raahe", "Kempele", "Kuusamo", "Ylivieska"],
    "FI-19": ["Rovaniemi", "Kemi", "Tornio", "Sodankylä", "Kittilä"],
}

SECTOR_LABEL = {
    "grocery_retail": "Grocery", "nonfood_retail": "Retail", "shopping_center": "Mall",
    "logistics_warehouse": "Logistics", "manufacturing": "Manufacturing",
    "hospitality_hotel": "Hospitality", "food_processing": "FoodPro", "office_services": "Office",
}

FREQ_OPTIONS = [5.0, 3.0, 2.0, 1.0, 0.5, 0.25]   # collections per week for fixed schedules

# reference indices exist only for credit-eligible streams (cardboard and plastics; Europress review 30.10.2026)
INDEX_ID = {"cardboard": "IDX-OCC", "plastic_film": "IDX-FILM", "mixed_plastic": "IDX-MIXPL"}


CONTRACT_NOTE = ("HYPOTHETICAL illustrative customer–operator tariff. Europress is not a party. "
                 "Not an actual operator contract.")


def eur_to_cents(x: float) -> int:
    return int(round(float(x) * 100))


@dataclass
class World:
    tb: TimeBase
    orgs: pd.DataFrame
    sites: pd.DataFrame
    devices: pd.DataFrame
    operators: pd.DataFrame
    vehicles: pd.DataFrame
    facilities: pd.DataFrame
    contracts: pd.DataFrame
    contract_versions: pd.DataFrame
    price_index: pd.DataFrame
    site_calendar: pd.DataFrame
    regions: pd.DataFrame
    specs: dict = field(default_factory=dict)      # device_id -> spec dict (simulation inputs)
    site_open: dict = field(default_factory=dict)  # site_id -> (open_d bool[n_days], open_h, close_h, closure_reason list)
    global_scen: dict = field(default_factory=dict)


def _choice_weighted(rng, d: dict):
    keys = list(d.keys())
    p = np.array([float(v) for v in d.values()], dtype=float)
    return keys[rng.choice(len(keys), p=p / p.sum())]


def _build_price_index(tb: TimeBase, A: dict, seed: int, profile: dict) -> pd.DataFrame:
    rng = rng_for(seed, "price_index")
    # monthly keys from one month before start to end
    first = dt.date(tb.start.year, tb.start.month, 1) - dt.timedelta(days=1)
    months = [f"{first.year:04d}-{first.month:02d}"] + tb.month_keys
    rows = []
    n = len(months)
    for mat, idx_id in INDEX_ID.items():
        m = A["materials"][mat]
        p0 = float(m["index_start"])
        vol = float(m["index_monthly_vol"])
        level = np.empty(n)
        x = 0.0
        for i in range(n):
            x = 0.75 * x + rng.normal(0, vol)        # mean-reverting log deviation
            level[i] = x
        mult = np.ones(n)
        # Scenario S05: cardboard value collapse (3 months), S06: film price spike (1-2 months)
        if mat == "cardboard" and n > 6:
            c0 = int(n * 0.42)
            depth = 0.48
            mult[c0:c0 + 3] *= (1 - depth)
            mult[c0 + 3:c0 + 4] *= (1 - depth / 2)
        if mat == "plastic_film" and n > 4:
            s0 = int(n * 0.25)
            mult[s0] *= 1.55
            mult[s0 + 1] *= 1.25
        if profile.get("market_regimes") and n > 14:
            # second-year market regime shift (enterprise profile)
            shift = {"cardboard": 0.82, "plastic_film": 1.15, "mixed_plastic": 0.6}[mat]
            mult[12:] *= shift
        if mat == "mixed_plastic":
            price = p0 * mult + 40 * level          # additive: can go negative (handling cost)
        else:
            price = p0 * np.exp(level) * mult
        for i, mk in enumerate(months):
            y, mo = map(int, mk.split("-"))
            pub = (dt.date(y, mo, 28) + dt.timedelta(days=6)).replace(day=3)
            rows.append({"index_id": idx_id, "material": mat, "month": mk,
                         "price_eur_per_t": round(float(price[i]), 2),
                         "published_on": pub, "source": "SYNTHETIC illustrative index"})
    return pd.DataFrame(rows)


def build_world(cfg, tb: TimeBase) -> World:
    A = cfg.assumptions
    P = cfg.profile
    seed = cfg.seed
    rng = rng_for(seed, "world")
    target = int(P["target_devices"])
    intensity = float(P.get("scenario_intensity", 1.0))

    # ---------------- regions, operators, vehicles, facilities ----------------
    regions = pd.DataFrame([{"region_code": k, "region_name": v["name"], "median_billable_km": v["median_km"],
                             "remote_surcharge_eur": v["remote_surcharge"]} for k, v in A["regions"].items()])
    op_rows, veh_rows, fac_rows = [], [], []
    for op_id, o in A["operators"].items():
        op_rows.append({"operator_id": op_id, "operator_name": o["name"], "regions_served": ",".join(o["regions"]),
                        "weighbridge_data_shared": o["weighbridge_share_prob"] > 0,
                        "api_feed": bool(o["api_feed"]), "synthetic": True})
        orng = rng_for(seed, "operator", op_id)
        for k in range(int(orng.integers(10, 22))):
            tare = int(orng.uniform(11500, 16500))
            stored_err = int(orng.normal(0, 40))
            if orng.random() < 0.22 * intensity:            # S20: outdated stored tare (tare not re-weighed after changes)
                stored_err += int(orng.choice([-1, 1]) * orng.uniform(180, 420))
            veh_rows.append({"vehicle_id": f"{op_id}-V{k + 1:02d}", "operator_id": op_id,
                             "true_tare_kg": tare, "stored_tare_kg": tare + stored_err})
        for k, reg in enumerate(o["regions"]):
            # operator-side data: Europress does not know where the operator takes the material. Facilities are kept
            # in the private truth only; public weighbridge tickets (operator-shared records) carry the facility id.
            fac_rows.append({"facility_id": f"FAC-{op_id[-1]}{k + 1}", "operator_id": op_id, "region_code": reg,
                             "facility_type": "sorting_and_treatment (fictional)"})
    operators = pd.DataFrame(op_rows)
    vehicles = pd.DataFrame(veh_rows)
    facilities = pd.DataFrame(fac_rows)
    ops_by_region = {r: [o for o, v in A["operators"].items() if r in v["regions"]] for r in A["regions"]}

    sectors = A["sectors"]
    sector_names = list(sectors.keys())
    sector_w = np.array([sectors[s]["weight"] for s in sector_names], dtype=float)
    reg_codes = list(A["regions"].keys())
    reg_w = np.array([A["regions"][r]["weight"] for r in reg_codes], dtype=float)
    spo = A["organisations"]["sites_per_org"]

    org_rows, site_rows, dev_rows = [], [], []
    specs = {}
    n_dev = 0
    org_n = 0
    site_n = 0
    mats = A["materials"]
    pol_cfg = A["policies"]
    while n_dev < target:
        org_n += 1
        org_id = f"ORG-{org_n:04d}"
        orng = rng_for(seed, "org", org_id)
        primary = sector_names[orng.choice(len(sector_names), p=sector_w / sector_w.sum())]
        org_sectors = [primary]
        if orng.random() > A["organisations"]["single_sector_prob"]:
            other = [s for s in sector_names if s != primary]
            org_sectors.append(other[orng.integers(len(other))])
        n_sites = int(_choice_weighted(orng, {int(k): v for k, v in spo.items()}))
        home_regions = list(orng.choice(reg_codes, size=min(len(reg_codes), 1 + int(n_sites > 3) + int(n_sites > 10)),
                                        replace=False, p=reg_w / reg_w.sum()))
        org_ops = {r: ops_by_region[r][orng.integers(len(ops_by_region[r]))] for r in reg_codes}
        org_rows.append({"customer_id": org_id,
                         "customer_name": f"Fictional {SECTOR_LABEL[primary]} Customer {org_n:04d}",
                         "primary_sector": primary, "n_sites": n_sites, "synthetic": True})
        org_scale = float(np.exp(orng.normal(0, 0.25)))
        for s in range(n_sites):
            if n_dev >= target:
                break
            site_n += 1
            site_id = f"SITE-{site_n:05d}"
            srng = rng_for(seed, "site", site_id)
            sector = org_sectors[0] if (len(org_sectors) == 1 or srng.random() < 0.7) else org_sectors[1]
            sc = sectors[sector]
            region = home_regions[srng.integers(len(home_regions))]
            city = CITIES[region][srng.integers(len(CITIES[region]))]
            rc = A["regions"][region]
            km = int(max(4, round(rc["median_km"] * np.exp(srng.normal(0, rc["km_sigma"])))))
            site_scale = org_scale * float(np.exp(srng.normal(0, 0.35)))
            outdoor = bool(srng.random() < 0.35)
            site_rows.append({"site_id": site_id, "customer_id": org_id, "site_name": f"{city} site {s + 1} ({org_id})",
                              "sector": sector, "region_code": region, "municipality": city,
                              "billable_round_trip_km": km, "outdoor_material_staging": outdoor,
                              "opening_days_mon_sun": "".join(str(x) for x in sc["open_days"]),
                              "opening_hours_local": f"{sc['hours'][0]:02d}-{sc['hours'][1]:02d}",
                              "timezone": A["timezone"], "synthetic": True})
            # streams
            streams = [m for m, (p, _, _) in sc["streams"].items() if srng.random() < p]
            if not streams:
                streams = [max(sc["streams"], key=lambda m: sc["streams"][m][0])]
            site_contam_base = {}
            for mat in streams:
                if n_dev >= target:
                    break
                n_dev += 1
                dev_id = f"CMP-{n_dev:05d}"
                drng = rng_for(seed, "device_static", dev_id)
                m = mats[mat]
                p_has, med_kg, lsig = sc["streams"][mat]
                daily = float(med_kg * site_scale * np.exp(drng.normal(0, lsig * 0.6)))
                wk = np.array(sc["weekday"], dtype=float)
                mean_daily = daily * wk.mean()
                density = float(m["compacted_density"] * np.exp(drng.normal(0, m["density_cv"])))
                comp = float(m["compressibility"])
                equip = m["equipment"][drng.integers(len(m["equipment"]))]
                target_days = float(np.exp(drng.normal(np.log(min(9.0, m["max_days_between"] * 0.7)), 0.35)))
                best = None
                for v in m["volumes"]:
                    capm = v * density * (1 + comp / 2)
                    days = capm / max(mean_daily, 1.0)
                    score = abs(np.log(days / target_days))
                    if best is None or score < best[0]:
                        best = (score, v, capm, days)
                _, vol, capm, days_full = best
                vols = list(m["volumes"])
                if drng.random() < 0.12 and vols.index(vol) + 1 < len(vols):   # customer bought a larger unit
                    vol = vols[vols.index(vol) + 1]
                    capm = vol * density * (1 + comp / 2)
                    days_full = capm / max(mean_daily, 1.0)
                # Europress container limits: COMBI max 22 m3, DUO max 30 m3. equipment_class is a label only,
                # so a larger unit is a DUO (no random draw, the rest of the world is unchanged)
                vmax = A["equipment_max_volume_m3"]
                if vol > vmax[equip]:
                    equip = "DUO"
                if vol > vmax[equip]:
                    raise ValueError(f"{mat}: container {vol} m3 exceeds every equipment class limit")
                # collection policy
                pol = _choice_weighted(drng, pol_cfg["mix"])
                # customers plan for ~70 % fill (safety margin after past overflows) but mis-estimate demand
                days70 = 0.70 * days_full
                est_days = days70 * float(np.exp(drng.normal(0, pol_cfg["sizing_error_sigma"])))
                est_days = min(est_days, m["max_days_between"])
                desired = 7.0 / max(est_days, 0.5)
                ok = [f for f in FREQ_OPTIONS if f >= 0.85 * desired]
                freq = min(ok) if ok else max(FREQ_OPTIONS)
                min_freq = 7.0 / m["max_days_between"]
                if freq < min_freq:
                    freq = min([f for f in FREQ_OPTIONS if f >= min_freq])
                if pol == "HYBRID":
                    idx = FREQ_OPTIONS.index(freq)
                    freq = FREQ_OPTIONS[max(0, idx - 1)]          # hybrid: book more often, skip when low
                if sc["open_days"][6] == 0 and freq == 5.0:
                    freq = 3.0 if sc["open_days"][5] == 0 else freq
                wd = _weekday_set(freq, drng)
                policy = {"type": pol, "freq_per_week": freq, "weekdays": wd,
                          "week_parity": int(drng.integers(0, 4)),
                          "route_hour": int(drng.integers(6, 14)),
                          "threshold_pct": float(np.round(drng.uniform(*pol_cfg["on_call_threshold_pct"]), 0)),
                          "skip_below_pct": float(np.round(drng.uniform(*pol_cfg["hybrid_skip_below_pct"]), 0)),
                          "adhoc_after_full_h": float(drng.uniform(*pol_cfg["adhoc_after_full_hours"]))}
                has_w = bool(drng.random() > 0.08)
                operator = org_ops[region] if drng.random() > 0.15 else ops_by_region[region][drng.integers(len(ops_by_region[region]))]
                act_from = 0
                act_to = tb.n_days
                status = "ACTIVE"
                commissioned = tb.start - dt.timedelta(days=int(drng.integers(120, 3600)))
                u = drng.random()
                if u < 0.04 and tb.n_days > 120:
                    act_from = int(drng.integers(20, tb.n_days // 2))
                    commissioned = tb.start + dt.timedelta(days=act_from)
                elif u < 0.055 and tb.n_days > 120:
                    act_to = int(drng.integers(tb.n_days // 2, tb.n_days - 20))
                    status = "DECOMMISSIONED"
                if mat in ("cardboard", "paper", "plastic_film", "mixed_plastic"):
                    a, b = m["contamination_alpha"], m["contamination_beta"]
                    site_contam_base[mat] = float(drng.beta(a, b))
                misalloc = 0.0
                if mat == "mixed_waste" and ("cardboard" in streams or "plastic_film" in streams):
                    if drng.random() < 0.45:
                        misalloc = float(drng.uniform(0.04, 0.32))     # S30: recyclables in mixed waste
                elif mat == "mixed_waste" and drng.random() < 0.25:
                    misalloc = float(drng.uniform(0.04, 0.20))
                spec = dict(device_id=dev_id, device_num=n_dev, customer_id=org_id, site_id=site_id, sector=sector,
                            region=region, material=mat, equipment_class=equip, volume_m3=float(vol),
                            density=density, compressibility=comp, daily_kg=daily, lsig=float(lsig),
                            season=list(sc["season"]), weekday=list(sc["weekday"]), open_days=list(sc["open_days"]),
                            hours=list(sc["hours"]), holiday_mode=sc["holiday_mode"], outdoor=outdoor,
                            has_weight_sensor=has_w, policy=policy, operator_id=operator, billable_km=km,
                            act_from_day=act_from, act_to_day=act_to, max_days=int(m["max_days_between"]),
                            input_event_kg=float(m["input_event_kg"]), contam_base=site_contam_base.get(mat, 0.0),
                            misalloc_share=misalloc, cap_mass_kg=float(capm), credit_eligible=bool(m["credit_eligible"]),
                            moisture_sensitive=bool(m["moisture_sensitive"]), base_moisture=float(m["base_moisture_pct"]),
                            daily_density_cv=float(m["daily_density_cv"]), episodes={})
                specs[dev_id] = spec
                dev_rows.append({"device_id": dev_id, "site_id": site_id, "customer_id": org_id,
                                 "equipment_class": equip, "container_volume_m3": float(vol),
                                 "material_stream": mat, "commissioned_on": commissioned,
                                 "lifecycle_status": status,
                                 "active_from": tb.dates[act_from] if act_from < tb.n_days else None,
                                 "active_to": tb.dates[act_to - 1] if act_to < tb.n_days else None,
                                 "weight_measurement": "INTEGRATED_SIMULATED" if has_w else "NONE",
                                 "fill_measurement": "SIMULATED_FILL_ESTIMATE",
                                 "collection_policy": pol,
                                 "fixed_schedule_per_week": freq if pol != "ON_CALL" else None,
                                 "fixed_schedule_weekdays": ",".join(str(x) for x in wd) if pol != "ON_CALL" else None,
                                 "on_call_threshold_pct": policy["threshold_pct"] if pol == "ON_CALL" else None,
                                 "hybrid_skip_below_pct": policy["skip_below_pct"] if pol == "HYBRID" else None,
                                 "operator_id": operator, "synthetic": True})

    orgs = pd.DataFrame(org_rows)
    sites = pd.DataFrame(site_rows)
    devices = pd.DataFrame(dev_rows)
    # drop sites that ended with zero devices (target reached mid-site)
    sites = sites[sites.site_id.isin(devices.site_id)].reset_index(drop=True)
    orgs = orgs[orgs.customer_id.isin(devices.customer_id)].reset_index(drop=True)
    orgs["n_sites"] = orgs.customer_id.map(sites.groupby("customer_id").size())

    price_index = _build_price_index(tb, A, seed, P)
    contracts, versions = _build_contracts(cfg, tb, specs, sites, intensity)
    dev_contract = contracts.set_index("device_id").contract_id
    devices["contract_id"] = devices.device_id.map(dev_contract)
    for d, s in specs.items():
        s["contract_id"] = dev_contract[d]

    site_calendar, site_open = _build_site_calendars(cfg, tb, sites, intensity)
    return World(tb, orgs, sites, devices, operators, vehicles, facilities, contracts, versions, price_index,
                 site_calendar, regions, specs, site_open)


def _weekday_set(freq: float, rng) -> list:
    if freq >= 5:
        return [0, 1, 2, 3, 4]
    if freq >= 3:
        return [0, 2, 4]
    if freq >= 2:
        return [[0, 3], [1, 4]][int(rng.integers(2))]
    return [int(rng.integers(0, 5))]


def _build_contracts(cfg, tb: TimeBase, specs: dict, sites: pd.DataFrame, intensity: float):
    A = cfg.assumptions
    C = A["contracts"]
    seed = cfg.seed
    c_rows, v_rows = [], []
    site_km = sites.set_index("site_id").billable_round_trip_km
    for k, (dev_id, s) in enumerate(specs.items()):
        crng = rng_for(seed, "contract", dev_id)
        cid = f"CTR-{k + 1:05d}"
        mat = s["material"]
        m = A["materials"][mat]
        model = _choice_weighted(crng, C["pricing_model_mix"])
        exp_t = 0.85 * s["cap_mass_kg"] / 1000.0
        bench_t = 0.80 * s["cap_mass_kg"] / 1000.0
        lift = crng.uniform(*C["lift_fee_eur"]) * (0.85 + 0.01 * s["volume_m3"])
        per_km = crng.uniform(*C["per_km_eur"])
        free_km = int(crng.choice([0, 0, 10, 20, 30]))
        fuel_bp = int(crng.choice([0, 0, 300, 450, 600, 750, 900]))
        proc = crng.uniform(*m["processing_fee"]) if m["processing_fee"][1] > 0 else 0.0
        lift_c = haul_c = proc_c = min_c = 0
        if model == "FIXED_PER_LIFT":
            lift_c = eur_to_cents(lift + proc * exp_t * crng.uniform(0.9, 1.1))
        elif model == "PER_TONNE":
            haul_c = eur_to_cents(lift / max(exp_t, 0.3) * crng.uniform(0.85, 1.2))
            proc_c = eur_to_cents(proc)
            min_c = eur_to_cents(crng.uniform(*C["min_charge_eur"]))
        else:
            lift_c = eur_to_cents(lift)
            proc_c = eur_to_cents(proc)
            if model == "HYBRID_MIN":
                min_c = eur_to_cents(crng.uniform(*C["min_charge_eur"]))
        share_bp = 0
        if s["credit_eligible"] and crng.random() < 0.8:
            share_bp = int(round(crng.uniform(*C["credit_share_bp"]) / 100) * 100)
        km = int(site_km[s["site_id"]])
        remote_c = eur_to_cents(A["regions"][s["region"]]["remote_surcharge"])
        base = dict(pricing_model=model, lift_fee_cents=lift_c, per_km_cents=eur_to_cents(per_km), free_km=free_km,
                    contract_km=km, remote_surcharge_cents=remote_c, fuel_surcharge_bp=fuel_bp,
                    haul_fee_cents_per_t=haul_c, processing_fee_cents_per_t=proc_c, min_charge_cents=min_c,
                    credit_share_bp=share_bp, credit_floor_cents_per_t=0,
                    contamination_penalty_cents=eur_to_cents(crng.uniform(*C["contamination_penalty_eur"])) if s["credit_eligible"] else 0,
                    rejection_fee_cents_per_t=eur_to_cents(crng.uniform(120, 160)) if s["credit_eligible"] else 0,
                    cancellation_fee_cents=eur_to_cents(crng.uniform(*C["cancellation_fee_eur"])),
                    wasted_trip_fee_cents=eur_to_cents(crng.uniform(*C["wasted_trip_fee_eur"])),
                    side_waste_fee_cents=eur_to_cents(crng.uniform(*C["side_waste_fee_eur"])),
                    emergency_surcharge_cents=eur_to_cents(crng.uniform(*C["emergency_surcharge_eur"])),
                    rental_cents_per_month=eur_to_cents(crng.choice([0, 0, 1]) * crng.uniform(*C["rental_eur_month"])),
                    default_weight_kg=int(round(0.6 * s["cap_mass_kg"] / 10) * 10))
        # contract benchmark: logistics cost per tonne at a well-run 85 % fill, times a tolerance
        transport_c = max(0, km - free_km) * base["per_km_cents"]
        logi = (lift_c + transport_c + remote_c) * (1 + fuel_bp / 10000) + haul_c * bench_t
        if model == "PER_TONNE":
            logi = max(logi, min_c)
        base["target_collection_cost_cents_per_t"] = int(round(logi / max(bench_t, 0.05) *
                                                               crng.uniform(*C["benchmark_eur_per_t_multiplier"])))
        start = tb.start - dt.timedelta(days=int(crng.integers(60, 2000)))
        c_rows.append({"contract_id": cid, "customer_id": s["customer_id"], "site_id": s["site_id"],
                       "device_id": dev_id, "material_stream": mat, "operator_id": s["operator_id"],
                       "pricing_model_initial": model, "contract_start": start, "notice_period_days": int(crng.choice([30, 60, 90])),
                       "price_index_id": INDEX_ID.get(mat), "synthetic": True,
                       "note": CONTRACT_NOTE})
        # versions: annual escalation each 1 Jan, optional mid-period amendment (S23)
        boundaries = [start]
        for y in range(tb.start.year + 1, tb.dates[-1].year + 1):
            d = dt.date(y, 1, 1)
            if tb.start < d <= tb.dates[-1]:
                boundaries.append(d)
        amend = None
        if crng.random() < C["midyear_amendment_prob"] * intensity and tb.n_days > 60:
            amend = tb.start + dt.timedelta(days=int(crng.integers(30, tb.n_days - 20)))
            if amend not in boundaries:
                boundaries.append(amend)
        boundaries = sorted(set(boundaries))
        cur = dict(base)
        for vi, b in enumerate(boundaries):
            reason = "INITIAL"
            if vi > 0:
                if b == amend:
                    kind = crng.choice(["LIFT_FEE", "FUEL", "CREDIT_SHARE", "PROCESSING", "MIN_CHARGE"])
                    reason = f"AMENDMENT_{kind}"
                    if kind == "LIFT_FEE" and cur["lift_fee_cents"]:
                        cur["lift_fee_cents"] = int(round(cur["lift_fee_cents"] * crng.uniform(1.06, 1.18)))
                    elif kind == "FUEL":
                        cur["fuel_surcharge_bp"] = int(crng.choice([300, 600, 900, 1200]))
                    elif kind == "CREDIT_SHARE" and cur["credit_share_bp"]:
                        cur["credit_share_bp"] = int(max(4000, cur["credit_share_bp"] - 1500))
                    elif kind == "PROCESSING" and cur["processing_fee_cents_per_t"]:
                        cur["processing_fee_cents_per_t"] = int(round(cur["processing_fee_cents_per_t"] * crng.uniform(1.05, 1.15)))
                    else:
                        cur["min_charge_cents"] = int(round(max(cur["min_charge_cents"], 12000) * crng.uniform(1.05, 1.2)))
                        reason = "AMENDMENT_MIN_CHARGE"
                else:
                    reason = "ANNUAL_INDEXATION"
                    esc = 1 + crng.uniform(*C["annual_escalation_pct"]) / 100
                    for kf in ("lift_fee_cents", "haul_fee_cents_per_t", "processing_fee_cents_per_t", "min_charge_cents",
                               "per_km_cents", "rental_cents_per_month", "target_collection_cost_cents_per_t"):
                        cur[kf] = int(round(cur[kf] * esc))
            v_end = boundaries[vi + 1] if vi + 1 < len(boundaries) else None
            v_rows.append({"contract_version_id": f"{cid}-V{vi + 1}", "contract_id": cid, "version_no": vi + 1,
                           "effective_from": b, "effective_to": v_end, "change_reason": reason, **cur})
    return pd.DataFrame(c_rows), pd.DataFrame(v_rows)


def _build_site_calendars(cfg, tb: TimeBase, sites: pd.DataFrame, intensity: float):
    A = cfg.assumptions
    rows = []
    site_open = {}
    for r in sites.itertuples(index=False):
        sc = A["sectors"][r.sector]
        crng = rng_for(cfg.seed, "calendar", r.site_id)
        open_d = np.array([bool(sc["open_days"][w]) for w in tb.weekday_d])
        oh = np.full(tb.n_days, sc["hours"][0], dtype=np.int8)
        ch = np.full(tb.n_days, sc["hours"][1], dtype=np.int8)
        reason = [None if o else "WEEKLY_CLOSED" for o in open_d]
        activity = np.ones(tb.n_days)
        for i, d in enumerate(tb.dates):
            if tb.holiday_d[i]:
                name = tb.holiday_name_d[i]
                if sc["holiday_mode"] == "closed" or name in ("Christmas Day",):
                    if sc["holiday_mode"] != "peak":
                        open_d[i] = False
                        reason[i] = "PUBLIC_HOLIDAY"
                elif sc["holiday_mode"] == "reduced":
                    ch[i] = min(ch[i], oh[i] + 6)
                    activity[i] = 0.6
                elif sc["holiday_mode"] == "peak":
                    activity[i] = 1.2
        if "summer_shutdown_weeks" in sc and crng.random() < 0.7:
            w0, w1 = sc["summer_shutdown_weeks"]
            w0 += int(crng.integers(0, 2))
            for i in range(tb.n_days):
                if tb.month_d[i] in (6, 7, 8) and w0 <= tb.isoweek_d[i] < w1:
                    open_d[i] = False
                    reason[i] = "SUMMER_SHUTDOWN"
        # S11: planned site closures (renovation / inventory), 1-4 weeks
        if crng.random() < 0.12 * intensity and tb.n_days > 60:
            c0 = int(crng.integers(10, tb.n_days - 35))
            c1 = c0 + int(crng.integers(5, 29))
            for i in range(c0, min(c1, tb.n_days)):
                open_d[i] = False
                reason[i] = "PLANNED_CLOSURE"
        site_open[r.site_id] = (open_d, oh, ch, reason, activity)
        for i, d in enumerate(tb.dates):
            rows.append((r.site_id, d, bool(open_d[i]), int(oh[i]) if open_d[i] else None,
                         int(ch[i]) if open_d[i] else None, reason[i], tb.holiday_name_d[i]))
    cal = pd.DataFrame(rows, columns=["site_id", "date", "is_open", "open_hour_local", "close_hour_local",
                                      "closure_reason", "public_holiday_name"])
    return cal, site_open
