"""Can we estimate collected weight WITHOUT a scale on every container? (notes/ideas.md, Part 1 idea 1)

    python notes/weight_without_scale.py [data/competition/public]

Truth = operator weighbridge net (single-load, no side waste, completed lifts). For each lift we only use
signals every compactor already has: fill % before the lift, press load index and compaction cycles since the
previous lift, days since the previous lift, container volume, material stream, equipment class, site sector.

Variants
  A  stream profile, no ML       kg = median density of the stream x volume x fill   (devices never weighed)
  B  ML on profiles (GBM)        same + press/cycles/sector features                  (devices never weighed)
  C  rotation kit, N months      device-specific density learned while the kit was on that device,
                                 then used for the rest of the year                    (each device weighed once)
  D  integrated scale            the dataset's own device estimate (before - after)    (reference)

All evaluation of A/B is leave-device-out (GroupKFold): a device is never in its own training set.
Synthetic data: results show what this simulated world allows, not real-world accuracy.
"""
import sys; sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from europress_data.sdk import open_dataset

pub = sys.argv[1] if len(sys.argv) > 1 else "data/competition/public"
con = open_dataset(pub)

lifts = con.sql("""
WITH ev AS (
  SELECT c.collection_id, c.device_id, c.actual_at, c.device_fill_pct_before AS fill,
         c.device_estimated_collected_kg AS device_kg, w.allocated_net_kg AS truth_kg,
         LAG(c.actual_at) OVER (PARTITION BY c.device_id ORDER BY c.actual_at) AS prev_at,
         c.status, c.driver_reported_side_waste AS side, w.loads_on_vehicle
  FROM collection_events c
  LEFT JOIN weighbridge_tickets w USING (operator_job_ref)
  WHERE c.status IN ('COMPLETED', 'PARTIAL')
)
SELECT ev.*, d.container_volume_m3 AS vol, d.material_stream AS stream, d.equipment_class AS eq, s.sector
FROM ev JOIN devices d USING (device_id) JOIN sites s ON s.site_id = d.site_id
WHERE ev.status = 'COMPLETED' AND NOT COALESCE(ev.side, FALSE) AND ev.loads_on_vehicle = 1
  AND ev.truth_kg > 100 AND ev.fill IS NOT NULL AND ev.prev_at IS NOT NULL
""").df()

feats = con.sql("""
SELECT l.collection_id,
       AVG(t.press_load_index) AS press_mean, MAX(t.press_load_index) AS press_max,
       SUM(t.compaction_cycles) AS cycles
FROM lifts l JOIN telemetry_dedup t
  ON t.device_id = l.device_id AND t.measured_at > l.prev_at AND t.measured_at <= l.actual_at
GROUP BY 1
""").df()
df = lifts.merge(feats, on="collection_id", how="left")
df["days"] = (df.actual_at - df.prev_at).dt.total_seconds() / 86400
df["fill_vol"] = df.vol * df.fill / 100
df = df[df.fill_vol > 0.3].reset_index(drop=True)


def score(name, pred, truth):
    r = pred / truth - 1
    band = (truth >= 2500) & (truth <= 3500)
    return {"variant": name, "lifts": int(np.isfinite(r).sum()),
            "median_abs_err_pct": round(100 * np.nanmedian(np.abs(r)), 1),
            "sigma_pct (1.4826*MAD)": round(100 * 1.4826 * np.nanmedian(np.abs(r - np.nanmedian(r))), 1),
            "p95_abs_err_pct": round(100 * np.nanpercentile(np.abs(r), 95), 1),
            "within_100kg_2.5-3.5t": round(float((np.abs(pred - truth)[band] <= 100).mean()), 3)}


rows = []
truth = df.truth_kg.to_numpy(float)
gkf = GroupKFold(n_splits=5)

# A · stream profile (no ML): density per stream from the training devices only
predA = np.full(len(df), np.nan)
for tr, te in gkf.split(df, groups=df.device_id):
    dens = (df.truth_kg / df.fill_vol).iloc[tr].groupby(df.stream.iloc[tr]).median()
    predA[te] = df.fill_vol.iloc[te] * df.stream.iloc[te].map(dens).to_numpy()
rows.append(score("A stream profile, no ML (never weighed)", predA, truth))

# B · gradient boosting on profile + press features; target = density, so volume/fill scale is exact
X = pd.get_dummies(df[["fill", "vol", "press_mean", "press_max", "cycles", "days", "stream", "eq", "sector"]],
                   columns=["stream", "eq", "sector"], dtype=float)
y = np.log(df.truth_kg / df.fill_vol)
predB = np.full(len(df), np.nan)
for tr, te in gkf.split(X, groups=df.device_id):
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=0).fit(X.iloc[tr], y.iloc[tr])
    predB[te] = np.exp(m.predict(X.iloc[te])) * df.fill_vol.iloc[te]
rows.append(score("B ML: stream + press + sector (never weighed)", predB, truth))

# C · rotation kit: weigh each device for its first N months, learn its own density, predict the rest
df = df.sort_values("actual_at")
start = df.groupby("device_id").actual_at.transform("min")
for months in (1, 3):
    calib = df.actual_at < start + pd.Timedelta(days=30 * months)
    dens_dev = (df.truth_kg / df.fill_vol)[calib].groupby(df.device_id[calib]).median()
    test = ~calib & df.device_id.isin(dens_dev.index)
    pred = df.fill_vol[test] * df.device_id[test].map(dens_dev)
    rows.append(score(f"C rotation kit, {months} month(s) on each device", pred.to_numpy(), df.truth_kg[test].to_numpy(float)))

# D · reference: integrated scale (dataset's own device before-after estimate)
d = df.dropna(subset=["device_kg"])
rows.append(score("D integrated scale on every device (reference)", d.device_kg.to_numpy(float), d.truth_kg.to_numpy(float)))

print(pd.DataFrame(rows).to_markdown(index=False))
print("\nTarget from U10: sigma ~1.75 % -> ~95 % of 3 t loads within +/-100 kg; overbilling detection breaks down above ~2.5 %.")
