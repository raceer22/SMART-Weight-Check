"""Deeper look at 'weigh a sample, then estimate' (notes/ideas.md Part 1 idea 1).

    python notes/rotation_experiments.py [data/competition/public]

Questions
  1. Where does the remaining error come from (fill sensor noise? density drift? aggregation)?
  2. Which way of running the rotation learns most per kit-month?
  3. Does the error average out over a month / a year (what a customer report actually shows)?

Truth = shared single-load weighbridge net (completed, no side waste). Synthetic data.
"""
import sys; sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold
from europress_data.sdk import open_dataset

pub = sys.argv[1] if len(sys.argv) > 1 else "data/competition/public"
con = open_dataset(pub)
MD = lambda d: print(d.to_markdown(index=False), "\n")

# ---------------------------------------------------------------- lifts + features
con.sql("""
CREATE OR REPLACE TEMP TABLE lifts AS
WITH ev AS (
  SELECT c.collection_id, c.device_id, c.actual_at, c.device_fill_pct_before AS fill,
         c.device_estimated_collected_kg AS device_kg, w.allocated_net_kg AS truth_kg, w.loads_on_vehicle,
         LAG(c.actual_at) OVER (PARTITION BY c.device_id ORDER BY c.actual_at) AS prev_at,
         c.status, c.driver_reported_side_waste AS side
  FROM collection_events c LEFT JOIN weighbridge_tickets w USING (operator_job_ref)
  WHERE c.status IN ('COMPLETED','PARTIAL'))
SELECT ev.*, d.container_volume_m3 AS vol, d.material_stream AS stream, d.equipment_class AS eq, s.sector
FROM ev JOIN devices d USING (device_id) JOIN sites s ON s.site_id = d.site_id
WHERE ev.status='COMPLETED' AND NOT COALESCE(ev.side,FALSE) AND ev.loads_on_vehicle=1
  AND ev.truth_kg > 100 AND ev.fill IS NOT NULL AND ev.prev_at IS NOT NULL""")
df = con.sql("""
SELECT l.*, AVG(t.press_load_index) press_mean, MAX(t.press_load_index) press_max, SUM(t.compaction_cycles) cycles,
       MEDIAN(t.fill_pct) FILTER (WHERE t.measured_at > l.actual_at - INTERVAL 6 HOUR) AS fill_6h
FROM lifts l JOIN telemetry_dedup t
  ON t.device_id = l.device_id AND t.measured_at > l.prev_at AND t.measured_at <= l.actual_at - INTERVAL 1 HOUR
GROUP BY ALL""").df()
df["days"] = (df.actual_at - df.prev_at).dt.total_seconds() / 86400
df["fv"] = df.vol * df.fill / 100
df = df[df.fv > 0.3].sort_values("actual_at").reset_index(drop=True)
df["month"] = df.actual_at.dt.strftime("%Y-%m")
start = df.groupby("device_id").actual_at.transform("min")


def stats(name, pred, truth, extra=""):
    pred, truth = np.asarray(pred, float), np.asarray(truth, float)
    ok = np.isfinite(pred) & np.isfinite(truth)
    r = pred[ok] / truth[ok] - 1
    return {"method": name, "lifts": int(ok.sum()), "median_abs_err_%": round(100 * np.median(np.abs(r)), 1),
            "bias_%": round(100 * np.median(r), 1), "p90_abs_err_%": round(100 * np.percentile(np.abs(r), 90), 1),
            "note": extra}


# ---------------------------------------------------------------- 1. fill sensor noise
print("## 1. How noisy is the fill sensor?\n")
noise = con.sql("""
WITH h AS (SELECT device_id, measured_at, fill_pct, compaction_cycles,
                  fill_pct - LAG(fill_pct) OVER (PARTITION BY device_id ORDER BY measured_at) AS dfill,
                  LAG(compaction_cycles) OVER (PARTITION BY device_id ORDER BY measured_at) AS prev_cycles
           FROM telemetry_dedup)
SELECT ROUND(STDDEV(dfill)/SQRT(2), 2) AS fill_noise_sigma_pct_points, COUNT(*) AS quiet_hour_pairs
FROM h WHERE compaction_cycles = 0 AND prev_cycles = 0 AND fill_pct BETWEEN 20 AND 95""").df()
MD(noise)
print("Quiet hours (no compaction in either hour): the true content cannot change, so the hour-to-hour jitter is sensor noise.\n")

# ---------------------------------------------------------------- 2. rotation strategies (1 kit-month per device)
print("## 2. Ways to run the rotation (each device gets the kit for its first 30 days, evaluated on the rest of the year)\n")
calib = df.actual_at < start + pd.Timedelta(days=30)
test = ~calib
rows = []

# 2a per-lift calibration (what the first test did)
d_lift = (df.truth_kg / df.fv)[calib].groupby(df.device_id[calib]).median()
p = df.fv * df.device_id.map(d_lift)
rows.append(stats("a) kit sees the ~2 lifts in its month", p[test], df.truth_kg[test], "1-2 data points per device"))

# 2b hourly calibration: the kit (here: the simulated scale) logs mass every hour, regress mass on fill*vol
dev = con.sql("SELECT device_id, container_volume_m3 vol FROM devices").df()
hourly = con.sql("""
SELECT t.device_id, t.measured_at, t.fill_pct, t.mass_kg FROM telemetry_dedup t
WHERE t.quality_flag='VALID' AND t.fill_pct BETWEEN 25 AND 98""").df().merge(dev, on="device_id")
first = df.groupby("device_id").actual_at.min().rename("t0")
hourly = hourly.merge(first, left_on="device_id", right_index=True)
hk = hourly[(hourly.measured_at >= hourly.t0 - pd.Timedelta(days=20)) & (hourly.measured_at < hourly.t0 + pd.Timedelta(days=30))]
d_hour = (hk.mass_kg / (hk.vol * hk.fill_pct / 100)).groupby(hk.device_id).median()
p = df.fv * df.device_id.map(d_hour)
rows.append(stats("b) kit logs every hour (~500 fill/mass pairs)", p[test], df.truth_kg[test], "density from hourly pairs"))

# 2c cross-device ML prior (no kit) + shrink toward the device's kit data
X = pd.get_dummies(df[["fill", "vol", "press_mean", "press_max", "cycles", "days", "stream", "eq", "sector"]],
                   columns=["stream", "eq", "sector"], dtype=float)
y = np.log(df.truth_kg / df.fv)
prior = np.full(len(df), np.nan)
for tr, te in GroupKFold(5).split(X, groups=df.device_id):
    m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, random_state=0).fit(X.iloc[tr], y.iloc[tr])
    prior[te] = m.predict(X.iloc[te])
df["prior"] = prior
rows.append(stats("c) no kit: ML prior from other devices", (np.exp(df.prior) * df.fv)[test], df.truth_kg[test], "baseline"))
res = np.log(df.device_id.map(d_hour)) - df.prior          # device offset vs prior, from kit hours
p = np.exp(df.prior + res) * df.fv
rows.append(stats("d) ML prior + device offset from kit hours", p[test], df.truth_kg[test], "hierarchical"))

# 2e smoothing the fill reading (median of the last 6 h instead of one hour)
fv6 = df.vol * df.fill_6h / 100
p = fv6 * df.device_id.map(d_hour)
rows.append(stats("e) = b) + fill = median of last 6 h", p[test], df.truth_kg[test], "less fill noise"))

# 2f free 'rotation': keep learning from every shared weighbridge ticket (rolling last 5 lifts)
df["dens"] = df.truth_kg / df.fv
roll = df.groupby("device_id").dens.transform(lambda s: s.shift(1).rolling(5, min_periods=2).median())
rows.append(stats("f) no kit: learn from shared weighbridge tickets (last 5)", (df.fv * roll)[test], df.truth_kg[test],
                  "online, operator data"))
rows.append(stats("ref) scale on every device", df.device_kg[test], df.truth_kg[test], "dataset device estimate"))
MD(pd.DataFrame(rows))

# ---------------------------------------------------------------- 3. does it drift?
print("## 3. Does a 1-month calibration go stale? (method b, error by months since the kit left)\n")
df["pred_b"] = df.fv * df.device_id.map(d_hour)
df["age_m"] = ((df.actual_at - start).dt.days // 30).clip(upper=11)
r = (df.pred_b / df.truth_kg - 1)[test]
MD(r.abs().groupby(df.age_m[test]).median().mul(100).round(1).rename("median_abs_err_%").reset_index())

# ---------------------------------------------------------------- 4. aggregation
print("## 4. Error on totals: per lift vs per device-month vs per device-year (method b)\n")
t = df[test & df.pred_b.notna()]
agg = []
for lvl, keys in [("single lift", ["collection_id"]), ("device-month", ["device_id", "month"]), ("device-year", ["device_id"])]:
    g = t.groupby(keys)[["pred_b", "truth_kg"]].sum()
    e = g.pred_b / g.truth_kg - 1
    agg.append({"level": lvl, "n": len(g), "median_abs_err_%": round(100 * e.abs().median(), 1),
                "p90_abs_err_%": round(100 * e.abs().quantile(0.9), 1)})
MD(pd.DataFrame(agg))

# ---------------------------------------------------------------- 5. what is left
print("## 5. What still explains the error? (method b, median abs error by group)\n")
t = t.assign(err=(t.pred_b / t.truth_kg - 1).abs() * 100,
             fill_band=pd.cut(t.fill, [0, 40, 60, 80, 101], labels=["<40", "40-60", "60-80", ">80"]))
for col in ["fill_band", "stream"]:
    MD(t.groupby(col, observed=True).err.agg(["count", "median"]).round(1).reset_index())



# ---------------------------------------------------------------- 6. better learning: a curve, not one density
print("## 6. Learn a per-device weight-vs-fill CURVE from kit hours instead of one density number\n")
hk = hk.assign(f=hk.fill_pct / 100)
coef = {}
for dev_id, g in hk.groupby("device_id"):
    if len(g) < 50:
        continue
    A = np.c_[g.f, g.f ** 2]                                   # mass = a*f + b*f^2  (0 kg at 0 % fill)
    coef[dev_id] = np.linalg.lstsq(A, g.mass_kg.to_numpy(float), rcond=None)[0]
f = df.fill / 100
cf = df.device_id.map(coef)
df["pred_curve"] = [c[0] * x + c[1] * x * x if isinstance(c, np.ndarray) else np.nan for c, x in zip(cf, f)]
rows6 = [stats("b) one density per device", df.pred_b[test], df.truth_kg[test]),
         stats("g) per-device curve a*f + b*f^2", df.pred_curve[test], df.truth_kg[test])]
MD(pd.DataFrame(rows6))
t = df[test & df.pred_curve.notna()]
t = t.assign(err=(t.pred_curve / t.truth_kg - 1).abs() * 100,
             fill_band=pd.cut(t.fill, [0, 40, 60, 80, 101], labels=["<40", "40-60", "60-80", ">80"]))
MD(t.groupby("fill_band", observed=True).err.agg(["count", "median"]).round(1).reset_index())

# ---------------------------------------------------------------- 7. does per-load press data explain what is left?
print("## 7. Can press/compaction data since the last lift explain the remaining per-load error? (leave-device-out)\n")
t = df[test & df.pred_curve.notna()].copy()
t["lr"] = np.log(t.truth_kg / t.pred_curve)
Xr = t[["press_mean", "press_max", "cycles", "days", "fill"]]
corr = np.full(len(t), np.nan)
for tr, te in GroupKFold(5).split(Xr, groups=t.device_id):
    m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, random_state=0).fit(Xr.iloc[tr], t.lr.iloc[tr])
    corr[te] = m.predict(Xr.iloc[te])
MD(pd.DataFrame([stats("g) curve", t.pred_curve, t.truth_kg),
                 stats("h) curve + press/cycles correction", t.pred_curve * np.exp(corr), t.truth_kg)]))

wo = con.sql("SELECT work_order_type, COUNT(*) n FROM maintenance_work_orders GROUP BY 1 ORDER BY n DESC").df()

MD(con.sql("SELECT work_order_type, COUNT(*) n FROM maintenance_work_orders GROUP BY 1 ORDER BY n DESC").df())
