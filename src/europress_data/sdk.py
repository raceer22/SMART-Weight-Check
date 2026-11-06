"""Tiny helper for participants: open a package as DuckDB views, optionally 'as of' a time.

    from europress_data.sdk import open_dataset
    con = open_dataset("data/competition/public")
    con.sql("SELECT * FROM collection_events LIMIT 5").show()

    con = open_dataset("data/competition/public", as_of="2026-03-01")   # leak-free view for a decision

as_of semantics (local Europe/Helsinki midnight of the given date):
  * rows are kept only if they were knowable before the cutoff (received/published/issued/reported/occurred);
  * columns that are computed at extraction time or describe the future are neutralised
    (reconciliation statuses and dispute status -> 'UNKNOWN_AS_OF'; future end dates -> NULL);
  * the daily summary is rebuilt from the as-of telemetry;
  * label, benchmark-answer and metadata tables are not exposed.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

HIDDEN_AS_OF = ("labels_dev", "labels_test", "metadata", "truth")


def _views(root: Path, as_of: str | None) -> dict:
    """name -> (relative path, SQL)."""
    cut = f"TIMESTAMPTZ '{as_of} 00:00:00 Europe/Helsinki'" if as_of else None
    cut_date = f"CAST(timezone('Europe/Helsinki', {cut}) AS DATE)" if as_of else None
    out = {}
    for p in sorted(root.rglob("*.parquet")):
        rel = p.relative_to(root)
        if "/month=" in str(p) or (as_of and rel.parts[0] in HIDDEN_AS_OF):
            continue
        name, f = p.stem, f"read_parquet('{p}')"
        q = f"SELECT * FROM {f}"
        if as_of:
            q = {
                "collection_events": f"SELECT * REPLACE ('UNKNOWN_AS_OF' AS weight_reconciliation_status, 'UNKNOWN_AS_OF' AS invoice_match_status) "
                                     f"FROM {f} WHERE coalesce(actual_at, scheduled_at) < {cut} AND (order_placed_at IS NULL OR order_placed_at < {cut})",
                "weighbridge_tickets": f"SELECT * FROM {f} WHERE published_at < {cut}",
                "quality_assessments": f"SELECT * FROM {f} WHERE published_at < {cut}",
                "maintenance_work_orders": f"SELECT * REPLACE (CASE WHEN completed_at < {cut} THEN completed_at END AS completed_at) FROM {f} WHERE reported_at < {cut}",
                "invoices": f"SELECT * REPLACE ('UNKNOWN_AS_OF' AS dispute_status) FROM {f} WHERE issued_at < {cut}",
                "invoice_lines": f"SELECT l.* FROM {f} l JOIN read_parquet('{root / 'finance' / 'invoices.parquet'}') i USING (invoice_id) WHERE i.issued_at < {cut}",
                "sensor_registry": f"SELECT * REPLACE (CASE WHEN removed_at < {cut} THEN removed_at END AS removed_at) FROM {f} WHERE installed_at < {cut}",
                "contract_versions": f"SELECT * REPLACE (CASE WHEN effective_to <= {cut_date} THEN effective_to END AS effective_to) FROM {f} WHERE effective_from < {cut_date}",
                "price_index_monthly": f"SELECT * FROM {f} WHERE published_on < {cut_date}",
                "devices": f"SELECT * REPLACE (CASE WHEN active_to < {cut_date} THEN active_to END AS active_to, "
                           f"CASE WHEN active_to < {cut_date} THEN lifecycle_status ELSE 'ACTIVE' END AS lifecycle_status) FROM {f}",
                "device_installations": f"SELECT * REPLACE (CASE WHEN removed_on < {cut_date} THEN removed_on END AS removed_on) FROM {f}",
                "telemetry_hourly": f"SELECT * FROM {f} WHERE received_at < {cut}",
                "decision_cases": f"SELECT * FROM {f} WHERE decision_at <= {cut}",
            }.get(name, q)
            if name in ("telemetry_daily_summary", "task_ab_test_collections", "task_b_test_invoice_lines"):
                continue
        out[name] = (str(rel), q)
    tel = root / "telemetry" / "telemetry_hourly"
    if tel.exists() and tel.is_dir():
        q = f"SELECT * FROM read_parquet('{tel}/*/*.parquet', hive_partitioning=false)"
        if as_of:
            q += f" WHERE received_at < {cut}"
        out["telemetry_hourly"] = ("telemetry/telemetry_hourly.parquet", q)
    return out


DAILY_FROM_DEDUP = """SELECT device_id, CAST(timezone('Europe/Helsinki', measured_at) AS DATE) AS date, count(*) AS n_messages,
  CAST(arg_min(fill_pct, measured_at) AS FLOAT) AS fill_pct_first, CAST(arg_max(fill_pct, measured_at) AS FLOAT) AS fill_pct_last,
  CAST(max(fill_pct) AS FLOAT) AS fill_pct_max, CAST(min(fill_pct) AS FLOAT) AS fill_pct_min,
  CAST(arg_max(mass_kg, measured_at) FILTER (WHERE quality_flag IN ('VALID','LOW_CONFIDENCE')) AS FLOAT) AS mass_kg_last_valid,
  CAST(max(mass_kg) FILTER (WHERE quality_flag IN ('VALID','LOW_CONFIDENCE')) AS FLOAT) AS mass_kg_max_valid,
  count(*) FILTER (WHERE quality_flag IN ('VALID','LOW_CONFIDENCE')) AS n_valid_mass, CAST(sum(compaction_cycles) AS BIGINT) AS compaction_cycles,
  count(*) FILTER (WHERE operational_state='DOWN') AS hours_down, count(*) FILTER (WHERE operational_state='FULL') AS hours_full,
  count(*) FILTER (WHERE delivery_mode='BUFFERED') AS n_buffered, round(least(100.0, 100.0 * count(*) / 24), 1) AS data_completeness_pct
FROM telemetry_dedup GROUP BY 1, 2"""


def open_dataset(root: str | Path, as_of: str | None = None, memory_limit: str = "3GB") -> duckdb.DuckDBPyConnection:
    root = Path(root)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'; SET TimeZone='UTC'")
    views = _views(root, as_of)
    for name, (_, q) in views.items():
        con.execute(f"CREATE OR REPLACE VIEW {name} AS {q}")
    if "telemetry_hourly" in views:
        con.execute("""CREATE OR REPLACE VIEW telemetry_dedup AS SELECT * EXCLUDE (rn) FROM (
                       SELECT *, row_number() OVER (PARTITION BY message_id ORDER BY received_at, delivery_id) rn FROM telemetry_hourly) WHERE rn = 1""")
        if as_of:
            con.execute(f"CREATE OR REPLACE VIEW telemetry_daily_summary AS {DAILY_FROM_DEDUP}")
    return con


def write_snapshot(root: str | Path, dest: str | Path, as_of: str) -> dict:
    """Materialise the as-of views of a package (used for the private hold-out Task C snapshot)."""
    root, dest = Path(root), Path(dest)
    con = open_dataset(root, as_of=as_of)
    counts = {}
    views = dict(_views(root, as_of))
    views["telemetry_daily_summary"] = ("telemetry/telemetry_daily_summary.parquet", None)
    for name, (rel, _) in views.items():
        d = dest / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY (SELECT * FROM {name} ORDER BY ALL) TO '{d}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        counts[str(d)] = con.execute(f"SELECT count(*) FROM '{d}'").fetchone()[0]
    con.close()
    return counts
