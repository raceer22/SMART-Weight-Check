"""How close to >99 % per-lift accuracy can software get with the device scale we already simulate?

    python notes/precision_experiments.py [data/competition/public]

Levers tested on top of the dataset's integrated scale (reading noise 1.4 % + install gain 0.4 % + offset 6 kg):
  1  average ALL readings while the content cannot change (after the last compaction before the lift,
     before the first compaction after it) instead of one reading each side
  2  continuous span calibration: correct each device's gain with the median ratio of its previous
     weighbridge tickets (no extra hardware)
Reference = single-load weighbridge net with a freshly WEIGHED tare (stored tares carry extra error).
Synthetic data: shows what the simulated sensor allows, not real hardware.
"""
import sys; sys.path.insert(0, "src")
import numpy as np
import pandas as pd
from europress_data.sdk import open_dataset

pub = sys.argv[1] if len(sys.argv) > 1 else "data/competition/public"
con = open_dataset(pub)

df = con.sql("""
WITH ev AS (
  SELECT c.collection_id, c.device_id, c.actual_at, c.device_estimated_collected_kg AS one_reading_kg,
         w.allocated_net_kg AS truth_kg, w.tare_method
  FROM collection_events c JOIN weighbridge_tickets w USING (operator_job_ref)
  WHERE c.status = 'COMPLETED' AND NOT COALESCE(c.driver_reported_side_waste, FALSE)
    AND NOT c.driver_reported_partial AND w.loads_on_vehicle = 1 AND w.allocated_net_kg > 500
    AND c.device_estimated_collected_kg IS NOT NULL),
h AS (SELECT device_id, measured_at, mass_kg, compaction_cycles, quality_flag FROM telemetry_dedup),
w AS (
  SELECT ev.collection_id,
         MAX(h.measured_at) FILTER (WHERE h.compaction_cycles > 0 AND h.measured_at <= ev.actual_at
                                    AND h.measured_at > ev.actual_at - INTERVAL 7 DAY) AS last_cycle_before,
         MIN(h.measured_at) FILTER (WHERE h.compaction_cycles > 0 AND h.measured_at > ev.actual_at + INTERVAL 1 HOUR
                                    AND h.measured_at < ev.actual_at + INTERVAL 7 DAY) AS first_cycle_after
  FROM ev JOIN h USING (device_id) GROUP BY 1)
SELECT ev.*,
  AVG(h.mass_kg) FILTER (WHERE h.measured_at > w.last_cycle_before AND h.measured_at <= ev.actual_at - INTERVAL 1 HOUR) AS before_avg,
  COUNT(*)       FILTER (WHERE h.measured_at > w.last_cycle_before AND h.measured_at <= ev.actual_at - INTERVAL 1 HOUR) AS n_before,
  AVG(h.mass_kg) FILTER (WHERE h.measured_at > ev.actual_at + INTERVAL 1 HOUR AND h.measured_at < w.first_cycle_after) AS after_avg,
  COUNT(*)       FILTER (WHERE h.measured_at > ev.actual_at + INTERVAL 1 HOUR AND h.measured_at < w.first_cycle_after) AS n_after
FROM ev JOIN w USING (collection_id)
JOIN h ON h.device_id = ev.device_id AND h.quality_flag = 'VALID'
     AND h.measured_at BETWEEN ev.actual_at - INTERVAL 7 DAY AND ev.actual_at + INTERVAL 7 DAY
GROUP BY ALL
""").df().sort_values("actual_at").reset_index(drop=True)

df["avg_kg"] = df.before_avg - df.after_avg
# lever 2: rolling gain correction from this device's previous tickets (strictly past data)
df["ratio"] = df.truth_kg / df.avg_kg
df["gain"] = df.groupby("device_id").ratio.transform(lambda s: s.shift(1).rolling(8, min_periods=3).median())
df["avg_cal_kg"] = df.avg_kg * df.gain


def stats(name, pred, sub):
    p, t = pred[sub].to_numpy(float), df.truth_kg[sub].to_numpy(float)
    ok = np.isfinite(p)
    e = np.abs(p[ok] / t[ok] - 1)
    return {"method": name, "lifts": int(ok.sum()), "median_err_%": round(100 * np.median(e), 2),
            "p95_err_%": round(100 * np.percentile(e, 95), 2), "share_within_1%": round(float((e <= 0.01).mean()), 3)}


for label, sub in [("WEIGHED tare (clean reference)", df.tare_method == "WEIGHED"),
                   ("STORED tare (noisy reference)", df.tare_method == "STORED")]:
    sub = sub & (df.n_before >= 3) & (df.n_after >= 3)
    print(f"\n## Reference: {label}\n")
    print(pd.DataFrame([
        stats("one reading before / after (dataset today)", df.one_reading_kg, sub),
        stats("1  average all quiet readings", df.avg_kg, sub),
        stats("1+2 average + rolling gain calibration", df.avg_cal_kg, sub),
    ]).to_markdown(index=False))

q = df[(df.n_before >= 3) & (df.n_after >= 3)]
print(f"\nQuiet readings available per lift: median {q.n_before.median():.0f} before, {q.n_after.median():.0f} after "
      f"({len(q)} of {len(df)} lifts have >=3 on both sides).")
print("Weighbridge alone: sigma 12 kg + 20 kg resolution ~ 0.5 % on a 3 t load, so ~1 % is the limit this reference can verify.")
