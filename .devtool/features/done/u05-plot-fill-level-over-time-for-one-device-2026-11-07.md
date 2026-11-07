---
id: "u05-plot-fill-level-over-time-for-one-device-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:12:17.000Z"
completedAt: "2026-11-07T02:12:17.000Z"
labels: ["data", "beginner", "python", "chart"]
order: "b0E"
---
# U05 · Plot fill level over time for one device

**Time:** ~30 min  ·  **Do first:** U03

**Why:** Seeing the saw-tooth pattern (fills up → emptied → fills up) makes the data click.

## Steps
1. Pick one `device_id` from the `devices` table.
2. Load its daily data:
   ```python
   df = con.sql("SELECT * FROM telemetry_daily_summary WHERE device_id = 'XXX' ORDER BY date").df()
   ```
3. Plot it:
   ```python
   import matplotlib.pyplot as plt
   plt.plot(df.date, df.fill_pct_max); plt.title('Fill % – XXX'); plt.savefig('notes/fill.png')
   ```
4. Open `notes/fill.png`.

## Done when
- [x] `notes/fill.png` shows a saw-tooth line, and it is posted in the chat.
