"""Regenerate the generated documentation from the schema, validation reports and baseline results.
python -m europress_data.docs_build"""
from __future__ import annotations

import json
import re
from pathlib import Path

import duckdb

from .config import ROOT
from .scenarios import SCENARIOS
from .schema import TABLES

DOCS = ROOT / "docs"
REP = ROOT / "reports"

CHALLENGE = {
    "S01": "Separate over-servicing from legitimate early lifts (hygiene, max interval, pre-closure).",
    "S02": "Distinguish operator delay from undersized policy; FULL state is noisy.",
    "S03": "High EUR/t can be structural (small stream, minimum charge) — compare with contract benchmark.",
    "S04": "Remote surcharges inflate EUR/t legitimately; not an anomaly by itself.",
    "S05": "Credit drop is market-wide, not a site problem — do not blame the customer.",
    "S06": "One-month spike: avoid extrapolating revenue.",
    "S07": "Grade comes from operator assessment with noise and delay; OP-D never publishes grades.",
    "S08": "Peaks cause ad-hoc lifts; reducing frequency afterwards would be wrong.",
    "S09": "Low volume periods make fixed schedules over-service temporarily.",
    "S10": "December peaks; pre-holiday lifts are legitimate.",
    "S11": "Lifts during closures are empty — some customers cancel, some forget.",
    "S12": "Do not impute missing mass; fall back to weighbridge/invoice with provenance.",
    "S13": "Slow gain drift: device vs weighbridge ratio trends; device reports no fault.",
    "S14": "Step change at replacement; recalibrate history per sensor id.",
    "S15": "Offset/gain error after a maintenance visit; work orders give the hint.",
    "S16": "Late data: use received_at for as-of features.",
    "S17": "Deduplicate by message_id.",
    "S18": "Order by measured_at, not arrival.",
    "S19": "Ticket available weeks later — economics change after the fact.",
    "S20": "Device vs ticket gaps have several causes; only some are sensor problems.",
    "S21": "Cancellation fees only with < 24 h notice.",
    "S22": "Residual mass remains; next cycle starts non-empty.",
    "S23": "Pick the version valid on the local service date; outdated tariffs on invoices.",
    "S24": "Fuel rate / km / remote surcharge errors: compare with contract.",
    "S25": "Same job + line type twice.",
    "S26": "Phantom lines, missing lines, uninvoiced jobs, job-ref typos (not errors).",
    "S27": "Downtime creates side waste and extra lifts — context, not PdM.",
    "S28": "Wet loads are heavier: per-tonne fees up, grade down.",
    "S29": "Density shifts change kg per fill %; config changes are logged, mix changes are not.",
    "S30": "Mixed waste with low density at sites that also have recyclable streams.",
    "S31": "Benefit within tolerance: NO_ACTION is also acceptable.",
    "S32": "Expensive but explained — flagging them costs precision.",
    "S33": "No weight sensor + no shared tickets: value is invisible without assumptions.",
    "S34": "Cheapest action violates hygiene/overflow constraints.",
    "S35": "Lift-count savings disappear after emergency lifts, side waste and minimums.",
    "S36": "Well-tuned devices: every alternative is neutral or harmful.",
    "S37": "Wasted trip fees; nothing-to-collect lifts.",
    "S38": "Rejected loads: no credit + reprocessing at mixed-waste rate.",
    "S39": "Spot unnecessary 'to be safe' orders on on-call devices (published only as CUSTOMER_REQUEST).",
}


def data_dictionary() -> dict:
    return {k: {"package": v["pkg"], "description": v["desc"], "primary_key": v["pk"], "foreign_keys": v["fk"],
                "partitioned": bool(v.get("partitioned")), "columns": v["cols"]} for k, v in TABLES.items()}


def write_dictionary():
    dd = data_dictionary()
    (DOCS / "data_dictionary.json").write_text(json.dumps(dd, indent=1))
    out = ["# Data dictionary", "", "Generated from `src/europress_data/schema.py` (the single source of truth; the validator fails if a published column is missing here).",
           "Types: `str`, `int16/32/64`, `float32/64`, `bool`, `date` (local date), `ts` (timestamp, ms, UTC). Money columns `*_eur` are exact to the cent; `*_cents` are integers.", ""]
    for pkg, title in (("public", "Public package"), ("private", "Private evaluation package (NOT FOR DISTRIBUTION)")):
        out += [f"## {title}", ""]
        for k, v in TABLES.items():
            if v["pkg"] != pkg or (pkg == "private" and k.startswith("labels_test")):
                continue
            out += [f"### `{k}`", "", v["desc"], "", f"Primary key: `{', '.join(v['pk']) or '—'}`" +
                    (f" · Foreign keys: " + ", ".join(f"`{a}` → `{b}`" for a, b in v["fk"].items()) if v["fk"] else ""), "",
                    "| column | type | unit | nullable | description | allowed values |", "|---|---|---|---|---|---|"]
            for c in v["cols"]:
                out.append(f"| `{c['name']}` | {c['type']} | {c['unit'] or ''} | {'yes' if c['nullable'] else 'no'} | {c['description']} | {(c['values'] or '').replace('|', ', ')} |")
            out.append("")
        if pkg == "private":
            out += ["`labels_test/*` have the same schemas as `labels_dev/*`; `benchmark/decision_cases_private` as `benchmark/decision_cases`.", ""]
    (DOCS / "DATA_DICTIONARY.md").write_text("\n".join(out))


def write_scenarios():
    cov = {}
    p = REP / "competition" / "validation_report.json"
    if p.exists():
        cov = json.load(open(p)).get("scenario_coverage", {})
    out = ["# Scenario catalog", "", "38 scenario families. *Mechanism*: injected (parameters placed before simulation), emergent (arises from policy × demand × contract, labelled from truth), derived (observation / billing artefacts).",
           "Coverage = counts in the generated **competition** profile (public + private): `borderline` / `clear` label counts where the family is labelled; `evidence` = count of rows exhibiting it where it is a data property.", "",
           "| id | family | mechanism | label entity | tables | how generated | detection challenge | coverage (competition) |", "|---|---|---|---|---|---|---|---|"]
    for sid, name, mech, tables, ent, desc in SCENARIOS:
        c = cov.get(sid, {})
        cs = ", ".join(f"{k}: {v}" for k, v in sorted(c.items())) or "—"
        out.append(f"| {sid} | {name} | {mech} | {ent} | {tables} | {desc} | {CHALLENGE.get(sid, '')} | {cs} |")
    out += ["", "Each labelled family has normal (unlabelled), borderline and clear cases; explained cases are labelled `is_actionable = false`.",
            "Scenario labels live only in `labels_dev` (train/validation) and the private evaluation package; public feature tables contain no scenario columns."]
    (DOCS / "SCENARIO_CATALOG.md").write_text("\n".join(out))


def _null_rates(pub: Path, tables: list) -> list:
    con = duckdb.connect()
    rows = []
    for t in tables:
        f = pub / f"{t}.parquet"
        if not f.exists():
            continue
        cols = [c["name"] for c in TABLES[t]["cols"] if c["nullable"]]
        n = con.execute(f"SELECT count(*) FROM '{f}'").fetchone()[0]
        for c in cols:
            k = con.execute(f"SELECT count(*) FROM '{f}' WHERE {c} IS NULL").fetchone()[0]
            if k:
                rows.append((t, c, n, k, round(100 * k / n, 1)))
    return rows


def write_quality_report():
    out = ["# Data quality report", "", "Generated from actual generator, validator and test outputs (`reports/`). Numbers below are measured, not targets.", ""]
    for prof in ("quickstart", "competition", "enterprise"):
        gs = ROOT / "data" / prof / "generation_summary.json"
        vr = REP / prof / "validation_report.json"
        if not gs.exists():
            sc = REP / f"scale_test_{prof}.json"
            if sc.exists():
                out += [f"## Profile `{prof}`", "", "```json", sc.read_text(), "```", ""]
            continue
        g = json.load(open(gs))
        out += [f"## Profile `{prof}`", "",
                (f"* Seed: undisclosed (organiser-held; commitment `{g['seed_commitment_sha256'][:16]}…`), generator `{g['generator_version']}`, "
                 f"config hash (without seed) `{g['config_hash'][:16]}…`" if not g.get("seed_disclosed", True) else
                 f"* Seed `{g['seed']}`, generator `{g['generator_version']}`, config hash `{g['config_hash'][:16]}…`"),
                f"* Window: {g['start_date']} + {g['n_days']} days; extraction {g['extraction_time_utc']}",
                f"* Devices: {g['n_devices_public']} public + {g['n_devices_holdout']} hold-out; public customers: {g['n_customers_public']}",
                f"* Generation runtime: {g['runtime_seconds']} s (2 CPU cores); size public {g['bytes_public'] / 1e6:.1f} MB, private {g['bytes_private'] / 1e6:.1f} MB",
                f"* Golden cases: {g.get('golden_cases')}"]
        st = REP / f"runstats_{prof}.json"
        if st.exists():
            out.append(f"* Resource use: {st.read_text().strip()}")
        if vr.exists():
            v = json.load(open(vr))
            out += [f"* Validation: **{v['n_checks']} checks, {v['blocking_failures']} release-blocking failures, {v['warnings']} warnings**", ""]
            failed = [c for c in v["checks"] if not c["passed"]]
            if failed:
                out += ["Failed checks:", ""] + [f"* `{c['check_id']}` ({c['level']}): {c['violations']} — {c['detail']}" for c in failed] + [""]
            out += ["Key statistics:", "", "```json", json.dumps(v["stats"], indent=1), "```", ""]
            cats = {}
            for c in v["checks"]:
                cats.setdefault(c["check_id"].split(":")[0], [0, 0])
                cats[c["check_id"].split(":")[0]][0] += 1
                cats[c["check_id"].split(":")[0]][1] += 0 if c["passed"] else 1
            out += ["| check group | checks | failed |", "|---|---|---|"] + [f"| {k} | {a} | {b} |" for k, (a, b) in sorted(cats.items())] + [""]
        rc = {k: v for k, v in g["row_counts"].items() if "/" in str(k)}
        out += ["Row counts (selected):", "", "| table | rows |", "|---|---|"]
        for k, n in sorted(rc.items()):
            out.append(f"| `{Path(str(k)).as_posix().split(prof + '/')[-1]}` | {n:,} |")
        man = ROOT / "data" / prof / "public" / "metadata" / "dataset_manifest.json"
        if man.exists():
            m = json.load(open(man))
            tel = sum(f.get("rows", 0) for f in m["files"] if "telemetry_hourly/" in f["path"])
            out += [f"| `public/telemetry/telemetry_hourly` (all partitions) | {tel:,} |", "", f"Public files: {m['n_files']}, {m['total_bytes'] / 1e6:.1f} MB.", ""]
        if prof == "competition":
            nr = _null_rates(ROOT / "data" / prof / "public", ["operations/collection_events", "operations/weighbridge_tickets", "telemetry/telemetry_daily_summary", "finance/invoice_lines"])
            out += ["Missingness of nullable columns (public, competition) — expected and documented, never silently filled:", "",
                    "| table | column | rows | nulls | % |", "|---|---|---|---|---|"] + [f"| {a} | `{b}` | {c:,} | {d:,} | {e} |" for a, b, c, d, e in nr] + [""]
    pt = REP / "pytest.txt"
    if pt.exists():
        out += ["## Automated tests", "", "```", pt.read_text().strip()[-3000:], "```", ""]
    out += ["## Known limitations", "", "See `ASSUMPTIONS_AND_LIMITATIONS.md`. Plausibility checks are sanity ranges chosen by Since AI, not calibration against measured data."]
    (DOCS / "DATA_QUALITY_REPORT.md").write_text("\n".join(out))


def _baseline_block(r: dict, splits: tuple, c2_splits: tuple, public: bool) -> list:
    head = ("### Baseline results (competition profile, public validation labels)" if public else
            "### Baseline results (competition profile; validation = public dev labels, test = PRIVATE labels incl. hold-out customers)")
    L = [head, ""]
    if public:
        L += ["Scores on the private test period are kept by the organisers and are not shown here, so that nobody "
              "calibrates against the test period. Score yourself on the validation period with the commands in "
              "`QUICKSTART_FOR_BUILDERS.md`.", ""]
    L += ["**Task A — financial reconstruction (B1)**", "", "| split | net exact to cent | collection cost exact | €/t coverage | €/t within 5 % | fabricated €/t |", "|---|---|---|---|---|---|"]
    for sp in splits:
        a = r["task_A"]["B1_calculator"][sp]
        L.append(f"| {sp} | {a['net_material_contribution_eur:exact_to_cent_share']:.3f} | {a['collection_cost_eur:exact_to_cent_share']:.3f} | {a['per_t:coverage']:.3f} | {a['per_t:within_5pct_share']:.3f} | {a['per_t:fabricated_where_reference_null']} |")
    L += ["", f"Mass basis used by B1: {r['task_A']['mass_basis_counts']}", "", "**Task B — anomaly detection (macro-F1 over families with positives)**", "",
          "| model | " + " | ".join(splits) + " |", "|---|" + "---|" * len(splits)]
    for m, v in r["task_B"].items():
        L.append(f"| {m} | " + " | ".join(str(v[sp]["macro_f1"]) for sp in splits) + " |")
    L += ["", "Per-family (B2 rules, validation):", "", "| family | positives | precision | recall | F1 | explained cases flagged |", "|---|---|---|---|---|---|"]
    for fam, v in r["task_B"]["B2_rules"]["validation"].items():
        if isinstance(v, dict):
            L.append(f"| {fam} | {v['positives']} | {v['precision']} | {v['recall']} | {v['f1']} | {v['explained_flagged_as_anomaly']} |")
    if "task_B2" in r:
        L += ["", "**Task B2 — operator performance scorecard (B5 from public records; score 0–100, per-metric score 1 = exact, 0 = error ≥ tolerance; "
              "B5 has no trained parameters, so its 'validation' row uses all public dev months)**", "",
              "| split | rows | score | on-time | missed | shared ≤7 d | share lag | overcharge % | undercharge % | discrepant lines | weight bias % | order→lift |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for sp in splits:
            b = r["task_B2"]["B5_public_records"][sp]
            ms = ["on_time_rate", "missed_visit_rate", "weighbridge_shared_7d_rate", "median_share_lag_days", "billing_overcharge_pct",
                  "billing_undercharge_pct", "discrepant_line_rate", "weight_bias_pct", "median_order_to_lift_hours"]
            L.append(f"| {sp} | {b['n_rows']} | {b['scorecard_score_0_100']} | " + " | ".join(str(b.get(f'{m}:score')) for m in ms) + " |")
    L += ["", "**Task C — operational decisions (context)**", "", "| policy | split | cases | best share | acceptable share | mean regret € | impermissible |", "|---|---|---|---|---|---|---|"]
    for m, v in r["task_C"].items():
        for sp in splits:
            c = v[sp]
            L.append(f"| {m} | {sp} | {c['n_cases']} | {c['best_action_share']} | {c['acceptable_share']} | {c['mean_regret_eur']} | {c['impermissible_share']} |")
    d = r["task_C"]["B3_rules"]["validation"]
    L += ["", f"B3 diagnostics (validation): verify_weight_sensor precision {d.get('verify_weight_sensor:precision')}, recall {d.get('verify_weight_sensor:recall')}; "
          f"review_invoices precision {d.get('review_invoices:precision')}, recall {d.get('review_invoices:recall')}."]
    if "task_C2" in r:
        L += ["", "**Task C2 — operator and contract actions** (regret = best action set value − value of the chosen set, € per case)", "",
              "| policy | split | cases | mean regret € | value captured | dispute P/R | request P/R | renegotiate P/R | tender P/R |", "|---|---|---|---|---|---|---|---|---|"]
        for m, v in r["task_C2"].items():
            for sp in c2_splits:
                c = v[sp]
                pr = lambda a: f"{c.get(a + ':precision')}/{c.get(a + ':recall')}"
                L.append(f"| {m} | {sp} | {c['n_cases']} | {c['mean_regret_eur']} | {c['value_capture_share']} | {pr('DISPUTE_INVOICE')} | "
                         f"{pr('REQUEST_WEIGHBRIDGE_DATA')} | {pr('RENEGOTIATE_CONTRACT')} | {pr('TENDER_OR_SWITCH_OPERATOR')} |")
    return L


def write_baselines():
    p = REP / "baselines_competition.json"
    bm = DOCS / "BENCHMARK.md"
    if not p.exists() or not bm.exists():
        return
    r = json.load(open(p))
    block = "\n".join(["<!-- BASELINES:START -->"] + _baseline_block(r, ("validation",), ("dev",), True) + ["<!-- BASELINES:END -->"])
    txt = bm.read_text()
    if "BASELINE_RESULTS_PLACEHOLDER" in txt:
        txt = txt.replace("BASELINE_RESULTS_PLACEHOLDER", block)
    else:
        txt = re.sub(r"<!-- BASELINES:START -->.*<!-- BASELINES:END -->", lambda m_: block, txt, flags=re.S)
    bm.write_text(txt)
    org = REP / "organizer_only"
    org.mkdir(exist_ok=True)
    (org / "BASELINE_RESULTS_INCL_TEST.md").write_text(
        "# Baseline results incl. private test period (ORGANISERS ONLY — do not share with participants)\n\n" +
        "\n".join(_baseline_block(r, ("validation", "test"), ("dev", "test"), False)) +
        "\n\nTask C test = private hold-out customers at the as-of cutoff (small sample). Task C2 test = 60 % of public customers at extraction.\n")


def main(argv=None):
    write_dictionary()
    write_scenarios()
    write_quality_report()
    write_baselines()
    print("docs regenerated")


if __name__ == "__main__":
    main()
