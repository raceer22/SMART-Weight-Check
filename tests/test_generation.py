import json

import duckdb
import pandas as pd

from conftest import make
from europress_data.export import enforce_schemas, hash_tree, logical_hash


def test_deterministic_for_fixed_seed(small_dataset, tmp_path):
    again = make(tmp_path / "again")
    assert hash_tree(small_dataset / "public") == hash_tree(again / "public")
    assert hash_tree(small_dataset / "private_evaluation") == hash_tree(again / "private_evaluation")


def test_different_seed_differs(small_dataset, tmp_path):
    other = make(tmp_path / "other", seed=1)
    assert hash_tree(small_dataset / "public") != hash_tree(other / "public")


def test_chunking_does_not_change_results(small_dataset, tmp_path):
    chunked = make(tmp_path / "chunked", chunk_devices=7)
    a, b = logical_hash(small_dataset), logical_hash(chunked)
    assert a.keys() == b.keys()
    assert [k for k in a if a[k] != b[k]] == []


def test_every_column_documented(small_dataset):
    assert enforce_schemas(small_dataset) == []


def test_mass_balance_per_device(small_dataset):
    con = duckdb.connect()
    d = small_dataset / "private_evaluation" / "truth"
    bad = con.execute(f"""SELECT count(*) FROM '{d}/truth_device.parquet' t LEFT JOIN
        (SELECT device_id, sum(true_collected_kg + true_side_waste_collected_kg) c FROM '{d}/truth_collections.parquet' GROUP BY 1) x USING (device_id)
        WHERE abs(true_total_inflow_kg - coalesce(c,0) - true_end_container_kg - true_end_side_stock_kg) > 0.01""").fetchone()[0]
    assert bad == 0


def test_heterogeneous_behaviour(small_dataset):
    dv = pd.read_parquet(small_dataset / "public" / "reference" / "devices.parquet")
    cal = pd.read_parquet(small_dataset / "public" / "reference" / "site_calendar.parquet")
    assert dv.collection_policy.nunique() == 3 and dv.material_stream.nunique() >= 4
    assert (~cal.is_open).any(), "not every site operates every day"


def test_weight_carries_information_beyond_fill(small_dataset):
    """kg per % fill must vary within material (density, moisture, mix) — unlike the v0 pack."""
    con = duckdb.connect()
    cv = con.execute(f"""SELECT d.material_stream, stddev(t.mass_kg / (t.fill_pct * d.container_volume_m3 / 100)) / avg(t.mass_kg / (t.fill_pct * d.container_volume_m3 / 100))
        FROM read_parquet('{small_dataset}/public/telemetry/telemetry_hourly/*/*.parquet', hive_partitioning=false) t
        JOIN '{small_dataset}/public/reference/devices.parquet' d USING (device_id)
        WHERE t.quality_flag='VALID' AND t.fill_pct > 40 GROUP BY 1""").fetchall()
    assert all(v > 0.08 for _, v in cv), cv


def test_labels_and_decisions_exist(small_dataset):
    lab = pd.read_parquet(small_dataset / "public" / "labels_dev" / "anomaly_labels.parquet")
    assert (~lab.is_actionable).any() and lab.is_actionable.any()            # false-positive traps exist
    dt = pd.read_parquet(small_dataset / "public" / "labels_dev" / "decision_truth.parquet")
    assert (dt.best_action == "NO_ACTION").any() and (dt.best_action != "NO_ACTION").any()
    oc = pd.read_parquet(small_dataset / "public" / "labels_dev" / "decision_outcomes.parquet")
    assert (oc.benefit_vs_no_action_cents < 0).any(), "some actions must be harmful"
    best = dt.merge(oc, left_on=["case_id", "best_action"], right_on=["case_id", "action"])
    assert best.permissible.all()
