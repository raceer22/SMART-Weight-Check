import json

import pandas as pd
import pyarrow.parquet as pq

from europress_data.validate import V


def run(d):
    rep = V(d).run()
    return rep, {r["check_id"] for r in rep["checks"] if not r["passed"] and r["level"] == "blocking"}


def test_clean_dataset_has_zero_blocking_failures(small_dataset):
    rep, failed = run(small_dataset)
    assert failed == set(), failed


def _rw(path, fn):
    df = pd.read_parquet(path)
    df = fn(df)
    df.to_parquet(path, index=False)


def test_detects_duplicate_primary_key(mutable_copy):
    _rw(mutable_copy / "public/operations/collection_events.parquet", lambda d: pd.concat([d, d.head(1)]))
    assert "PK:pub:operations/collection_events" in run(mutable_copy)[1]


def test_detects_broken_foreign_key(mutable_copy):
    def f(d):
        d.loc[d.index[0], "device_id"] = "CMP-99999"
        return d
    _rw(mutable_copy / "public/operations/collection_events.parquet", f)
    assert "FK:pub:operations/collection_events.device_id" in run(mutable_copy)[1]


def test_detects_mass_balance_violation(mutable_copy):
    def f(d):
        d.loc[d.index[0], "true_total_inflow_kg"] += 500
        return d
    _rw(mutable_copy / "private_evaluation/truth/truth_device.parquet", f)
    assert "PHYS:mass_balance" in run(mutable_copy)[1]


def test_detects_invoice_total_mismatch(mutable_copy):
    def f(d):
        d.loc[d.index[0], "total_eur"] += 10
        return d
    _rw(mutable_copy / "public/finance/invoices.parquet", f)
    assert "FIN:invoice_total_equals_lines" in run(mutable_copy)[1]


def test_detects_unlabelled_billing_difference(mutable_copy):
    def f(d):
        i = d.index[d.line_type == "LIFT_FEE"][0]
        d.loc[i, "amount_eur"] += 5
        return d
    _rw(mutable_copy / "public/finance/invoice_lines.parquet", f)
    def g(d):
        return d
    failed = run(mutable_copy)[1]
    assert "FIN:invoice_total_equals_lines" in failed


def test_detects_sensor_semantics_violation(mutable_copy):
    p = next((mutable_copy / "public/telemetry/telemetry_hourly").glob("*/*.parquet"))
    t = pq.read_table(p)
    def f(d):
        i = d.index[d.quality_flag == "VALID"][0]
        d.loc[i, "quality_flag"] = "SENSOR_FAULT"
        return d
    df = f(t.to_pandas())
    pq.write_table(__import__("pyarrow").Table.from_pandas(df, schema=t.schema, preserve_index=False), p)
    assert "SENSOR:mass_null_iff_fault_or_absent" in run(mutable_copy)[1]


def test_detects_personal_data(mutable_copy):
    def f(d):
        d.loc[d.index[0], "site_name"] = "contact matti.meikalainen@example.com"
        return d
    _rw(mutable_copy / "public/reference/sites.parquet", f)
    assert "PRIV:no_personal_data_patterns" in run(mutable_copy)[1]


def test_detects_holdout_leakage(mutable_copy):
    hold = pd.read_parquet(mutable_copy / "private_evaluation/holdout_full/reference/devices.parquet")
    assert len(hold) > 0
    _rw(mutable_copy / "public/reference/devices.parquet", lambda d: pd.concat([d, hold.head(1)]))
    assert "SPLIT:no_holdout_devices_public" in run(mutable_copy)[1]


def test_detects_test_label_leakage(mutable_copy):
    t = pd.read_parquet(mutable_copy / "private_evaluation/labels_test/anomaly_labels.parquet")
    _rw(mutable_copy / "public/labels_dev/anomaly_labels.parquet", lambda d: pd.concat([d, t[t.event_at > d.event_at.max()].head(3)]))
    assert "SPLIT:dev_labels_before_test" in run(mutable_copy)[1]


def test_detects_time_ordering_violation(mutable_copy):
    p = next((mutable_copy / "public/telemetry/telemetry_hourly").glob("*/*.parquet"))
    t = pq.read_table(p)
    df = t.to_pandas()
    df.loc[df.index[0], "received_at"] = df.loc[df.index[0], "measured_at"] - pd.Timedelta(hours=2)
    pq.write_table(__import__("pyarrow").Table.from_pandas(df, schema=t.schema, preserve_index=False), p)
    assert "TIME:telemetry_received_after_measured" in run(mutable_copy)[1]


def test_detects_checksum_tampering(mutable_copy):
    p = mutable_copy / "public/reference/regions.parquet"
    _rw(p, lambda d: d.assign(median_billable_km=d.median_billable_km + 1))
    assert "META:public:checksums" in run(mutable_copy)[1]
