"""First useful analysis: collection cost per tonne per device, with an explicit mass basis.
python examples/first_analysis.py data/quickstart/public"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "baselines"))
import pandas as pd  # noqa: E402
from b1_economic_calculator import compute  # noqa: E402

root = sys.argv[1] if len(sys.argv) > 1 else "data/quickstart/public"
ev, _ = compute(root)
lifts = ev[ev.status.isin(["COMPLETED", "PARTIAL"])]
dev = pd.read_parquet(Path(root) / "reference" / "devices.parquet")
ce = pd.read_parquet(Path(root) / "operations" / "collection_events.parquet", columns=["collection_id", "device_fill_pct_before"])
lifts = lifts.merge(ce, on="collection_id")
known = lifts[lifts.mass_known]
g = known.groupby("device_id").agg(lifts=("collection_id", "count"), t=("mass_kg", lambda s: s.sum() / 1000),
                                   cost=("collection_cost_eur", "sum"), bench=("benchmark_eur_per_t", "median"),
                                   median_fill_before=("device_fill_pct_before", "median"))
g["eur_per_t"] = (g.cost / g.t).round(1)
g["vs_benchmark"] = (g.eur_per_t / g.bench).round(2)
basis = lifts.groupby("device_id").mass_basis.agg(lambda s: ", ".join(f"{k}:{v}" for k, v in s.value_counts().items()))
unknown = lifts[~lifts.mass_known].groupby("device_id").size().rename("lifts_mass_unknown")
out = g.join(basis.rename("mass_basis_counts")).join(unknown).fillna({"lifts_mass_unknown": 0})
out = out.join(dev.set_index("device_id")[["material_stream", "collection_policy"]])
print("Collection cost per tonne (SYNTHETIC; mass basis shown; unknown mass excluded, never imputed)\n")
print(out.sort_values("vs_benchmark", ascending=False).head(15).round(2).to_string())
print("\nDevices above 2x benchmark with median fill < 50 % before lifts are candidates for a policy review —"
      " check hygiene / maximum-interval rules before proposing anything.")
