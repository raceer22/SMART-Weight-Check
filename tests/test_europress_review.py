"""Checks for the change requests of the Europress data review (30 Oct 2026)."""
import json
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

from conftest import ROOT, SMALL
from europress_data.config import load_config
from europress_data.evaluate import score_b2, score_c2
from europress_data.export import hash_tree
from europress_data.generate import generate, seed_commitment


def test_equipment_classes_are_europress_machine_types(small_dataset):
    dv = pd.read_parquet(small_dataset / "public" / "reference" / "devices.parquet")
    assert set(dv.equipment_class) == {"COMBI", "DUO"}
    assert (dv[dv.material_stream == "biowaste"].equipment_class == "COMBI").all()
    assert (dv[dv.material_stream == "mixed_plastic"].equipment_class == "DUO").all()
    # Europress, 4 Nov 2026: COMBI containers at most 22 m3, DUO at most 30 m3
    assert dv[dv.equipment_class == "COMBI"].container_volume_m3.max() <= 22
    assert dv[dv.equipment_class == "DUO"].container_volume_m3.max() <= 30
    A = yaml.safe_load(open(ROOT / "configs" / "assumptions.yaml"))
    assert A["equipment_max_volume_m3"] == {"COMBI": 22, "DUO": 30}


def test_neutral_wording_and_review_additions():
    """Europress, 4 Nov 2026: neutral tonnage wording, goal sentence, SMART links, S40 note, no premium remnant."""
    files = [ROOT / "README.md", ROOT / "START_HERE.md", ROOT / "START_HERE.html"] + list((ROOT / "docs").glob("*.md")) + \
        list((ROOT / "baselines").glob("*.py")) + list((ROOT / "scripts").glob("*.py")) + list((ROOT / "src" / "europress_data").glob("*.py"))
    for p in files:
        if p.name == "EUROPRESS_REVIEW.md" or not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        removed = ("inflated" + " tonnage", "premium" + "-service", "premium" + " service")   # wording Europress asked to remove
        assert not any(w in t.lower() for w in removed), p.name
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Europress's goal is to bring transparency to the waste value chain" in readme
    assert "europressgroup.com" in readme and "epsmart.fi" in readme
    assert "do not describe the performance of the SMART fill measurement" in (ROOT / "docs" / "ASSUMPTIONS_AND_LIMITATIONS.md").read_text(encoding="utf-8")


def test_only_cardboard_and_plastics_earn_credits(small_dataset):
    pub = small_dataset / "public"
    mc = pd.read_parquet(pub / "reference" / "material_classes.parquet").set_index("material_stream")
    assert set(mc[mc.credit_eligible].index) == {"cardboard", "plastic_film", "mixed_plastic"}
    assert mc.loc["paper", "customer_economics"] == "CHARGEABLE"
    pi = pd.read_parquet(pub / "reference" / "price_index_monthly.parquet")
    assert set(pi.material) <= {"cardboard", "plastic_film", "mixed_plastic"}
    con = duckdb.connect()
    n = con.execute(f"""SELECT count(*) FROM '{pub}/finance/invoice_lines.parquet' l JOIN '{pub}/finance/invoices.parquet' i USING (invoice_id)
        JOIN '{pub}/reference/contracts.parquet' c USING (contract_id)
        WHERE l.line_type='MATERIAL_CREDIT' AND c.material_stream NOT IN ('cardboard','plastic_film','mixed_plastic')""").fetchone()[0]
    assert n == 0
    A = yaml.safe_load(open(ROOT / "configs" / "assumptions.yaml"))
    assert A["materials"]["paper"]["processing_fee"][0] > 0, "paper is chargeable to the customer"


def test_collection_policy_is_mostly_on_call(small_dataset):
    dv = pd.read_parquet(small_dataset / "public" / "reference" / "devices.parquet")
    assert (dv.collection_policy == "ON_CALL").mean() >= 0.55
    A = yaml.safe_load(open(ROOT / "configs" / "assumptions.yaml"))
    mix = A["policies"]["mix"]
    assert mix["ON_CALL"] > 0.7 and mix["FIXED_SCHEDULE"] < 0.2


def test_unnecessary_lifts_still_exist_on_on_call_devices(small_dataset):
    lab = pd.concat([pd.read_parquet(small_dataset / "public" / "labels_dev" / "anomaly_labels.parquet"),
                     pd.read_parquet(small_dataset / "private_evaluation" / "labels_test" / "anomaly_labels.parquet")])
    prem = lab[lab.label_family == "PREMATURE_UNJUSTIFIED"]
    assert {"PRECAUTIONARY_ORDER", "FILL_SENSOR_FALSE_HIGH"} & set(prem.explanation_code)
    ce = pd.read_parquet(small_dataset / "public" / "operations" / "collection_events.parquet")
    assert "CUSTOMER_PRECAUTIONARY" not in set(ce.trigger_type) | set(ce.original_trigger_type), "motive is not public"


def test_weighing_accuracy_target_in_normal_state(small_dataset):
    """Normal-state weighing: at most ~100 kg error on a 3 t load (sigma 1.5 % -> ~97 % within 3.3 %)."""
    A = yaml.safe_load(open(ROOT / "configs" / "assumptions.yaml"))["telemetry"]
    assert A["mass_sigma_rel"] <= 0.015 and A["mass_sigma_abs_kg"] <= 18
    sr = pd.read_parquet(small_dataset / "public" / "reference" / "sensor_registry.parquet")
    assert (sr.nominal_sigma_rel <= 0.015).all()
    con0 = duckdb.connect()
    con0.execute("SET TimeZone='UTC'")
    con = con0
    d = small_dataset
    err = con.execute(f"""
        WITH t AS (SELECT device_id, date_trunc('hour', measured_at) h, mass_kg FROM read_parquet('{d}/public/telemetry/telemetry_hourly/*/*.parquet', hive_partitioning=false)
                   WHERE quality_flag='VALID' AND sensor_status='OK'),
             s AS (SELECT device_id, hour_start_at h, true_container_mass_kg m, true_sensor_gain g, true_sensor_offset_kg o
                   FROM read_parquet('{d}/private_evaluation/truth/truth_hourly_state/*/*.parquet', hive_partitioning=false)),
             e AS (SELECT device_id, start_at, coalesce(end_at, TIMESTAMPTZ '2100-01-01') end_at
                   FROM '{d}/private_evaluation/truth/truth_sensor_episodes.parquet')
        SELECT abs(t.mass_kg - s.m) / s.m FROM t JOIN s USING (device_id, h)
        WHERE s.m >= 1000 AND NOT EXISTS (SELECT 1 FROM e WHERE e.device_id = t.device_id AND t.h >= e.start_at AND t.h < e.end_at)""").fetchdf().iloc[:, 0]
    assert len(err) > 200
    assert (err <= 0.0333).mean() >= 0.94, (err <= 0.0333).mean()


def test_role_notes_on_contracts_and_invoices(small_dataset):
    pub = small_dataset / "public"
    ct = pd.read_parquet(pub / "reference" / "contracts.parquet")
    assert ct.note.str.contains("Europress is not a party").all()
    inv = pd.read_parquet(pub / "finance" / "invoices.parquet")
    il = pd.read_parquet(pub / "finance" / "invoice_lines.parquet")
    assert inv.synthetic.all() and il.synthetic.all() and inv.record_note.str.startswith("SYNTHETIC").all()
    # point 4.6: every customer-operator table says who agrees and who shares the data
    from europress_data.schema import TABLES
    for t in ("reference/contracts", "reference/contract_versions", "finance/invoices", "finance/invoice_lines", "reference/price_index_monthly"):
        d = TABLES[t]["desc"]
        assert "not a party" in d and ("hands over" in d or "customer-provided" in d), t


def test_facilities_are_not_public(small_dataset):
    assert not (small_dataset / "public" / "reference" / "facilities.parquet").exists()
    assert (small_dataset / "private_evaluation" / "truth" / "facilities.parquet").exists()


def test_manifests_contain_no_absolute_paths(small_dataset):
    for pkg in ("public", "private_evaluation"):
        txt = (small_dataset / pkg / "metadata" / "dataset_manifest.json").read_text()
        assert str(small_dataset) not in txt and "/home/" not in txt and "/tmp/" not in txt


def test_undisclosed_seed_blocks_regeneration(tmp_path):
    secret = 7_315_004_771_129
    cfg = load_config("quickstart", secret, tmp_path / "official", {**SMALL, "target_devices": 25})
    generate(cfg, workers=1, verbose=False, seed_disclosed=False)
    man = json.load(open(tmp_path / "official" / "public" / "metadata" / "dataset_manifest.json"))
    assert str(secret) not in json.dumps(man)
    assert man["seed"].startswith("UNDISCLOSED") and "config_hash_with_seed" not in man
    assert man["seed_commitment_sha256"] == seed_commitment("quickstart", secret)
    priv = json.load(open(tmp_path / "official" / "private_evaluation" / "metadata" / "dataset_manifest.json"))
    assert priv["seed"] == secret
    # the documented demo seed produces a different world
    demo = load_config("quickstart", 20261023, tmp_path / "demo", {**SMALL, "target_devices": 25})
    generate(demo, workers=1, verbose=False)
    assert hash_tree(tmp_path / "demo" / "private_evaluation" / "truth") != hash_tree(tmp_path / "official" / "private_evaluation" / "truth")


def test_operator_scorecard_truth_and_scorer(small_dataset):
    dev = small_dataset / "public" / "labels_dev"
    sc = pd.read_parquet(dev / "operator_scorecard.parquet")
    assert len(sc) and set(sc.split) <= {"train", "validation"}
    assert sc.on_time_rate.between(0, 1).all() and sc.missed_visit_rate.between(0, 1).all()
    test = pd.read_parquet(small_dataset / "private_evaluation" / "labels_test" / "operator_scorecard.parquet")
    assert set(test.split) == {"test"}
    rows = pd.read_parquet(small_dataset / "public" / "benchmark" / "task_b2_scorecard_rows.parquet")
    assert len(rows) == len(test)
    perfect = score_b2(sc, dev, "all")
    assert perfect["scorecard_score_0_100"] == 100.0


def test_operator_action_cases_values_and_scorer(small_dataset):
    pub = small_dataset / "public"
    cases = pd.read_parquet(pub / "benchmark" / "operator_action_cases.parquet")
    assert cases.case_id.is_unique and set(cases.split) <= {"dev", "test"}
    v = pd.concat([pd.read_parquet(pub / "labels_dev" / "operator_action_values.parquet"),
                   pd.read_parquet(small_dataset / "private_evaluation" / "labels_test" / "operator_action_values.parquet")])
    assert set(v.case_id) == set(cases.case_id)
    for c in cases.itertuples():
        assert set(v[v.case_id == c.case_id].action) == set(c.candidate_actions.split(","))
    assert v.positive.any() and (~v.positive).any(), "some actions pay, some do not"
    # an oracle that picks exactly the positive actions (best of renegotiate/tender) has zero regret
    rows = []
    for cid, g in v.groupby("case_id"):
        vals = dict(zip(g.action, g.value_eur))
        ch = [a for a in ("DISPUTE_INVOICE", "REQUEST_WEIGHBRIDGE_DATA") if vals.get(a, -1) > 0]
        ex = {a: vals[a] for a in ("RENEGOTIATE_CONTRACT", "TENDER_OR_SWITCH_OPERATOR") if a in vals and vals[a] > 0}
        if ex:
            ch.append(max(ex, key=ex.get))
        rows.append({"case_id": cid, "actions": ";".join(ch)})
    dev = pub / "labels_dev"
    r = score_c2(pd.DataFrame(rows), dev, "dev")
    assert abs(r["mean_regret_eur"]) < 0.01
    assert score_c2(pd.DataFrame({"case_id": [], "actions": []}), dev, "dev")["value_captured_eur"] == 0


def test_business_case_has_no_prices_and_needs_team_parameters(tmp_path):
    C = yaml.safe_load(open(ROOT / "configs" / "commercial_assumptions.yaml"))
    flat = json.dumps(C)
    assert not re.search(r"\b(15|29|49)\b", flat), "old placeholder prices must not reappear"
    import business_case
    assert business_case.main(["quickstart", "--out", str(tmp_path / "bc")]) == 2


def test_removed_service_name_and_wording():
    hits = []
    for p in list((ROOT / "docs").glob("*.md")) + [ROOT / "README.md"] + list((ROOT / "configs").glob("*.yaml")) + \
            list((ROOT / "baselines").glob("*.py")) + list((ROOT / "src" / "europress_data").glob("*.py")):
        if p.name == "EUROPRESS_REVIEW.md":          # the review record quotes the removed name on purpose
            continue
        t = p.read_text(encoding="utf-8")
        if re.search(r"Premium SMART|premium SMART|'Material Value' service|\"Material Value\" service", t):
            hits.append(p.name)
    assert hits == [], hits
