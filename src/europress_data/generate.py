"""CLI: python -m europress_data.generate --profile competition --seed 12345 [--workers 2]

The official Since AI packages are generated with organiser-held seeds (--seed-file); the public manifest then
records only a SHA-256 commitment of the seed, so the private evaluation data cannot be regenerated from the
public package. Any other seed produces a statistically equivalent but different synthetic world."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from . import DATASET_STATUS, GENERATOR_VERSION
from .config import canonical_hash, load_config
from .export import dir_size, enforce_schemas, finalize, manifest, route, safe_rmtree, to_frame, write_parquet
from .pipeline import make_ctx, run_chunk
from .rng import rng_for
from .scenarios import SCENARIOS, build_weather
from .timebase import build_timebase
from .world import INDEX_ID, build_world

_G = {}
H = 3_600_000

PUBLIC_WB_COLS = ["ticket_id", "weighing_event_id", "operator_id", "operator_job_ref", "vehicle_id", "facility_id",
                  "arrival_at", "gross_kg", "tare_kg", "tare_method", "net_kg", "allocated_net_kg", "allocation_method",
                  "loads_on_vehicle", "material_declared", "published_at"]
PUBLIC_QA_COLS = ["quality_assessment_id", "ticket_id", "operator_id", "assessed_at", "published_at", "material_declared",
                  "contamination_pct_est", "grade", "rejected", "remark_code"]


def assign_splits(world, cfg) -> dict:
    frac = float(cfg.profile.get("holdout_org_fraction", 0.0))
    dev_split = {d: "public" for d in world.devices.device_id}
    if frac <= 0:
        return dev_split
    rng = rng_for(cfg.seed, "split")
    orgs = world.devices.groupby("customer_id").size()
    total = len(world.devices)
    order = list(orgs.index)
    rng.shuffle(order)
    chosen, n = [], 0
    for o in order:
        if orgs[o] > 0.08 * total:
            continue
        if n >= frac * total:
            break
        chosen.append(o)
        n += orgs[o]
    hold = set(world.devices[world.devices.customer_id.isin(chosen)].device_id)
    for d in hold:
        dev_split[d] = "holdout"
    return dev_split


def _bounds(tb, profile):
    out = {}
    for name, (a, b) in profile["label_periods"].items():
        ta = pd.Timestamp(a).tz_localize(tb.tz).value // 10 ** 6
        tbb = pd.Timestamp(b).tz_localize(tb.tz).value // 10 ** 6
        out[name] = (ta, tbb)
    return out


def _period(ms, bounds):
    ms = np.asarray(ms, dtype="float64")
    out = np.full(ms.shape, "outside", dtype=object)
    for name, (a, b) in bounds.items():
        out[(ms >= a) & (ms < b)] = name
    return out


def _daily_summary(tel: pd.DataFrame, tz: str) -> pd.DataFrame:
    if tel.empty:
        return pd.DataFrame()
    t = tel.sort_values(["device_id", "received_at"]).drop_duplicates("message_id", keep="first")
    t = t.assign(date=t.measured_at.dt.tz_convert(tz).dt.date)
    t = t.sort_values(["device_id", "measured_at"])
    valid = t.quality_flag.isin(["VALID", "LOW_CONFIDENCE"])
    t = t.assign(mass_valid=t.mass_kg.where(valid), _down=(t.operational_state == "DOWN").astype(int),
                 _full=(t.operational_state == "FULL").astype(int), _buf=(t.delivery_mode == "BUFFERED").astype(int))
    g = t.groupby(["device_id", "date"], sort=True)
    d = pd.DataFrame({
        "n_messages": g.size(),
        "fill_pct_first": g.fill_pct.first(), "fill_pct_last": g.fill_pct.last(),
        "fill_pct_max": g.fill_pct.max(), "fill_pct_min": g.fill_pct.min(),
        "mass_kg_last_valid": g.mass_valid.last(), "mass_kg_max_valid": g.mass_valid.max(),
        "n_valid_mass": g.mass_valid.count(),
        "compaction_cycles": g.compaction_cycles.sum(),
        "hours_down": g._down.sum(), "hours_full": g._full.sum(), "n_buffered": g._buf.sum(),
    }).reset_index()
    d["data_completeness_pct"] = (100 * d.n_messages / 24).clip(upper=100).round(1)
    d["fill_pct_first"] = d.fill_pct_first.astype("float32")
    return d


def _process_chunk(k: int, devs: list) -> dict:
    cfg, world, ctx = _G["cfg"], _G["world"], _G["ctx"]
    split_of, ext, bounds = _G["split"], _G["extraction_ms"], _G["bounds"]
    stg, pub, priv = _G["staging"], _G["public"], _G["private"]
    tb = world.tb
    T = run_chunk(cfg, world, ctx, devs, split_of, ext, bounds)
    stats = {"chunk": k, "devices": len(devs)}
    contract_split = {world.specs[d]["contract_id"]: split_of[d] for d in devs}
    # --- telemetry (directly partitioned) ---
    tel = finalize(to_frame(T.pop("telemetry_hourly")))
    if not tel.empty:
        tel["_split"] = tel.device_id.map(split_of)
        mon = tel.measured_at.dt.tz_convert(tb.tz).dt.strftime("%Y-%m")
        for (sp, mk), part in tel.groupby([tel._split, mon]):
            base = pub if sp == "public" else priv / "holdout_full"
            write_parquet(part.drop(columns=["_split"]), base / "telemetry" / "telemetry_hourly" / f"month={mk}" / f"part-{k:05d}.parquet")
        ds = _daily_summary(tel.drop(columns=["_split"]), tb.tz)
        ds["_split"] = ds.device_id.map(split_of)
        write_parquet(ds, stg / "telemetry_daily_summary" / f"chunk-{k:05d}.parquet")
        stats["telemetry_rows"] = len(tel)
    th = to_frame(T.pop("truth_hourly_state", []))
    if not th.empty:
        th = finalize(th)
        mon = th.hour_start_at.dt.tz_convert(tb.tz).dt.strftime("%Y-%m")
        for mk, part in th.groupby(mon):
            write_parquet(part, priv / "truth" / "truth_hourly_state" / f"month={mk}" / f"part-{k:05d}.parquet")
    # --- other tables -> staging ---
    # evaluation time of a collection = when it is fully observable: max(event, issue of the invoice billing it).
    # Charged but not yet invoiced at extraction -> extraction time. This one timestamp defines its split.
    inv_issue = {(i["contract_id"], i["billing_period"]): i["issued_ms"] for i in T.get("invoices", [])}
    coll_eval_ms = {}
    for e in T.get("reference_economics", []):
        b = inv_issue.get((e["contract_id"], str(e["service_date"])[:7]))
        if e["expected_invoice_amount_eur"] == 0:
            coll_eval_ms[e["collection_id"]] = e["event_ms"]
        elif b is None:
            coll_eval_ms[e["collection_id"]] = ext
        else:
            coll_eval_ms[e["collection_id"]] = max(e["event_ms"], b)
    for name, rows in T.items():
        df = to_frame(rows)
        if df.empty:
            continue
        if name in ("anomaly_labels", "reference_economics"):
            cid = df["collection_id"] if name == "reference_economics" else df["entity_id"].where(df["entity_type"] == "collection")
            ev = cid.map(coll_eval_ms)
            df["eval_ms"] = ev.where(ev.notna(), df["event_ms"]).astype("int64")
            df["_period"] = _period(df["eval_ms"].astype("float64"), bounds)
            df["_bill_period"] = df["_period"]
        if name in ("invoices",):
            df["_split"] = df.contract_id.map(contract_split)
            df["_period"] = _period(df["issued_ms"], bounds)
        elif name == "invoice_lines":
            df["_split"] = ("CTR-" + df.invoice_id.str[4:9]).map(contract_split)
            df = df.drop(columns=["_collection_id"])
        elif name == "invoice_line_labels":
            df["_split"] = ("CTR-" + df.invoice_id.str[4:9]).map(contract_split)
        elif "device_id" in df.columns:
            df["_split"] = df.device_id.map(split_of)
        elif "collection_id" in df.columns:
            df["_split"] = ("CMP-" + df.collection_id.str[4:9]).map(split_of)
        df = finalize(df)
        write_parquet(df, stg / name / f"chunk-{k:05d}.parquet")
    return stats


def _chunks(world, size: int) -> list:
    out, cur = [], []
    for org, g in world.devices.groupby("customer_id", sort=True):
        cur.extend(g.device_id.tolist())
        if len(cur) >= size:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def seed_commitment(profile: str, seed: int) -> str:
    import hashlib
    return hashlib.sha256(f"europress-smve:{profile}:{int(seed)}".encode()).hexdigest()


def generate(cfg, workers: int = 1, verbose: bool = True, seed_disclosed: bool = True) -> dict:
    t0 = time.time()
    P = cfg.profile
    tb = build_timebase(P["start_date"], int(P["n_days"]), cfg.assumptions["timezone"])
    world = build_world(cfg, tb)
    weather = build_weather(tb, list(cfg.assumptions["regions"]), cfg.seed)
    ctx = make_ctx(cfg, world, weather)
    split = assign_splits(world, cfg)
    out = Path(cfg.out_dir)
    safe_rmtree(out)
    stg, pub, priv = out / "_staging", out / "public", out / "private_evaluation"
    end_local = pd.Timestamp(tb.dates[-1] + dt.timedelta(days=15)).tz_localize(tb.tz) + pd.Timedelta(hours=12)
    extraction_ms = int(end_local.value // 10 ** 6)
    bounds = _bounds(tb, P)
    _G.update(cfg=cfg, world=world, ctx=ctx, split=split, extraction_ms=extraction_ms, bounds=bounds,
              staging=stg, public=pub, private=priv)
    chunks = _chunks(world, int(P.get("chunk_devices", 100)))
    if verbose:
        print(f"[{cfg.name}] world: {len(world.orgs)} customers, {len(world.sites)} sites, {len(world.devices)} devices, "
              f"{tb.n_hours} hours; {len(chunks)} chunks; workers={workers}", flush=True)
    stats = []
    if workers > 1:
        import multiprocessing as mp
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as ex:
            for s in ex.map(_process_chunk, range(len(chunks)), chunks):
                stats.append(s)
                if verbose:
                    print(f"  chunk {s['chunk'] + 1}/{len(chunks)} done ({time.time() - t0:.0f}s)", flush=True)
    else:
        for k, devs in enumerate(chunks):
            stats.append(_process_chunk(k, devs))
            if verbose:
                print(f"  chunk {k + 1}/{len(chunks)} done ({time.time() - t0:.0f}s)", flush=True)
    t_sim = time.time() - t0
    counts = finalize_outputs(cfg, world, split, stg, pub, priv, extraction_ms, bounds)
    safe_rmtree(stg)
    from .operator_tasks import write_all as write_operator_tasks
    counts.update(write_operator_tasks(cfg, world, split, out, extraction_ms))
    if verbose:
        print(f"[{cfg.name}] operator scorecard + operator/contract action cases written ({time.time() - t0:.0f}s)", flush=True)
    problems = enforce_schemas(out)
    if problems:
        raise RuntimeError("schema problems:\n" + "\n".join(problems))
    from .golden import write as write_golden
    golden_counts = write_golden(cfg.name, out)
    from .docs_build import data_dictionary
    dd = json.dumps(data_dictionary(), indent=1)
    notice_pub = (f"{DATASET_STATUS}\nEuropress SMART Material Value Engine, Since AI Hackathon 2026 ({cfg.name} profile).\n"
                  "No Europress customer data, device readings, product specifications, contracts or validated prices.\n"
                  "All customers, sites, contracts, costs and invoices are invented. Not evidence of real savings or of weighing feasibility.\n"
                  "Europress is currently not a party to waste transport or treatment. Tariffs, processing fees and material credits are\n"
                  "agreed between the customer and the waste operator. All prices in this dataset are hypothetical.\n"
                  "The dataset depicts a future scenario in which most devices have integrated weighing.\n"
                  "Documentation: see the repository docs/ (README, QUICKSTART_FOR_BUILDERS, DATA_DICTIONARY, ECONOMIC_MODEL).\n")
    for root, extra in ((pub, ""), (priv, "\n*** PRIVATE EVALUATION PACKAGE — NOT FOR DISTRIBUTION TO PARTICIPANTS ***\n"
                                         "Contains simulator truth, test-period labels, hold-out customers and private golden cases.\n")):
        if root.exists():
            (root / "metadata").mkdir(parents=True, exist_ok=True)
            (root / "metadata" / "data_dictionary.json").write_text(dd)
            (root / "README_FIRST.txt").write_text(extra + notice_pub)
    public_cfg_hash = canonical_hash({"profile": cfg.profile, "assumptions": cfg.assumptions})
    info = {"generator_version": GENERATOR_VERSION, "dataset_status": DATASET_STATUS, "profile": cfg.name,
            "seed": cfg.seed, "seed_disclosed": bool(seed_disclosed), "seed_commitment_sha256": seed_commitment(cfg.name, cfg.seed),
            "config_hash": public_cfg_hash, "config_hash_with_seed": cfg.config_hash,
            "start_date": P["start_date"], "n_days": P["n_days"],
            "extraction_time_utc": pd.Timestamp(extraction_ms, unit="ms", tz="UTC").isoformat(),
            "label_periods": P["label_periods"], "synthetic": True, "contains_real_customer_data": False,
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
            "runtime_seconds": round(time.time() - t0, 1), "simulation_seconds": round(t_sim, 1),
            "n_customers_public": int(world.devices[world.devices.device_id.map(split) == "public"].customer_id.nunique()),
            "n_devices_public": int(sum(1 for v in split.values() if v == "public")),
            "n_devices_holdout": int(sum(1 for v in split.values() if v == "holdout")),
            "row_counts": counts, "golden_cases": golden_counts}
    pub_info = {**info, "row_counts": {k: v for k, v in counts.items() if not str(k).startswith("private_evaluation")},
                "golden_cases": {"public": golden_counts.get("public")}}
    if not seed_disclosed:
        # leak protection: the public package must not allow regenerating the private evaluation data
        pub_info["seed"] = "UNDISCLOSED (organiser-held; see seed_commitment_sha256)"
        pub_info.pop("config_hash_with_seed", None)
    for root, inf in ((pub, pub_info), (priv, info)):
        if root.exists():
            manifest(root, {**inf, "package": root.name})
    info["bytes_public"] = dir_size(pub)
    info["bytes_private"] = dir_size(priv) if priv.exists() else 0
    with open(out / "generation_summary.json", "w") as fh:
        json.dump(info, fh, indent=2, default=str)
    if verbose:
        print(f"[{cfg.name}] done in {info['runtime_seconds']}s; public {info['bytes_public'] / 1e6:.1f} MB, "
              f"private {info['bytes_private'] / 1e6:.1f} MB", flush=True)
    return info


def finalize_outputs(cfg, world, split, stg, pub, priv, extraction_ms, bounds) -> dict:
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    P = cfg.profile
    write_csv = bool(P.get("write_csv"))
    counts = {}
    holdout_devs = [d for d, s in split.items() if s == "holdout"]
    hf = priv / "holdout_full"

    def g(name):
        return str(stg / name / "*.parquet")

    def exists(name):
        return (stg / name).exists()

    def r(name, dest, where="TRUE", order=None, key=None, csv_rel=None):
        if not exists(name):
            return
        csv = (pub / "csv" / csv_rel) if (write_csv and csv_rel) else None
        counts[key or str(dest.relative_to(cfg.out_dir))] = route(con, g(name), dest, where, order, csv)

    pubw, holdw = "_split = 'public'", "_split = 'holdout'"
    # operations / finance
    for name, sub, order in [("collection_events", "operations", "device_id, scheduled_at, collection_id"),
                             ("maintenance_work_orders", "operations", "device_id, started_at, work_order_id"),
                             ("invoices", "finance", "contract_id, billing_period"),
                             ("invoice_lines", "finance", "invoice_id, line_no"),
                             ("telemetry_daily_summary", "telemetry", "device_id, date")]:
        r(name, pub / sub / f"{name}.parquet", pubw, order, csv_rel=f"{name}.csv")
        if holdout_devs:
            r(name, hf / sub / f"{name}.parquet", holdw, order)
    if exists("weighbridge_all"):
        cols = ", ".join(PUBLIC_WB_COLS)
        for where, dest in [(f"{pubw} AND public", pub / "operations" / "weighbridge_tickets.parquet"),
                            (f"{holdw} AND public", hf / "operations" / "weighbridge_tickets.parquet")]:
            if "holdout" in where and not holdout_devs:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            con.execute(f"COPY (SELECT {cols} FROM read_parquet('{g('weighbridge_all')}', union_by_name=true) WHERE {where} "
                        f"ORDER BY arrival_at, ticket_id) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            counts[str(dest.relative_to(cfg.out_dir))] = con.execute(f"SELECT count(*) FROM '{dest}'").fetchone()[0]
            if write_csv and "public" in str(dest.parent.parent.name):
                con.execute(f"COPY (SELECT * FROM '{dest}') TO '{pub / 'csv' / 'weighbridge_tickets.csv'}' (HEADER)")
        r("weighbridge_all", priv / "truth" / "weighbridge_all.parquet", order="arrival_at, ticket_id")
    if exists("quality_all"):
        cols = ", ".join(PUBLIC_QA_COLS)
        qsrc = g("quality_all")
        for where, dest in [(f"{pubw} AND public", pub / "operations" / "quality_assessments.parquet"),
                            (f"{holdw} AND public", hf / "operations" / "quality_assessments.parquet")]:
            if "holdout" in where and not holdout_devs:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            # quality rows carry no device_id: derive split from collection id -> device
            con.execute(f"COPY (SELECT {cols} FROM read_parquet('{qsrc}', union_by_name=true) WHERE {where} "
                        f"ORDER BY assessed_at, quality_assessment_id) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            counts[str(dest.relative_to(cfg.out_dir))] = con.execute(f"SELECT count(*) FROM '{dest}'").fetchone()[0]
            if write_csv and "holdout" not in where:
                con.execute(f"COPY (SELECT * FROM '{dest}') TO '{pub / 'csv' / 'quality_assessments.csv'}' (HEADER)")
        r("quality_all", priv / "truth" / "quality_all.parquet", order="assessed_at, quality_assessment_id")
    # truth tables
    for name in ("truth_collections", "truth_sensor_episodes", "truth_device", "invoice_line_labels"):
        r(name, priv / "truth" / f"{name}.parquet")
    # labels: dev (train+validation, public devices) vs test (+ all holdout)
    val_end_ms = bounds["validation"][1]
    # public dev labels: event AND its billing in train/validation; device-period labels must also have ended
    dev_w = (f"{pubw} AND _period IN ('train','validation') AND _bill_period IN ('train','validation')")
    dev_lab_w = dev_w + (f" AND (entity_type NOT IN ('device_period','device') OR (end_at IS NOT NULL AND end_at < epoch_ms({val_end_ms})))")
    test_w = f"NOT ({dev_w})"
    r("anomaly_labels", pub / "labels_dev" / "anomaly_labels.parquet", dev_lab_w, csv_rel="labels_dev_anomaly_labels.csv")
    r("anomaly_labels", priv / "labels_test" / "anomaly_labels.parquet", f"NOT ({dev_lab_w})")
    r("reference_economics", pub / "labels_dev" / "reference_economics.parquet", dev_w, csv_rel="labels_dev_reference_economics.csv")
    r("reference_economics", priv / "labels_test" / "reference_economics.parquet", test_w)
    if exists("reference_charge_lines"):
        for where, dest in [(dev_w, pub / "labels_dev" / "reference_charge_lines.parquet"),
                            (test_w, priv / "labels_test" / "reference_charge_lines.parquet")]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            con.execute(f"""COPY (SELECT * EXCLUDE (_split, _period, _bill_period) FROM (SELECT l.* EXCLUDE (_split), e._split, e._period, e._bill_period
                        FROM read_parquet('{g('reference_charge_lines')}') l JOIN
                        (SELECT collection_id, _split, _period, _bill_period FROM read_parquet('{g('reference_economics')}')) e USING (collection_id))
                        WHERE {where} ORDER BY collection_id, line_no) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
            counts[str(dest.relative_to(cfg.out_dir))] = con.execute(f"SELECT count(*) FROM '{dest}'").fetchone()[0]
    # aggregated reference economics: device x month (site / material / customer levels are group-bys of this)
    if exists("reference_economics"):
        con2 = duckdb.connect()
        con2.register("dev_ref", world.devices[["device_id", "site_id", "customer_id", "material_stream"]])
        for where, dest in [(dev_w, pub / "labels_dev" / "reference_economics_monthly.parquet"),
                            (test_w, priv / "labels_test" / "reference_economics_monthly.parquet")]:
            con2.execute(f"""COPY (SELECT e.device_id, d.site_id, d.customer_id, d.material_stream, e.contract_id,
                strftime(e.service_date, '%Y-%m') AS month, count(*) AS n_events,
                sum(CASE WHEN e.status IN ('COMPLETED','PARTIAL') THEN 1 ELSE 0 END) AS n_lifts,
                sum(e.billing_mass_kg) AS billing_mass_kg,
                round(sum(e.collection_cost_eur), 2) AS collection_cost_eur, round(sum(e.processing_cost_eur), 2) AS processing_cost_eur,
                round(sum(e.penalties_eur), 2) AS penalties_eur, round(sum(e.material_credit_eur), 2) AS material_credit_eur,
                round(sum(e.net_material_contribution_eur), 2) AS net_material_contribution_eur,
                round(sum(e.collection_cost_eur) / nullif(sum(e.billing_mass_kg) / 1000, 0), 2) AS collection_cost_eur_per_t,
                round(-sum(e.net_material_contribution_eur) / nullif(sum(e.billing_mass_kg) / 1000, 0), 2) AS total_cost_eur_per_t
                FROM read_parquet('{g('reference_economics')}') e JOIN dev_ref d USING (device_id) WHERE {where}
                GROUP BY ALL ORDER BY e.device_id, month) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
            counts[str(dest.relative_to(cfg.out_dir))] = con2.execute(f"SELECT count(*) FROM '{dest}'").fetchone()[0]
        con2.close()
    # decisions
    if exists("decision_cases"):
        r("decision_cases", pub / "benchmark" / "decision_cases.parquet", "split IN ('train','validation','test')", "decision_at, case_id",
          csv_rel="decision_cases.csv")
        r("decision_cases", priv / "benchmark" / "decision_cases_private.parquet", "split = 'test_private'", "decision_at, case_id")
        r("decision_truth", pub / "labels_dev" / "decision_truth.parquet", "split IN ('train','validation')", csv_rel="labels_dev_decision_truth.csv")
        r("decision_truth", priv / "labels_test" / "decision_truth.parquet", "split IN ('test','test_private')")
        r("decision_outcomes", pub / "labels_dev" / "decision_outcomes.parquet", "split IN ('train','validation')", csv_rel="labels_dev_decision_outcomes.csv")
        r("decision_outcomes", priv / "labels_test" / "decision_outcomes.parquet", "split IN ('test','test_private')")
    # benchmark entity lists for test period (public devices) — no answers
    if exists("collection_events"):
        dest = pub / "benchmark" / "task_ab_test_collections.parquet"
        a, b = bounds["test"]
        con.execute(f"""COPY (SELECT collection_id, device_id, status FROM read_parquet('{g('collection_events')}')
                    WHERE {pubw} AND coalesce(actual_at, scheduled_at) >= epoch_ms({a}) AND coalesce(actual_at, scheduled_at) < epoch_ms({b})
                    ORDER BY collection_id) TO '{dest}' (FORMAT PARQUET)""")
        counts[str(dest.relative_to(cfg.out_dir))] = con.execute(f"SELECT count(*) FROM '{dest}'").fetchone()[0]
        dest = pub / "benchmark" / "task_b_test_invoice_lines.parquet"
        con.execute(f"""COPY (SELECT l.invoice_line_id, l.invoice_id FROM read_parquet('{g('invoice_lines')}') l
                    JOIN read_parquet('{g('invoices')}') i USING (invoice_id)
                    WHERE l._split='public' AND i.issued_at >= epoch_ms({a}) AND i.issued_at < epoch_ms({b}) ORDER BY 1)
                    TO '{dest}' (FORMAT PARQUET)""")
        counts[str(dest.relative_to(cfg.out_dir))] = con.execute(f"SELECT count(*) FROM '{dest}'").fetchone()[0]
    if write_csv:
        for src, name in ((pub / "labels_dev" / "reference_charge_lines.parquet", "labels_dev_reference_charge_lines"),
                          (pub / "labels_dev" / "reference_economics_monthly.parquet", "labels_dev_reference_economics_monthly")):
            if src.exists():
                con.execute(f"COPY (SELECT * FROM '{src}') TO '{pub / 'csv' / (name + '.csv')}' (HEADER)")
        tel = pub / "telemetry" / "telemetry_hourly"
        if tel.exists():
            con.execute(f"COPY (SELECT * FROM read_parquet('{tel}/*/*.parquet', hive_partitioning=false) ORDER BY device_id, ingest_seq) "
                        f"TO '{pub / 'csv' / 'telemetry_hourly.csv'}' (HEADER)")
    con.close()
    counts.update(write_reference(cfg, world, split, pub, priv, write_csv))
    if holdout_devs and P.get("private_decision_cutoff"):
        from .sdk import write_snapshot
        snap = write_snapshot(hf, priv / f"holdout_asof_{P['private_decision_cutoff']}", P["private_decision_cutoff"])
        counts.update({str(Path(k).relative_to(cfg.out_dir)): v for k, v in snap.items()})
    write_legacy(cfg, pub) if cfg.name == "quickstart" else None
    if int(P.get("csv_sample_devices", 0) or 0) > 0 and not write_csv:
        counts.update(write_csv_samples(pub, int(P["csv_sample_devices"])))
    return counts


def write_csv_samples(pub: Path, n: int) -> dict:
    """CSV extracts for the first n public devices (all tables joined to those devices) — for spreadsheet users."""
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    out = pub / "csv_samples"
    out.mkdir(parents=True, exist_ok=True)
    devs = [r[0] for r in con.execute(f"SELECT device_id FROM '{pub / 'reference' / 'devices.parquet'}' ORDER BY 1 LIMIT {n}").fetchall()]
    dl = ", ".join(f"'{d}'" for d in devs)
    q = {
        "devices": f"SELECT * FROM '{pub}/reference/devices.parquet' WHERE device_id IN ({dl})",
        "contracts": f"SELECT * FROM '{pub}/reference/contracts.parquet' WHERE device_id IN ({dl})",
        "contract_versions": f"SELECT v.* FROM '{pub}/reference/contract_versions.parquet' v JOIN '{pub}/reference/contracts.parquet' c USING (contract_id) WHERE c.device_id IN ({dl})",
        "telemetry_hourly": f"SELECT * FROM read_parquet('{pub}/telemetry/telemetry_hourly/*/*.parquet', hive_partitioning=false) WHERE device_id IN ({dl}) ORDER BY device_id, ingest_seq",
        "telemetry_daily_summary": f"SELECT * FROM '{pub}/telemetry/telemetry_daily_summary.parquet' WHERE device_id IN ({dl}) ORDER BY 1, 2",
        "collection_events": f"SELECT * FROM '{pub}/operations/collection_events.parquet' WHERE device_id IN ({dl}) ORDER BY device_id, scheduled_at",
        "weighbridge_tickets": f"SELECT w.* FROM '{pub}/operations/weighbridge_tickets.parquet' w JOIN '{pub}/operations/collection_events.parquet' c USING (operator_job_ref) WHERE c.device_id IN ({dl}) ORDER BY w.arrival_at",
        "invoices": f"SELECT i.* FROM '{pub}/finance/invoices.parquet' i JOIN '{pub}/reference/contracts.parquet' c USING (contract_id) WHERE c.device_id IN ({dl}) ORDER BY 1",
        "invoice_lines": f"SELECT l.* FROM '{pub}/finance/invoice_lines.parquet' l JOIN '{pub}/finance/invoices.parquet' i USING (invoice_id) JOIN '{pub}/reference/contracts.parquet' c USING (contract_id) WHERE c.device_id IN ({dl}) ORDER BY 1",
        "price_index_monthly": f"SELECT * FROM '{pub}/reference/price_index_monthly.parquet'",
    }
    counts = {}
    for name, sql in q.items():
        f = out / f"{name}.csv"
        con.execute(f"COPY ({sql}) TO '{f}' (HEADER)")
        counts[f"public/csv_samples/{name}.csv"] = con.execute(f"SELECT count(*) FROM read_csv_auto('{f}')").fetchone()[0]
    con.close()
    return counts


def write_reference(cfg, world, split, pub, priv, write_csv) -> dict:
    A = cfg.assumptions
    counts = {}
    dev_pub = {d for d, s in split.items() if s == "public"}
    cust_pub = set(world.devices[world.devices.device_id.isin(dev_pub)].customer_id)
    site_pub = set(world.devices[world.devices.device_id.isin(dev_pub)].site_id)
    mat = pd.DataFrame([{"material_stream": k, "credit_eligible": v["credit_eligible"],
                         "customer_economics": "CREDIT_ELIGIBLE" if v["credit_eligible"] else "CHARGEABLE",
                         "typical_compacted_density_kg_m3": v["compacted_density"],
                         "max_days_between_collections": v["max_days_between"],
                         "price_index_id": INDEX_ID.get(k),
                         "assumption_note": "ILLUSTRATIVE assumption, not a measured or product value"}
                        for k, v in A["materials"].items()])
    grades = pd.DataFrame([{"grade": g, "max_contamination_pct": v["max_contamination"] * 100,
                            "credit_quality_factor": v["quality_bp"] / 10000,
                            "consequence": {"A": "full credit", "B": "credit x 0.85", "C": "credit x 0.60 + contamination penalty",
                                            "R": "rejected: no credit, reprocessing fee per t"}[g]} for g, v in A["quality_grades"].items()])
    devices = world.devices.copy()
    devices["has_weight_measurement"] = devices.weight_measurement != "NONE"
    inst = devices[["device_id", "site_id", "commissioned_on", "active_to"]].rename(
        columns={"commissioned_on": "installed_on", "active_to": "removed_on"})
    inst.insert(0, "installation_id", "INS-" + inst.device_id.str[4:])
    tables = {
        "reference/customers": (world.orgs, "customer_id", cust_pub),
        "reference/sites": (world.sites, "site_id", site_pub),
        "reference/site_calendar": (world.site_calendar, "site_id", site_pub),
        "reference/devices": (devices, "device_id", dev_pub),
        "reference/device_installations": (inst, "device_id", dev_pub),
        "reference/contracts": (world.contracts, "device_id", dev_pub),
        "reference/contract_versions": (world.contract_versions.merge(world.contracts[["contract_id", "device_id"]]), "device_id", dev_pub),
        "reference/operators": (world.operators, None, None),
        "reference/regions": (world.regions, None, None),
        "reference/price_index_monthly": (world.price_index, None, None),
        "reference/material_classes": (mat, None, None),
        "reference/quality_grade_rules": (grades, None, None),
    }
    for rel, (df, key, keep) in tables.items():
        df = df.copy()
        if key is None:
            parts = [("public", df)] + ([("holdout", df)] if any(v == "holdout" for v in split.values()) else [])
        else:
            parts = [("public", df[df[key].isin(keep)]), ("holdout", df[~df[key].isin(keep)])]
        for sp, part in parts:
            if rel.endswith("contract_versions"):
                part = part.drop(columns=["device_id"])
            if sp == "holdout" and part.empty:
                continue
            base = pub if sp == "public" else priv / "holdout_full"
            write_parquet(part.reset_index(drop=True), base / f"{rel}.parquet")
            counts[f"{'public' if sp == 'public' else 'private_evaluation/holdout_full'}/{rel}.parquet"] = len(part)
            if write_csv and sp == "public":
                (pub / "csv").mkdir(parents=True, exist_ok=True)
                part.to_csv(pub / "csv" / f"{rel.split('/')[-1]}.csv", index=False)
    # sensor registry from staging was routed? (it carries device_id) -> handled here from staging if present
    stg = Path(cfg.out_dir) / "_staging" / "sensor_registry"
    if stg.exists():
        con = duckdb.connect()
        for sp, base in (("public", pub), ("holdout", priv / "holdout_full")):
            if sp == "holdout" and not any(v == "holdout" for v in split.values()):
                continue
            dest = base / "reference" / "sensor_registry.parquet"
            counts[str(dest.relative_to(cfg.out_dir))] = route(con, str(stg / "*.parquet"), dest, f"_split = '{sp}'", "sensor_id",
                                      (pub / "csv" / "sensor_registry.csv") if (write_csv and sp == "public") else None)
        con.close()
    write_parquet(world.vehicles, priv / "truth" / "vehicles.parquet")
    # facilities are operator-side information (Europress review 30.10.2026): private truth only
    write_parquet(world.facilities, priv / "truth" / "facilities.parquet")
    sc = pd.DataFrame(SCENARIOS, columns=["scenario_id", "name", "mechanism", "tables_affected", "label_entity", "description"])
    (pub / "metadata").mkdir(parents=True, exist_ok=True)
    sc.to_csv(pub / "metadata" / "scenario_catalog.csv", index=False)
    return counts


def write_asof_snapshot(cfg, hf: Path, dest: Path, cutoff: str, tb) -> dict:
    """Holdout customers' observable data as known at the decision cutoff (for leak-free Task C scoring)."""
    con = duckdb.connect()
    con.execute("SET TimeZone='UTC'")
    cms = pd.Timestamp(cutoff).tz_localize(tb.tz).value // 10 ** 6
    cut = f"epoch_ms({cms})"
    counts = {}
    rules = {
        "telemetry/telemetry_hourly": f"received_at < {cut}",
        "telemetry/telemetry_daily_summary": f"date < CAST({cut} AT TIME ZONE '{tb.tz}' AS DATE)",
        "operations/collection_events": f"coalesce(actual_at, scheduled_at) < {cut} AND (order_placed_at IS NULL OR order_placed_at < {cut})",
        "operations/weighbridge_tickets": f"published_at < {cut}",
        "operations/quality_assessments": f"published_at < {cut}",
        "operations/maintenance_work_orders": f"reported_at < {cut}",
        "finance/invoices": f"issued_at < {cut}",
    }
    for rel, where in rules.items():
        src = hf / f"{rel}.parquet" if not rel.endswith("telemetry_hourly") else hf / "telemetry" / "telemetry_hourly" / "*" / "*.parquet"
        if not rel.endswith("telemetry_hourly") and not src.exists():
            continue
        d = dest / f"{rel}.parquet"
        d.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY (SELECT * FROM read_parquet('{src}', hive_partitioning=false) WHERE {where} ORDER BY ALL) TO '{d}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        counts[str(d.relative_to(cfg.out_dir))] = con.execute(f"SELECT count(*) FROM '{d}'").fetchone()[0]
    d = dest / "finance" / "invoice_lines.parquet"
    con.execute(f"""COPY (SELECT l.* FROM '{hf / 'finance' / 'invoice_lines.parquet'}' l JOIN '{dest / 'finance' / 'invoices.parquet'}' i
                USING (invoice_id) ORDER BY l.invoice_id, l.line_no) TO '{d}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    counts[str(d.relative_to(cfg.out_dir))] = con.execute(f"SELECT count(*) FROM '{d}'").fetchone()[0]
    for p in (hf / "reference").glob("*.parquet"):
        q = f"SELECT * FROM '{p}'"
        if p.stem == "contract_versions":
            q += f" WHERE effective_from < CAST({cut} AT TIME ZONE '{tb.tz}' AS DATE)"
        if p.stem == "site_calendar":
            q += f" WHERE date < CAST({cut} AT TIME ZONE '{tb.tz}' AS DATE)"
        if p.stem == "price_index_monthly":
            q += f" WHERE published_on < CAST({cut} AT TIME ZONE '{tb.tz}' AS DATE)"
        (dest / "reference").mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY ({q} ORDER BY ALL) TO '{dest / 'reference' / p.name}' (FORMAT PARQUET)")
    con.close()
    return counts


def write_legacy(cfg, pub: Path):
    """Backwards-compatible v0-shaped CSVs for the quickstart (daily readings / pickups / devices)."""
    con = duckdb.connect()
    con.execute("SET TimeZone='Europe/Helsinki'")
    leg = pub / "csv" / "legacy_v0"
    leg.mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY (SELECT d.device_id, d.material_stream AS material_type, d.container_volume_m3 AS capacity_m3,
        s.region_code AS region, d.contract_id, 'SYNTHETIC: invented device' AS note
        FROM '{pub / 'reference' / 'devices.parquet'}' d JOIN '{pub / 'reference' / 'sites.parquet'}' s USING (site_id) ORDER BY 1)
        TO '{leg / 'devices.csv'}' (HEADER)""")
    con.execute(f"""COPY (SELECT ds.device_id, ds.date, d.material_stream AS material_type, d.container_volume_m3 AS capacity_m3,
        ds.fill_pct_last AS fill_pct, ds.mass_kg_last_valid AS assumed_measured_weight_kg,
        CASE WHEN ds.n_valid_mass = 0 THEN 'missing' WHEN ds.n_valid_mass < 18 THEN 'low_confidence' ELSE 'valid' END AS weight_quality,
        (SELECT min(collection_id) FROM '{pub / 'operations' / 'collection_events.parquet'}' c
           WHERE c.device_id = ds.device_id AND CAST(c.actual_at AS DATE) = ds.date AND c.status IN ('COMPLETED','PARTIAL')) AS pickup_event_id
        FROM '{pub / 'telemetry' / 'telemetry_daily_summary.parquet'}' ds JOIN '{pub / 'reference' / 'devices.parquet'}' d USING (device_id)
        ORDER BY 1, 2) TO '{leg / 'daily_sensor_readings.csv'}' (HEADER)""")
    con.execute(f"""COPY (SELECT c.collection_id AS pickup_event_id, c.device_id, CAST(c.actual_at AS DATE) AS date,
        d.material_stream AS material_type, w.allocated_net_kg AS pickup_weight_kg, s.billable_round_trip_km AS transport_distance_km,
        c.status, c.trigger_type
        FROM '{pub / 'operations' / 'collection_events.parquet'}' c JOIN '{pub / 'reference' / 'devices.parquet'}' d USING (device_id)
        JOIN '{pub / 'reference' / 'sites.parquet'}' s ON s.site_id = c.site_id
        LEFT JOIN '{pub / 'operations' / 'weighbridge_tickets.parquet'}' w ON w.operator_job_ref = c.operator_job_ref
        WHERE c.status IN ('COMPLETED','PARTIAL') ORDER BY 1) TO '{leg / 'pickup_events.csv'}' (HEADER)""")
    con.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the Europress SMART Material Value Engine synthetic dataset")
    ap.add_argument("--profile", default="quickstart")
    ap.add_argument("--seed", type=int, default=None, help="any integer; default 20261023 (demo seed, disclosed)")
    ap.add_argument("--seed-file", default=None, help="JSON {profile: seed} with organiser-held seeds (official packages)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--max-devices", type=int, default=None, help="override target_devices (scale tests)")
    ap.add_argument("--days", type=int, default=None, help="override n_days (scale tests)")
    a = ap.parse_args(argv)
    ov = {}
    if a.max_devices:
        ov["target_devices"] = a.max_devices
    if a.days:
        ov["n_days"] = a.days
    disclosed = True
    seed = a.seed if a.seed is not None else 20261023
    if a.seed_file:
        seeds = json.load(open(a.seed_file))
        seed = int(seeds[Path(a.profile).stem if Path(a.profile).exists() else a.profile])
        disclosed = False
    cfg = load_config(a.profile, seed, a.out, ov or None)
    generate(cfg, workers=a.workers, seed_disclosed=disclosed)


if __name__ == "__main__":
    sys.exit(main())
