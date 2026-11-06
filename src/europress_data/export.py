"""Writing helpers: typed Parquet/CSV output, staging fragments, routing, manifests."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

RENAME_MS = {
    "order_placed_ms": "order_placed_at", "scheduled_ms": "scheduled_at", "actual_ms": "actual_at",
    "reported_ms": "reported_at", "started_ms": "started_at", "completed_ms": "completed_at",
    "installed_ms": "installed_at", "removed_ms": "removed_at", "arrival_ms": "arrival_at",
    "published_ms": "published_at", "assessed_ms": "assessed_at", "issued_ms": "issued_at",
    "hour_start_ms": "hour_start_at", "event_ms": "event_at", "end_ms": "end_at", "start_ms": "start_at",
    "decision_ms": "decision_at", "eval_ms": "eval_at",
}
TS_INT_COLS = ("measured_at", "received_at")


def to_frame(x) -> pd.DataFrame:
    if x is None or len(x) == 0:
        return pd.DataFrame()
    if isinstance(x[0], pd.DataFrame):
        cats = [c for c in x[0].columns if isinstance(x[0][c].dtype, pd.CategoricalDtype)]
        if cats:
            from pandas.api.types import union_categoricals
            cat_cols = {c: union_categoricals([f[c] for f in x], ignore_order=True) for c in cats}
            out = pd.concat([f.drop(columns=cats) for f in x], ignore_index=True)
            for c in x[0].columns:
                if c in cat_cols:
                    out[c] = cat_cols[c]
            return out[list(x[0].columns)]
        return pd.concat(x, ignore_index=True)
    return pd.DataFrame(x)


def finalize(df: pd.DataFrame) -> pd.DataFrame:
    for c in list(df.columns):
        if c in RENAME_MS:
            df[RENAME_MS[c]] = pd.to_datetime(df[c].astype("Int64"), unit="ms", utc=True)
            df = df.drop(columns=[c])
        elif c in TS_INT_COLS and np.issubdtype(df[c].dtype, np.integer):
            df[c] = pd.to_datetime(df[c], unit="ms", utc=True)
    return df


def write_parquet(df: pd.DataFrame, path: Path, compression: str = "zstd"):
    path.parent.mkdir(parents=True, exist_ok=True)
    tbl = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(tbl, path, compression=compression)


def route(con: duckdb.DuckDBPyConnection, src_glob: str, dest: Path, where: str = "TRUE", order_by: str | None = None,
          csv: Path | None = None) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cols = con.execute(f"SELECT * FROM read_parquet('{src_glob}', union_by_name=true) LIMIT 0").fetchdf().columns
    drop = [c for c in cols if c.startswith("_")]
    excl = f" EXCLUDE ({', '.join(drop)})" if drop else ""
    q = f"SELECT *{excl} FROM read_parquet('{src_glob}', union_by_name=true) WHERE {where}"
    q += f" ORDER BY {order_by}" if order_by else " ORDER BY ALL"
    con.execute(f"COPY ({q}) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n = con.execute(f"SELECT count(*) FROM read_parquet('{dest}')").fetchone()[0]
    if csv is not None:
        csv.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY (SELECT * FROM read_parquet('{dest}')) TO '{csv}' (HEADER, DELIMITER ',')")
    return int(n)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def manifest(root: Path, extra: dict) -> dict:
    files = []
    con = duckdb.connect()
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "dataset_manifest.json":
            rec = {"path": str(p.relative_to(root)), "bytes": p.stat().st_size, "sha256": sha256_file(p)}
            if p.suffix == ".parquet":
                rec["rows"] = int(pq.ParquetFile(p).metadata.num_rows)
            elif p.suffix == ".csv":
                with open(p, "rb") as fh:
                    rec["rows"] = max(0, sum(1 for _ in fh) - 1)
            files.append(rec)
    con.close()
    m = {**extra, "n_files": len(files), "total_bytes": sum(f["bytes"] for f in files), "files": files}
    (root / "metadata").mkdir(parents=True, exist_ok=True)
    with open(root / "metadata" / "dataset_manifest.json", "w") as fh:
        json.dump(m, fh, indent=2, default=str)
    return m


def dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def hash_tree(path: Path, exclude: tuple = ("dataset_manifest.json",)) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(path).rglob("*")):
        if p.is_file() and p.name not in exclude and p.suffix in (".parquet", ".csv", ".json"):
            if p.suffix == ".parquet":
                # hash logical content (row data) to be independent of writer metadata
                t = pq.read_table(p)
                h.update(str(p.relative_to(path)).encode())
                h.update(pd.util.hash_pandas_object(t.to_pandas(), index=False).values.tobytes())
            else:
                h.update(str(p.relative_to(path)).encode())
                h.update(p.read_bytes())
    return h.hexdigest()


def safe_rmtree(path: Path):
    if path.exists():
        for p in sorted(path.rglob("*"), reverse=True):
            if p.is_file() or p.is_symlink():
                p.unlink()
            else:
                p.rmdir()
        path.rmdir()


os.environ.setdefault("PYARROW_IGNORE_TIMEZONE", "1")


def enforce_schemas(root: Path) -> list:
    """Cast every parquet file under root to its documented schema. Returns list of problems."""
    from .schema import TABLES, arrow_schema, table_key
    problems = []
    for p in sorted(Path(root).rglob("*.parquet")):
        rel = str(p.relative_to(root))
        if rel.startswith("_staging"):
            continue
        sub = rel.split("/", 1)[1] if rel.split("/", 1)[0] in ("public", "private_evaluation") else rel
        key = table_key(sub)
        if key is None:
            problems.append(f"undocumented table: {rel}")
            continue
        t = pq.read_table(p, partitioning=None)
        sch = arrow_schema(key)
        names = [f.name for f in sch]
        extra = [c for c in t.column_names if c not in names]
        nullable = {c["name"]: c["nullable"] for c in TABLES[key]["cols"]}
        missing = [c for c in names if c not in t.column_names and not nullable[c]]      # absent nullable extras are filled with NULL
        if extra:
            problems.append(f"{rel}: undocumented columns {extra}")
        if missing:
            problems.append(f"{rel}: documented but missing columns {missing}")
        cols = []
        for f in sch:
            if f.name in t.column_names:
                cols.append(t.column(f.name).cast(f.type, safe=False))
            else:
                cols.append(pa.nulls(t.num_rows, f.type))
        pq.write_table(pa.Table.from_arrays(cols, schema=sch), p, compression="zstd")
    return problems


def logical_hash(root: Path) -> dict:
    """Content hash per logical table (partition files combined, rows sorted) — layout independent."""
    con = duckdb.connect()
    groups = {}
    for p in sorted(Path(root).rglob("*.parquet")):
        rel = str(p.relative_to(root))
        key = rel.split("/month=")[0] if "/month=" in rel else rel
        groups.setdefault(key, []).append(str(p))
    out = {}
    for key, files in groups.items():
        df = con.execute(f"SELECT * FROM read_parquet({files}, hive_partitioning=false) ORDER BY ALL").fetchdf()
        out[key] = hashlib.sha256(pd.util.hash_pandas_object(df, index=False).values.tobytes()).hexdigest()
    con.close()
    return out
