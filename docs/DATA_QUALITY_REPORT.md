# Data quality report

Generated from actual generator, validator and test outputs (`reports/`). Numbers below are measured, not targets.

## Profile `quickstart`

* Seed: undisclosed (organiser-held; commitment `64e93f96a4e29c86…`), generator `1.0.1`, config hash (without seed) `71be8223651b1a2c…`
* Window: 2026-07-01 + 90 days; extraction 2026-10-13T09:00:00+00:00
* Devices: 50 public + 0 hold-out; public customers: 4
* Generation runtime: 14.3 s (2 CPU cores); size public 19.1 MB, private 0.9 MB
* Golden cases: {'public': 119, 'private': 88, 'unit_financial': 90}
* Resource use: {"module": "europress_data.generate", "args": ["--profile", "quickstart", "--seed-file", "organizer/seeds.json"], "wall_seconds": 24.8, "peak_rss_main_mb": 280.6, "peak_rss_largest_child_mb": 0.0, "exit_code": 0}
* Validation: **150 checks, 0 release-blocking failures, 1 warnings**

Failed checks:

* `PLAUS:cost_per_t_range` (warning): 1 — {'cardboard': 124.2, 'mixed_plastic': 601.0, 'mixed_waste': 107.9, 'plastic_film': 287.4}

Key statistics:

```json
{
 "median_true_fill_at_lift_pct": 60.2,
 "share_cycles_with_overflow": 0.028,
 "telemetry_rows": 106751,
 "duplicate_rate": 0.0031,
 "missing_message_rate": 0.0146,
 "median_collection_cost_eur_per_t": {
  "cardboard": 124.2,
  "mixed_plastic": 601.0,
  "mixed_waste": 107.9,
  "plastic_film": 287.4
 },
 "label_counts": {
  "COST_PER_T_HIGH": 116,
  "PREMATURE_UNJUSTIFIED": 89,
  "WEIGHT_DISCREPANCY": 78,
  "CONTAMINATION_VALUE_LOSS": 57,
  "EARLY_JUSTIFIED": 35,
  "DELAYED_COLLECTION": 33,
  "CONTAMINATION_INCIDENT": 19,
  "FILL_SENSOR_FALSE_HIGH": 19,
  "SENSOR_FAULT": 13,
  "MOISTURE_HEAVY_LOAD": 13,
  "BREAKDOWN": 11,
  "REJECTED_LOAD": 11,
  "HIGH_GENERATION": 11,
  "UNMATCHED_LINE": 11,
  "WRONG_SURCHARGE": 10,
  "SENSOR_DRIFT": 9,
  "MISSING_LINE": 9,
  "SENSOR_DEGRADED": 7,
  "DENSITY_SHIFT": 7,
  "RECYCLABLES_IN_MIXED": 7,
  "TELEMETRY_LATENCY": 6,
  "WEIGHT_BASIS_MISMATCH": 6,
  "SENSOR_REPLACEMENT": 3,
  "DUPLICATE_LINE": 3,
  "CALIBRATION_ERROR": 3,
  "UNINVOICED_COLLECTION": 3,
  "OPERATOR_DELAY_EPISODE": 3
 }
}
```

| check group | checks | failed |
|---|---|---|
| CONTRACT | 2 | 0 |
| COV | 1 | 0 |
| DEV | 1 | 0 |
| FIN | 9 | 0 |
| FK | 26 | 0 |
| LEAK | 2 | 0 |
| MAT | 5 | 0 |
| META | 14 | 0 |
| PHYS | 7 | 0 |
| PK | 51 | 0 |
| PLAUS | 5 | 1 |
| PRIV | 2 | 0 |
| SEM | 2 | 0 |
| SENSOR | 4 | 0 |
| SPLIT | 6 | 0 |
| STRUCT | 1 | 0 |
| TIME | 5 | 0 |
| UNIT | 1 | 0 |
| WB | 6 | 0 |

Row counts (selected):

| table | rows |
|---|---|
| `private_evaluation/benchmark/decision_cases_private.parquet` | 0 |
| `private_evaluation/labels_test/anomaly_labels.parquet` | 320 |
| `private_evaluation/labels_test/decision_outcomes.parquet` | 239 |
| `private_evaluation/labels_test/decision_truth.parquet` | 50 |
| `private_evaluation/labels_test/operator_action_values.parquet` | 73 |
| `private_evaluation/labels_test/operator_scorecard.parquet` | 12 |
| `private_evaluation/labels_test/reference_charge_lines.parquet` | 970 |
| `private_evaluation/labels_test/reference_economics.parquet` | 251 |
| `private_evaluation/labels_test/reference_economics_monthly.parquet` | 78 |
| `private_evaluation/truth/invoice_line_labels.parquet` | 42 |
| `private_evaluation/truth/quality_all.parquet` | 269 |
| `private_evaluation/truth/truth_collections.parquet` | 386 |
| `private_evaluation/truth/truth_device.parquet` | 50 |
| `private_evaluation/truth/truth_sensor_episodes.parquet` | 35 |
| `private_evaluation/truth/weighbridge_all.parquet` | 385 |
| `public/benchmark/decision_cases.parquet` | 250 |
| `public/benchmark/operator_action_cases.parquet` | 50 |
| `public/benchmark/task_ab_test_collections.parquet` | 145 |
| `public/benchmark/task_b2_scorecard_rows.parquet` | 12 |
| `public/benchmark/task_b_test_invoice_lines.parquet` | 313 |
| `public/finance/invoice_lines.parquet` | 1,666 |
| `public/finance/invoices.parquet` | 149 |
| `public/labels_dev/anomaly_labels.parquet` | 272 |
| `public/labels_dev/decision_outcomes.parquet` | 956 |
| `public/labels_dev/decision_truth.parquet` | 200 |
| `public/labels_dev/operator_action_values.parquet` | 13 |
| `public/labels_dev/operator_scorecard.parquet` | 6 |
| `public/labels_dev/reference_charge_lines.parquet` | 661 |
| `public/labels_dev/reference_economics.parquet` | 214 |
| `public/labels_dev/reference_economics_monthly.parquet` | 76 |
| `public/operations/collection_events.parquet` | 465 |
| `public/operations/maintenance_work_orders.parquet` | 55 |
| `public/operations/quality_assessments.parquet` | 230 |
| `public/operations/weighbridge_tickets.parquet` | 323 |
| `public/reference/contract_versions.parquet` | 65 |
| `public/reference/contracts.parquet` | 50 |
| `public/reference/customers.parquet` | 4 |
| `public/reference/device_installations.parquet` | 50 |
| `public/reference/devices.parquet` | 50 |
| `public/reference/material_classes.parquet` | 6 |
| `public/reference/operators.parquet` | 5 |
| `public/reference/price_index_monthly.parquet` | 12 |
| `public/reference/quality_grade_rules.parquet` | 4 |
| `public/reference/regions.parquet` | 6 |
| `public/reference/sensor_registry.parquet` | 50 |
| `public/reference/site_calendar.parquet` | 1,440 |
| `public/reference/sites.parquet` | 16 |
| `public/telemetry/telemetry_daily_summary.parquet` | 4,486 |
| `public/telemetry/telemetry_hourly` (all partitions) | 106,751 |

Public files: 71, 19.1 MB.

## Profile `competition`

* Seed: undisclosed (organiser-held; commitment `4cb3796dd3c72975…`), generator `1.0.1`, config hash (without seed) `eeeceafb35ce6e27…`
* Window: 2025-10-01 + 365 days; extraction 2026-10-15T09:00:00+00:00
* Devices: 447 public + 53 hold-out; public customers: 52
* Generation runtime: 188.7 s (2 CPU cores); size public 120.4 MB, private 46.5 MB
* Golden cases: {'public': 123, 'private': 90, 'unit_financial': 90}
* Resource use: {"module": "europress_data.generate", "args": ["--profile", "competition", "--seed-file", "organizer/seeds.json", "--workers", "2"], "wall_seconds": 189.4, "peak_rss_main_mb": 640.8, "peak_rss_largest_child_mb": 700.3, "exit_code": 0}
* Validation: **204 checks, 0 release-blocking failures, 0 warnings**

Key statistics:

```json
{
 "median_true_fill_at_lift_pct": 69.6,
 "share_cycles_with_overflow": 0.142,
 "telemetry_rows": 3800881,
 "duplicate_rate": 0.003,
 "missing_message_rate": 0.0137,
 "median_collection_cost_eur_per_t": {
  "mixed_waste": 76.9,
  "plastic_film": 177.7,
  "cardboard": 67.6,
  "mixed_plastic": 251.1,
  "paper": 150.0,
  "biowaste": 164.3
 },
 "label_counts": {
  "COST_PER_T_HIGH": 4635,
  "DELAYED_COLLECTION": 3088,
  "WEIGHT_DISCREPANCY": 2986,
  "PREMATURE_UNJUSTIFIED": 2922,
  "CONTAMINATION_VALUE_LOSS": 2261,
  "EARLY_JUSTIFIED": 1166,
  "BREAKDOWN": 654,
  "OUTDATED_TARIFF": 467,
  "FILL_SENSOR_FALSE_HIGH": 441,
  "WRONG_SURCHARGE": 209,
  "UNMATCHED_LINE": 206,
  "DUPLICATE_LINE": 194,
  "REJECTED_LOAD": 182,
  "CONTAMINATION_INCIDENT": 173,
  "MISSING_LINE": 164,
  "WEIGHT_BASIS_MISMATCH": 119,
  "SENSOR_FAULT": 107,
  "MOISTURE_HEAVY_LOAD": 94,
  "UNINVOICED_COLLECTION": 86,
  "HIGH_GENERATION": 81,
  "SENSOR_DEGRADED": 61,
  "RECYCLABLES_IN_MIXED": 57,
  "TELEMETRY_LATENCY": 42,
  "SENSOR_DRIFT": 42,
  "DENSITY_SHIFT": 31,
  "DUPLICATE_BURST": 29,
  "OPERATOR_DELAY_EPISODE": 24,
  "CALIBRATION_ERROR": 21,
  "SENSOR_REPLACEMENT": 17
 }
}
```

| check group | checks | failed |
|---|---|---|
| CONTRACT | 2 | 0 |
| COV | 1 | 0 |
| DEV | 1 | 0 |
| FIN | 9 | 0 |
| FK | 51 | 0 |
| LEAK | 2 | 0 |
| MAT | 5 | 0 |
| META | 14 | 0 |
| PHYS | 7 | 0 |
| PK | 72 | 0 |
| PLAUS | 5 | 0 |
| PRIV | 2 | 0 |
| SEM | 2 | 0 |
| SENSOR | 4 | 0 |
| SPLIT | 14 | 0 |
| STRUCT | 1 | 0 |
| TIME | 5 | 0 |
| UNIT | 1 | 0 |
| WB | 6 | 0 |

Row counts (selected):

| table | rows |
|---|---|
| `private_evaluation/benchmark/decision_cases_private.parquet` | 52 |
| `private_evaluation/holdout_asof_2026-08-01/finance/invoice_lines.parquet` | 7,260 |
| `private_evaluation/holdout_asof_2026-08-01/finance/invoices.parquet` | 471 |
| `private_evaluation/holdout_asof_2026-08-01/operations/collection_events.parquet` | 2,558 |
| `private_evaluation/holdout_asof_2026-08-01/operations/maintenance_work_orders.parquet` | 164 |
| `private_evaluation/holdout_asof_2026-08-01/operations/quality_assessments.parquet` | 1,002 |
| `private_evaluation/holdout_asof_2026-08-01/operations/weighbridge_tickets.parquet` | 1,938 |
| `private_evaluation/holdout_asof_2026-08-01/reference/contract_versions.parquet` | 110 |
| `private_evaluation/holdout_asof_2026-08-01/reference/contracts.parquet` | 53 |
| `private_evaluation/holdout_asof_2026-08-01/reference/customers.parquet` | 7 |
| `private_evaluation/holdout_asof_2026-08-01/reference/device_installations.parquet` | 53 |
| `private_evaluation/holdout_asof_2026-08-01/reference/devices.parquet` | 53 |
| `private_evaluation/holdout_asof_2026-08-01/reference/material_classes.parquet` | 6 |
| `private_evaluation/holdout_asof_2026-08-01/reference/operators.parquet` | 5 |
| `private_evaluation/holdout_asof_2026-08-01/reference/price_index_monthly.parquet` | 30 |
| `private_evaluation/holdout_asof_2026-08-01/reference/quality_grade_rules.parquet` | 4 |
| `private_evaluation/holdout_asof_2026-08-01/reference/regions.parquet` | 6 |
| `private_evaluation/holdout_asof_2026-08-01/reference/sensor_registry.parquet` | 56 |
| `private_evaluation/holdout_asof_2026-08-01/reference/site_calendar.parquet` | 6,570 |
| `private_evaluation/holdout_asof_2026-08-01/reference/sites.parquet` | 18 |
| `private_evaluation/holdout_asof_2026-08-01/telemetry/telemetry_daily_summary.parquet` | 15,855 |
| `private_evaluation/holdout_asof_2026-08-01/telemetry/telemetry_hourly.parquet` | 377,467 |
| `private_evaluation/holdout_full/finance/invoice_lines.parquet` | 9,643 |
| `private_evaluation/holdout_full/finance/invoices.parquet` | 627 |
| `private_evaluation/holdout_full/operations/collection_events.parquet` | 3,062 |
| `private_evaluation/holdout_full/operations/maintenance_work_orders.parquet` | 197 |
| `private_evaluation/holdout_full/operations/quality_assessments.parquet` | 1,210 |
| `private_evaluation/holdout_full/operations/weighbridge_tickets.parquet` | 2,336 |
| `private_evaluation/holdout_full/reference/contract_versions.parquet` | 111 |
| `private_evaluation/holdout_full/reference/contracts.parquet` | 53 |
| `private_evaluation/holdout_full/reference/customers.parquet` | 7 |
| `private_evaluation/holdout_full/reference/device_installations.parquet` | 53 |
| `private_evaluation/holdout_full/reference/devices.parquet` | 53 |
| `private_evaluation/holdout_full/reference/material_classes.parquet` | 6 |
| `private_evaluation/holdout_full/reference/operators.parquet` | 5 |
| `private_evaluation/holdout_full/reference/price_index_monthly.parquet` | 39 |
| `private_evaluation/holdout_full/reference/quality_grade_rules.parquet` | 4 |
| `private_evaluation/holdout_full/reference/regions.parquet` | 6 |
| `private_evaluation/holdout_full/reference/sensor_registry.parquet` | 56 |
| `private_evaluation/holdout_full/reference/site_calendar.parquet` | 6,570 |
| `private_evaluation/holdout_full/reference/sites.parquet` | 18 |
| `private_evaluation/holdout_full/telemetry/telemetry_daily_summary.parquet` | 19,011 |
| `private_evaluation/labels_test/anomaly_labels.parquet` | 6,849 |
| `private_evaluation/labels_test/decision_outcomes.parquet` | 246 |
| `private_evaluation/labels_test/decision_truth.parquet` | 52 |
| `private_evaluation/labels_test/operator_action_values.parquet` | 711 |
| `private_evaluation/labels_test/operator_scorecard.parquet` | 45 |
| `private_evaluation/labels_test/reference_charge_lines.parquet` | 28,120 |
| `private_evaluation/labels_test/reference_economics.parquet` | 8,130 |
| `private_evaluation/labels_test/reference_economics_monthly.parquet` | 1,945 |
| `private_evaluation/truth/invoice_line_labels.parquet` | 1,445 |
| `private_evaluation/truth/quality_all.parquet` | 10,397 |
| `private_evaluation/truth/truth_collections.parquet` | 20,956 |
| `private_evaluation/truth/truth_device.parquet` | 500 |
| `private_evaluation/truth/truth_sensor_episodes.parquet` | 248 |
| `private_evaluation/truth/weighbridge_all.parquet` | 20,835 |
| `public/benchmark/decision_cases.parquet` | 3,946 |
| `public/benchmark/operator_action_cases.parquet` | 437 |
| `public/benchmark/task_ab_test_collections.parquet` | 3,509 |
| `public/benchmark/task_b2_scorecard_rows.parquet` | 45 |
| `public/benchmark/task_b_test_invoice_lines.parquet` | 12,720 |
| `public/csv_samples/collection_events.csv` | 1,001 |
| `public/csv_samples/contract_versions.csv` | 50 |
| `public/csv_samples/contracts.csv` | 25 |
| `public/csv_samples/devices.csv` | 25 |
| `public/csv_samples/invoice_lines.csv` | 3,430 |
| `public/csv_samples/invoices.csv` | 294 |
| `public/csv_samples/price_index_monthly.csv` | 39 |
| `public/csv_samples/telemetry_daily_summary.csv` | 8,916 |
| `public/csv_samples/telemetry_hourly.csv` | 212,312 |
| `public/csv_samples/weighbridge_tickets.csv` | 698 |
| `public/finance/invoice_lines.parquet` | 76,416 |
| `public/finance/invoices.parquet` | 5,269 |
| `public/labels_dev/anomaly_labels.parquet` | 13,710 |
| `public/labels_dev/decision_outcomes.parquet` | 18,071 |
| `public/labels_dev/decision_truth.parquet` | 3,946 |
| `public/labels_dev/operator_action_values.parquet` | 639 |
| `public/labels_dev/operator_scorecard.parquet` | 135 |
| `public/labels_dev/reference_charge_lines.parquet` | 55,816 |
| `public/labels_dev/reference_economics.parquet` | 15,866 |
| `public/labels_dev/reference_economics_monthly.parquet` | 4,009 |
| `public/operations/collection_events.parquet` | 20,934 |
| `public/operations/maintenance_work_orders.parquet` | 1,622 |
| `public/operations/quality_assessments.parquet` | 6,721 |
| `public/operations/weighbridge_tickets.parquet` | 13,569 |
| `public/reference/contract_versions.parquet` | 961 |
| `public/reference/contracts.parquet` | 447 |
| `public/reference/customers.parquet` | 52 |
| `public/reference/device_installations.parquet` | 447 |
| `public/reference/devices.parquet` | 447 |
| `public/reference/material_classes.parquet` | 6 |
| `public/reference/operators.parquet` | 5 |
| `public/reference/price_index_monthly.parquet` | 39 |
| `public/reference/quality_grade_rules.parquet` | 4 |
| `public/reference/regions.parquet` | 6 |
| `public/reference/sensor_registry.parquet` | 416 |
| `public/reference/site_calendar.parquet` | 54,750 |
| `public/reference/sites.parquet` | 150 |
| `public/telemetry/telemetry_daily_summary.parquet` | 159,579 |
| `public/telemetry/telemetry_hourly` (all partitions) | 3,800,881 |

Public files: 107, 120.4 MB.

Missingness of nullable columns (public, competition) — expected and documented, never silently filled:

| table | column | rows | nulls | % |
|---|---|---|---|---|
| operations/collection_events | `cancellation_notice_hours` | 20,934 | 19,025 | 90.9 |
| operations/collection_events | `wasted_trip_reason` | 20,934 | 20,602 | 98.4 |
| operations/collection_events | `vehicle_id` | 20,934 | 2,568 | 12.3 |
| operations/collection_events | `driver_reported_side_waste` | 20,934 | 2,457 | 11.7 |
| operations/collection_events | `device_fill_pct_before` | 20,934 | 2,717 | 13.0 |
| operations/collection_events | `device_fill_pct_after` | 20,934 | 2,726 | 13.0 |
| operations/collection_events | `device_mass_kg_before` | 20,934 | 4,464 | 21.3 |
| operations/collection_events | `device_mass_kg_after` | 20,934 | 4,476 | 21.4 |
| operations/collection_events | `device_estimated_collected_kg` | 20,934 | 4,595 | 21.9 |
| operations/collection_events | `order_placed_at` | 20,934 | 7,111 | 34.0 |
| operations/collection_events | `actual_at` | 20,934 | 2,125 | 10.2 |
| telemetry/telemetry_daily_summary | `mass_kg_last_valid` | 159,579 | 15,378 | 9.6 |
| telemetry/telemetry_daily_summary | `mass_kg_max_valid` | 159,579 | 15,378 | 9.6 |
| finance/invoice_lines | `operator_job_ref` | 76,416 | 2,007 | 2.6 |

## Profile `enterprise`

```json
{
 "note": "Stress test of the enterprise profile, last run with generator v1.0.0rc1 (before the Europress review changes, demo seed). The enterprise profile is not distributed. v1.0.0 adds the operator scorecard and operator/contract action post-processing, which has not been timed at this scale.",
 "generator_version": "1.0.0rc1",
 "n_days": 730,
 "n_devices_public": 4500,
 "n_devices_holdout": 500,
 "runtime_seconds": 1691.3,
 "bytes_public": 1810140894,
 "bytes_private": 882362912,
 "peak_rss_main_mb": 3679.1,
 "peak_rss_largest_child_mb": 1420.3
}
```

## Automated tests

```
........................................................................ [ 51%]
...................................................................      [100%]
139 passed in 106.20s (0:01:46)
```

## Known limitations

See `ASSUMPTIONS_AND_LIMITATIONS.md`. Plausibility checks are sanity ranges chosen by Since AI, not calibration against measured data.