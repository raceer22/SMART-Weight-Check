import json

import pandas as pd

from europress_data.sdk import open_dataset


def test_as_of_view_hides_future(small_dataset):
    con = open_dataset(small_dataset / "public", as_of="2026-08-01")
    cut = pd.Timestamp("2026-08-01", tz="Europe/Helsinki")
    for table, col in (("telemetry_hourly", "received_at"), ("weighbridge_tickets", "published_at"), ("invoices", "issued_at"),
                       ("quality_assessments", "published_at")):
        mx = con.execute(f"SELECT max({col}) FROM {table}").fetchone()[0]
        assert mx is None or pd.Timestamp(mx) < cut, table
    assert con.execute("SELECT count(*) FROM invoice_lines WHERE invoice_id NOT IN (SELECT invoice_id FROM invoices)").fetchone()[0] == 0
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    assert not tables & {"anomaly_labels", "reference_economics", "decision_truth", "decision_outcomes"}
    assert con.execute("SELECT count(*) FROM collection_events WHERE weight_reconciliation_status <> 'UNKNOWN_AS_OF'").fetchone()[0] == 0


def test_holdout_snapshot_is_truncated(small_dataset):
    snaps = list((small_dataset / "private_evaluation").glob("holdout_asof_*"))
    assert snaps, "hold-out as-of snapshot expected"
    cut = pd.Timestamp(snaps[0].name.split("_")[-1], tz="Europe/Helsinki")
    t = pd.read_parquet(snaps[0] / "telemetry" / "telemetry_hourly.parquet")
    assert (t.received_at < cut).all()
    ce = pd.read_parquet(snaps[0] / "operations" / "collection_events.parquet")
    assert (ce.actual_at.fillna(ce.scheduled_at) < cut).all()


def test_public_package_has_no_private_material(small_dataset):
    pub = small_dataset / "public"
    parts = [p.relative_to(pub).parts for p in pub.rglob("*")]
    assert not any(x in pp for pp in parts for x in ("truth", "labels_test", "holdout_full", "private_evaluation"))
    assert not any("golden_cases_private" in pp[-1] or pp[-1].startswith("holdout_asof") for pp in parts)
    man = json.load(open(pub / "metadata" / "dataset_manifest.json"))
    assert man["synthetic"] is True and man["contains_real_customer_data"] is False


def test_monthly_economics_consistent(small_dataset):
    m = pd.read_parquet(small_dataset / "public" / "labels_dev" / "reference_economics_monthly.parquet")
    e = pd.read_parquet(small_dataset / "public" / "labels_dev" / "reference_economics.parquet")
    assert abs(m.net_material_contribution_eur.sum() - e.net_material_contribution_eur.sum()) < 0.05
