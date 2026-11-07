---
id: "c11-demo-app-show-fill-and-weight-chart-for-the-de-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["app", "python", "chart"]
order: "b0X"
---
# C11 · Demo app: show fill and weight chart for the device

**Time:** ~30 min  ·  **Do first:** C10, U06

**Why:** Reuses your U05/U06 query inside the app.

## Steps
1. Query `telemetry_daily_summary` for the selected device.
2. Show it: `st.line_chart(df.set_index('date')[['fill_pct_max', 'mass_kg_last_valid']])`.
3. Add a caption: “Device data – observed”.

## Done when
- [x] Picking a device shows its chart.
