"""Epic 1 · Understand the weight data — reproducible exploration.

Run from repo root:  python notes/explore.py
Writes notes/fill.png, notes/mass.png, notes/fill_mass.png and prints every table used in notes/FINDINGS.md.
U10 is a separate script:  python examples/weighing_accuracy_value.py data/competition/public
"""
import sys; sys.path.insert(0, "src")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from europress_data.sdk import open_dataset

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 50)

con = open_dataset("data/quickstart/public")
DEVICE = "CMP-00001"  # mixed_waste, DUO, 8 m3, ON_CALL, has weight sensor, ~99 % data completeness


def show(title, sql):
    print(f"\n### {title}")
    print(con.sql(sql).df().to_string(index=False))


# U01 · list all tables
con.sql("SHOW TABLES").show(max_rows=100)

# U02 / U03 · sample rows (transposed so every column fits)
for t in ["collection_events", "telemetry_daily_summary"]:
    print(f"\n### U02/U03 · 5 rows of {t}")
    print(con.sql(f"SELECT * FROM {t} LIMIT 5").df().T.to_string())

# U04 · devices per waste stream, and how many have a weight sensor
show("U04 · devices per material_stream",
     "SELECT material_stream, COUNT(*) AS n FROM devices GROUP BY 1 ORDER BY n DESC")
show("U04 · devices with weight sensor",
     "SELECT has_weight_measurement, COUNT(*) AS n FROM devices GROUP BY 1 ORDER BY 1")

# U05 / U06 · fill and mass over time for one device
df = con.sql(f"SELECT * FROM telemetry_daily_summary WHERE device_id = '{DEVICE}' ORDER BY date").df()
lifts = con.sql(f"""SELECT actual_at FROM collection_events
                    WHERE device_id = '{DEVICE}' AND status IN ('COMPLETED','PARTIAL') ORDER BY actual_at""").df()

plt.figure(figsize=(11, 4))
plt.plot(df.date, df.fill_pct_max)
plt.title(f"Fill % (daily max) – {DEVICE}"); plt.ylabel("fill %"); plt.tight_layout()
plt.savefig("notes/fill.png", dpi=120); plt.close()

plt.figure(figsize=(11, 4))
plt.plot(df.date, df.mass_kg_last_valid, color="tab:orange")
plt.title(f"Mass kg (last valid reading of the day) – {DEVICE}"); plt.ylabel("kg"); plt.tight_layout()
plt.savefig("notes/mass.png", dpi=120); plt.close()

fig, ax1 = plt.subplots(figsize=(11, 4))
ax1.plot(df.date, df.fill_pct_max, label="fill % (max)")
ax1.set_ylabel("fill %")
ax2 = ax1.twinx()
ax2.plot(df.date, df.mass_kg_last_valid, color="tab:orange", label="mass kg (last valid)")
ax2.set_ylabel("kg")
for t in lifts.actual_at:
    ax1.axvline(t, color="grey", alpha=0.3, lw=0.8)
ax1.set_title(f"Fill vs mass – {DEVICE} (grey lines = collections)")
fig.legend(loc="upper left"); fig.tight_layout()
fig.savefig("notes/fill_mass.png", dpi=120); plt.close(fig)

both = df[["fill_pct_max", "mass_kg_max_valid"]].dropna()
print(f"\n### U06 · correlation fill_pct_max vs mass_kg_max_valid ({DEVICE}): {both.corr().iloc[0, 1]:.2f}")

# U07 · duplicates in the hourly ingest log
show("U07 · duplicate telemetry messages",
     """SELECT COUNT(*) AS all_rows, COUNT(DISTINCT message_id) AS unique_msgs,
               COUNT(*) - COUNT(DISTINCT message_id) AS duplicates FROM telemetry_hourly""")
show("U07 · rows in cleaned view", "SELECT COUNT(*) AS dedup_rows FROM telemetry_dedup")

# U08 · missing and bad weight readings (on the deduplicated view)
show("U08 · NULL / negative mass",
     """SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE mass_kg IS NULL) AS null_mass,
               COUNT(*) FILTER (WHERE mass_kg < 0) AS negative_mass FROM telemetry_dedup""")
show("U08 · quality_flag",
     """SELECT quality_flag, COUNT(*) AS n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (), 1) AS pct
        FROM telemetry_dedup GROUP BY 1 ORDER BY n DESC""")
show("U08 · sensor_status",
     """SELECT sensor_status, COUNT(*) AS n, ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER (), 1) AS pct
        FROM telemetry_dedup GROUP BY 1 ORDER BY n DESC""")

# U09 · device estimate vs weighbridge
show("U09 · 20 example rows",
     """SELECT c.collection_id, c.device_estimated_collected_kg AS device_kg, w.allocated_net_kg AS bridge_kg,
               c.device_estimated_collected_kg - w.allocated_net_kg AS diff_kg,
               w.loads_on_vehicle, c.driver_reported_side_waste AS side_waste
        FROM collection_events c JOIN weighbridge_tickets w USING (operator_job_ref)
        WHERE c.device_estimated_collected_kg IS NOT NULL ORDER BY c.collection_id LIMIT 20""")
show("U09 · all joined rows, grouped by cause",
     """WITH j AS (SELECT c.driver_reported_side_waste AS side_waste, w.loads_on_vehicle, w.allocated_net_kg,
                          c.device_estimated_collected_kg - w.allocated_net_kg AS d
                   FROM collection_events c JOIN weighbridge_tickets w USING (operator_job_ref)
                   WHERE c.device_estimated_collected_kg IS NOT NULL)
        SELECT loads_on_vehicle, side_waste, COUNT(*) AS n, ROUND(AVG(d)) AS mean_diff_kg,
               ROUND(MEDIAN(ABS(d))) AS median_abs_diff_kg,
               ROUND(100 * MEDIAN(ABS(d) / NULLIF(allocated_net_kg, 0)), 1) AS median_abs_pct
        FROM j GROUP BY ALL ORDER BY 1, 2""")
