-- Analytical queries against the PUBLIC package. Run all with: python examples/run_queries.py data/quickstart/public
-- Views are created by europress_data.sdk.open_dataset(): one view per parquet file (+ telemetry_dedup).

-- name: q01_fleet_overview
-- Devices per material stream and collection policy.
SELECT material_stream, collection_policy, count(*) AS devices,
       round(avg(container_volume_m3), 1) AS avg_m3, sum(CASE WHEN has_weight_measurement THEN 1 ELSE 0 END) AS with_weight
FROM devices GROUP BY ALL ORDER BY devices DESC;

-- name: q02_collection_outcomes
-- What happened to booked/ordered collections.
SELECT status, trigger_type, count(*) AS n FROM collection_events GROUP BY ALL ORDER BY n DESC;

-- name: q03_cost_per_tonne_by_device
-- Collection cost per tonne from INVOICES and the billing mass on the same invoice (NULL when no tonnage is invoiced).
WITH lines AS (
  SELECT l.operator_job_ref,
         sum(CASE WHEN line_type IN ('LIFT_FEE','TRANSPORT','REMOTE_SURCHARGE','FUEL_SURCHARGE','HAUL_PER_TONNE','MIN_CHARGE_TOPUP','SIDE_WASTE_FEE','EMERGENCY_SURCHARGE') THEN amount_eur ELSE 0 END) AS collection_cost_eur,
         max(CASE WHEN unit = 't' THEN quantity END) AS invoiced_t
  FROM invoice_lines l GROUP BY 1)
SELECT c.device_id, count(*) AS lifts, round(sum(collection_cost_eur), 2) AS cost_eur, round(sum(invoiced_t), 3) AS t,
       round(sum(collection_cost_eur) / nullif(sum(invoiced_t), 0), 1) AS eur_per_t
FROM collection_events c JOIN lines USING (operator_job_ref)
WHERE c.status IN ('COMPLETED','PARTIAL') GROUP BY 1 ORDER BY eur_per_t DESC NULLS LAST LIMIT 15;

-- name: q04_low_fill_lifts
-- Scheduled lifts with low device fill before the lift (candidate over-servicing — check legitimate reasons!).
SELECT c.device_id, d.material_stream, d.collection_policy, d.fixed_schedule_per_week, count(*) AS lifts,
       round(median(c.device_fill_pct_before), 1) AS median_fill_before
FROM collection_events c JOIN devices d USING (device_id)
WHERE c.status = 'COMPLETED' AND c.trigger_type = 'SCHEDULED'
GROUP BY ALL HAVING count(*) >= 3 ORDER BY median_fill_before LIMIT 15;

-- name: q05_device_vs_weighbridge
-- Device-side estimated collected mass vs published weighbridge allocation (matched by operator_job_ref).
SELECT c.collection_id, c.device_id, c.device_estimated_collected_kg, w.allocated_net_kg, w.loads_on_vehicle, w.tare_method,
       round(c.device_estimated_collected_kg - w.allocated_net_kg) AS diff_kg
FROM collection_events c JOIN weighbridge_tickets w USING (operator_job_ref)
WHERE c.device_estimated_collected_kg IS NOT NULL ORDER BY abs(diff_kg) DESC LIMIT 15;

-- name: q06_weighbridge_data_access
-- How much of the weighbridge truth is visible to the customer, by operator (the data-access problem).
SELECT c.operator_id, count(*) AS lifts, count(w.ticket_id) AS published_tickets,
       round(100.0 * count(w.ticket_id) / count(*), 1) AS pct_visible,
       round(median(epoch(w.published_at - w.arrival_at) / 86400), 1) AS median_lag_days
FROM collection_events c LEFT JOIN weighbridge_tickets w USING (operator_job_ref)
WHERE c.status IN ('COMPLETED','PARTIAL') GROUP BY 1 ORDER BY 1;

-- name: q07_effective_density
-- Effective density (kg per m3 of measured fill) per device and month — weight reveals what fill cannot.
SELECT t.device_id, d.material_stream, strftime(t.measured_at, '%Y-%m') AS month,
       round(median(t.mass_kg / (t.fill_pct / 100 * d.container_volume_m3)), 0) AS kg_per_m3
FROM telemetry_dedup t JOIN devices d USING (device_id)
WHERE t.quality_flag = 'VALID' AND t.fill_pct > 40 GROUP BY ALL ORDER BY 1, 3 LIMIT 30;

-- name: q08_contract_price_changes
-- Tariff versions and what changed (validity is [effective_from, effective_to)).
SELECT contract_id, version_no, effective_from, effective_to, change_reason, lift_fee_cents / 100.0 AS lift_fee_eur,
       fuel_surcharge_bp / 100.0 AS fuel_pct, credit_share_bp / 100.0 AS credit_share_pct
FROM contract_versions WHERE contract_id IN (SELECT contract_id FROM contract_versions WHERE change_reason LIKE 'AMENDMENT%' LIMIT 3)
ORDER BY 1, 2;

-- name: q09_duplicate_invoice_lines
-- Same job and line type billed more than once.
SELECT invoice_id, operator_job_ref, line_type, count(*) AS n, sum(amount_eur) AS billed_eur
FROM invoice_lines WHERE operator_job_ref IS NOT NULL GROUP BY ALL HAVING count(*) > 1 ORDER BY billed_eur DESC LIMIT 15;

-- name: q10_invoice_lines_without_collection
-- Invoice lines whose job reference does not exist in collection events (could be typos — check contract + date).
SELECT l.invoice_line_id, l.operator_job_ref, l.service_date, l.line_type, l.amount_eur
FROM invoice_lines l LEFT JOIN collection_events c USING (operator_job_ref)
WHERE l.operator_job_ref IS NOT NULL AND c.collection_id IS NULL ORDER BY l.amount_eur DESC LIMIT 15;

-- name: q11_quality_and_credit
-- Grade distribution and invoiced recyclable credit per material.
SELECT q.material_declared, q.grade, count(*) AS loads, round(avg(q.contamination_pct_est), 1) AS avg_contamination_pct
FROM quality_assessments q GROUP BY ALL ORDER BY 1, 2;

-- name: q12_telemetry_health
-- Message delivery health per device: duplicates, buffered (late) delivery, missing hours.
SELECT device_id, count(*) AS deliveries, count(DISTINCT message_id) AS measurements,
       count(*) - count(DISTINCT message_id) AS duplicates,
       sum(CASE WHEN delivery_mode = 'BUFFERED' THEN 1 ELSE 0 END) AS buffered,
       datediff('hour', min(measured_at), max(measured_at)) + 1 - count(DISTINCT message_id) AS missing_hours
FROM telemetry_hourly GROUP BY 1 ORDER BY missing_hours DESC LIMIT 15;

-- name: q13_monthly_site_economics
-- Monthly invoiced economics per site (charges, credits, net) — all synthetic.
SELECT ct.site_id, i.billing_period, round(sum(CASE WHEN l.amount_eur > 0 THEN l.amount_eur ELSE 0 END), 2) AS charges_eur,
       round(-sum(CASE WHEN l.amount_eur < 0 THEN l.amount_eur ELSE 0 END), 2) AS credits_eur, round(sum(l.amount_eur), 2) AS net_cost_eur
FROM invoices i JOIN invoice_lines l USING (invoice_id) JOIN contracts ct USING (contract_id)
GROUP BY ALL ORDER BY 1, 2 LIMIT 24;
