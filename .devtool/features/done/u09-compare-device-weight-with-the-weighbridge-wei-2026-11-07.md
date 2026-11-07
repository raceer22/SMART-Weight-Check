---
id: "u09-compare-device-weight-with-the-weighbridge-wei-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "1 · Understand the weight data"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T02:12:17.000Z"
completedAt: "2026-11-07T02:12:17.000Z"
labels: ["data", "sql", "weight"]
order: "b0I"
---
# U09 · Compare device weight with the weighbridge weight

**Time:** ~30 min  ·  **Do first:** U02

**Why:** The weighbridge (the truck scale at the operator's facility) is the reference. How close is the device?

## Steps
1. Run:
   ```sql
   SELECT c.collection_id, c.device_estimated_collected_kg AS device_kg, w.allocated_net_kg AS bridge_kg,
          w.loads_on_vehicle
   FROM collection_events c JOIN weighbridge_tickets w USING (operator_job_ref)
   WHERE c.device_estimated_collected_kg IS NOT NULL LIMIT 20
   ```
2. Add a column `diff_kg = device_kg - bridge_kg`.
3. Look at rows with a big difference. Is `loads_on_vehicle` > 1 there (combined loads)?

## Done when
- [x] 20 example rows plus 1–2 sentences on why they differ are in FINDINGS.md.

## Help
- A difference is **not automatically the operator's fault**: sensor drift, side waste and combined loads also cause differences.
