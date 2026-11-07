---
id: "c10-demo-app-add-a-device-picker-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "2 · Customer weight view"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T03:48:20.000Z"
completedAt: "2026-11-07T03:48:20.000Z"
labels: ["app", "python"]
order: "b0W"
---
# C10 · Demo app: add a device picker

**Time:** ~30 min  ·  **Do first:** C09

**Why:** The customer chooses which compactor to look at.

## Steps
1. In `app/app.py` load the dataset (see the `open_dataset` snippet in U01).
2. Get device ids: `ids = con.sql('SELECT device_id FROM devices ORDER BY 1').df().device_id`.
3. Add `device = st.selectbox('Device', ids)`.
4. Show `st.write(device)` to check it works.

## Done when
- [x] Changing the dropdown changes the shown id.

## Help
- Use `@st.cache_resource` on the function that opens the dataset so it loads only once.
