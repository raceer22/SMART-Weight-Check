# Summary — the weight data in 5 sentences (U13)

1. Each compactor reports an hourly fill-level estimate and (on 47 of 50 devices) a container mass in kg, and the collected weight per lift is estimated as mass before minus mass after the lift — in this dataset that weighing is a *simulated future scenario*, not something deployed today.
2. After removing 329 duplicate messages, 85.5 % of hourly mass readings are VALID, while the rest are missing (no sensor 6.0 %, sensor fault 0.8 %), negative (4.8 %), low-confidence (2.8 %) or spikes (0.1 %).
3. On ordinary single loads the device estimate is close to the weighbridge (median gap 45 kg ≈ 4 %, device slightly low), but gaps grow large when the driver loaded side waste or when several jobs were weighed together and the weighbridge split the net equally.
4. The main data traps are duplicate and buffered messages in `telemetry_hourly` (use `telemetry_dedup`), negative/flagged mass values, side waste the container scale never sees, and equal-split combined-load tickets that make the *weighbridge* allocation — not the device — wrong.
5. It matters because a weighing concept with ~1.5–1.75 % accuracy keeps ~95 % of 3 t loads within ±100 kg and catches ~95 % of +10 % tonnage overbilling, which turns the device weight into an independent check of what the customer is invoiced.

# Rules
- one finding = one bullet + where you saw it (table/script)
- reproduce everything with `python notes/explore.py` (quickstart data) and `python examples/weighing_accuracy_value.py data/competition/public`

# Findings

## Data

### U01 · Tables in the dataset (35) — `SHOW TABLES` in notes/explore.py, quickstart
- **Reference:** customers, sites, site_calendar, devices, device_installations, sensor_registry, contracts, contract_versions, operators, regions, price_index_monthly, material_classes, quality_grade_rules
- **Telemetry:** telemetry_hourly (raw ingest log), telemetry_dedup (SDK view, deduplicated), telemetry_daily_summary
- **Operations:** collection_events, weighbridge_tickets, quality_assessments, maintenance_work_orders
- **Finance:** invoices, invoice_lines
- **Labels (dev only):** anomaly_labels, reference_economics, reference_economics_monthly, reference_charge_lines, decision_truth, decision_outcomes, operator_scorecard, operator_action_values
- **Benchmark tasks:** decision_cases, task_ab_test_collections, task_b_test_invoice_lines, task_b2_scorecard_rows, operator_action_cases
- Quickstart sizes: 50 devices, 465 collection_events, 323 weighbridge_tickets, 4,486 daily summary rows, 106,751 hourly rows (Jul–Sep 2026).

### U02 · `collection_events` — one row per planned/ordered emptying (docs/DATA_DICTIONARY.md + 5 sample rows)
⭐ = top-5 columns for **weight**

| column | meaning | example |
|---|---|---|
| collection_id | event id | COL-00001-0001 |
| device_id / site_id / customer_id / contract_id | which compactor, where, whose, under which contract | CMP-00001 / SITE-00001 / ORG-0001 / CTR-00001 |
| operator_id | the hauler | OP-E |
| ⭐ operator_job_ref | hauler's job number — **the join key** to weighbridge tickets and invoice lines | OP-E-000010001 |
| trigger_type | why the lift happened (scheduled, on-call, customer request …) | CUSTOMER_REQUEST |
| original_trigger_type | for RESCHEDULED events, the original reason | CUSTOMER_REQUEST |
| status | outcome: COMPLETED, PARTIAL, SKIPPED_LOW_FILL, CANCELLED, MISSED, WASTED_TRIP | COMPLETED |
| cancellation_notice_hours | notice given for a cancel/skip | NULL |
| wasted_trip_reason | ACCESS_BLOCKED / NOTHING_TO_COLLECT | NULL |
| vehicle_id | truck used | OP-E-V14 |
| ⭐ driver_reported_side_waste | driver also loaded loose overflow next to the container (the container scale can't see it) | False |
| driver_reported_partial | container not fully emptied | False |
| device_fill_pct_before / _after | fill % the hour before / of the lift | 15.2 / 0.0 |
| ⭐ device_mass_kg_before | valid container mass before the lift | 540 kg |
| ⭐ device_mass_kg_after | valid container mass after the lift (can be slightly negative) | 10 kg |
| ⭐ device_estimated_collected_kg | before − after = device's estimate of what was collected (**not** a weighbridge value) | 530 kg |
| weight_reconciliation_status | naive device-vs-weighbridge check at extraction time | WITHIN_10PCT |
| invoice_match_status | naive job-ref match against invoices | MATCHED_BY_JOB_REF |
| order_placed_at / scheduled_at / actual_at | ordered / planned / actual service time (UTC) | 2026-07-03 07:00 / 11:00 / 07-04 05:22 |

### U03 · `telemetry_daily_summary` — the device's daily diary, built from deduplicated telemetry (docs/DATA_DICTIONARY.md + 5 sample rows)
| column | meaning | example |
|---|---|---|
| device_id, date | device and local date (key) | CMP-00001, 2026-07-01 |
| n_messages | unique hourly messages that day (max 24) | 24 |
| fill_pct_first / _last | first / last fill reading of the day | 3.2 / 3.7 |
| **fill_pct_max** / fill_pct_min | highest / lowest fill of the day | 3.9 / 0.0 |
| **mass_kg_last_valid** | last VALID or LOW_CONFIDENCE mass of the day | 95 kg |
| mass_kg_max_valid | highest valid mass of the day | 95 kg |
| n_valid_mass | messages with a usable mass | 21 |
| compaction_cycles | press cycles that day | 6 |
| hours_down | hours in DOWN state | 0 |
| **hours_full** | hours in FULL state (container full, customer can't use it) | 0 |
| n_buffered | messages delivered late after an outage | 0 |
| **data_completeness_pct** | n_messages / 24 | 100.0 |

### U04 · Devices per waste stream — `devices` table
| material_stream | devices |
|---|---|
| cardboard | 15 |
| mixed_waste | 14 |
| plastic_film | 11 |
| mixed_plastic | 9 |
| paper | 1 |

| has_weight_measurement | devices |
|---|---|
| True | 47 |
| False | 3 (2 cardboard COMBI, 1 mixed_plastic DUO) |

- 36 of 50 devices handle recyclables that can earn a material credit (cardboard, paper, plastics); 14 are mixed waste, which always costs money. — `devices`

### U05 / U06 · Fill and mass over time — CMP-00001 (mixed_waste, DUO, 8 m³, ON_CALL) — notes/explore.py
- `notes/fill.png`: clear saw-tooth, fill climbs over ~1–2 weeks and drops at each lift; collections get more frequent from mid-August as the fill rate rises.
- `notes/mass.png`, `notes/fill_mass.png` (both on one chart + collection markers).
- **Fill and mass move together** (correlation of daily max fill vs daily max mass = 0.99); mass drops lower than fill on lift days because `mass_kg_last_valid` is the post-lift reading while `fill_pct_max` still includes the pre-lift hours. — `telemetry_daily_summary`
- On 4–6 Sep CMP-00001 was FULL for 44 h before an ad-hoc lift (COL-00001-0011); that lift has side waste and is the biggest gap in the U09 sample (device 2,665 kg vs weighbridge 3,400 kg). — `telemetry_daily_summary` + `collection_events`

## Data quality

### U07 · Duplicate telemetry messages — `telemetry_hourly`
| all_rows | unique_msgs | duplicates |
|---|---|---|
| 106,751 | 106,422 | **329** |
- `telemetry_dedup` (SDK view) has exactly 106,422 rows → always use it for counts/sums. 1,651 rows arrived BUFFERED (late, after an outage). — `telemetry_hourly`, `telemetry_dedup`

### U08 · Missing and bad weight readings — `telemetry_dedup` (106,422 rows)
| check | rows |
|---|---|
| mass_kg IS NULL | 7,243 (6.8 %) — 6,396 no sensor + 847 sensor fault |
| mass_kg < 0 | 5,188 (4.9 %) — 5,137 NEGATIVE_READING + 51 SUSPECT_SPIKE |

| quality_flag | rows | % |
|---|---|---|
| VALID | 90,986 | 85.5 |
| NO_WEIGHT_SENSOR | 6,396 | 6.0 |
| NEGATIVE_READING | 5,137 | 4.8 |
| LOW_CONFIDENCE | 2,957 | 2.8 |
| SENSOR_FAULT | 847 | 0.8 |
| SUSPECT_SPIKE | 99 | 0.1 |

| sensor_status | rows | % |
|---|---|---|
| OK | 96,176 | 90.4 |
| NOT_INSTALLED | 6,396 | 6.0 |
| DEGRADED | 3,003 | 2.8 |
| FAULT | 847 | 0.8 |

- Filtering on `quality_flag IN ('VALID','LOW_CONFIDENCE')` (what the daily summary does) removes all NULL and negative masses. Negative values go down to −2,500 kg, so they are not just "near-zero noise". — `telemetry_dedup`

## Weight

### U09 · Device estimate vs weighbridge — `collection_events` ⨝ `weighbridge_tickets` on `operator_job_ref`
20 example rows (diff_kg = device_kg − bridge_kg):

| collection_id | device_kg | bridge_kg | diff_kg | loads_on_vehicle | side_waste |
|---|---|---|---|---|---|
| COL-00001-0001 | 530 | 520 | 10 | 1 | F |
| COL-00001-0002 | 1930 | 1960 | −30 | 1 | F |
| COL-00001-0003 | 1635 | 1700 | −65 | 1 | F |
| COL-00001-0004 | 905 | 980 | −75 | 1 | T |
| COL-00001-0005 | 2080 | 2140 | −60 | 1 | F |
| COL-00001-0006 | 2000 | 2040 | −40 | 1 | F |
| COL-00001-0007 | 2505 | 2520 | −15 | 1 | F |
| COL-00001-0008 | 2125 | 2120 | 5 | 1 | F |
| COL-00001-0009 | 2145 | 2220 | −75 | 1 | F |
| COL-00001-0010 | 2435 | 2540 | −105 | 1 | F |
| **COL-00001-0011** | 2665 | 3400 | **−735** | 1 | **T** |
| COL-00001-0012 | 2265 | 2380 | −115 | 1 | F |
| COL-00001-0013 | 2140 | 2220 | −80 | 1 | F |
| COL-00001-0015 | 1760 | 1840 | −80 | 1 | F |
| COL-00002-0001 | 1125 | 1100 | 25 | 1 | F |
| **COL-00002-0003** | 2205 | 1680 | **+525** | **2** | T |
| **COL-00002-0004** | 2205 | 1780 | **+425** | **2** | F |
| COL-00002-0006 | 2840 | 2880 | −40 | 1 | F |
| COL-00002-0007 | 1970 | 2000 | −30 | 1 | F |
| COL-00002-0008 | 2010 | 2140 | −130 | 1 | F |

All 294 joined rows (out of 354 collections with a device estimate), grouped by cause:

| loads_on_vehicle | side_waste | n | mean diff kg | median abs diff kg | median abs % |
|---|---|---|---|---|---|
| 1 | no | 241 | −56 | 45 | 4.1 |
| 1 | yes | 21 | −313 | 170 | 7.7 |
| 2 | no | 28 | −153 | 723 | 48.5 |
| 2 | yes | 4 | +304 | 345 | 17.8 |

- **Why they differ:** big gaps come from (a) **combined loads** — two jobs weighed together and the net split equally (`EQUAL_SPLIT_COMBINED_LOAD`), so the *weighbridge allocation* is wrong per job, not the device; and (b) **side waste** — loose overflow loaded next to the container is on the truck but never on the container scale, so the device reads low. On clean single loads the device reads slightly low (≈ −56 kg) and is within ~4 %. A difference is not automatically the operator's fault. — notes/explore.py U09
- Of 465 collections, 63 have no published weighbridge ticket and 29 have no device estimate (`weight_reconciliation_status`).

### U10 · What each weighing accuracy is worth — `examples/weighing_accuracy_value.py data/competition/public`
Reference = 10,342 shared single-load weighbridge tickets (competition data), absolute floor 15 kg.

| concept σ (% of load) | within ±100 kg on 2.5–3.5 t loads | median €/t error % | p95 €/t error % | detects +10 % overbilling | false alarms |
|---|---|---|---|---|---|
| 0.5 | 1.000 | 0.62 | 3.59 | 0.947 | 0.0084 |
| 1 | 0.998 | 0.85 | 3.54 | 0.947 | 0.0084 |
| 1.5 | 0.983 | 1.10 | 3.83 | 0.950 | 0.0101 |
| **≈1.75 ⭐ (~95 % target)** | **0.948** | **1.27** | **4.10** | **0.946** | **0.0123** |
| 2.5 | 0.821 | 1.75 | 5.47 | 0.925 | 0.0177 |
| 5 | 0.532 | 3.37 | 10.2 | 0.467 | 0.0204 |
| 10 | 0.259 | 6.65 | 20.11 | 0.156 | 0.0215 |

- ⭐ The ~95 % within ±100 kg row is **σ ≈ 1.75 %** (from a second run with `--sigmas 1.5,1.75,2,2.25`; σ 2 % already drops to 0.907). Results shift ±1–2 points between runs because the script's random draws depend on which sigmas are listed (1.5 % gave 0.983 in one run, 0.969 in the other).
- Today's dataset device estimate vs weighbridge: median |diff| 2.76 %, p95 25 %, only **68.5 %** of 3 t loads within ±100 kg → the simulated sensor is well below target. — script footer
- Verifying operator tonnage (overbilling detection) collapses above ~2.5 %; cost-per-tonne reporting tolerates much more. Device weight is never a billing basis. — script footer

### U11 · Three ways to weigh a compactor (idea level, web research)
| idea | rough cost | easy retrofit? | expected accuracy | notes |
|---|---|---|---|---|
| **Load cells under the container** (load-pin cells as roller/wheel axles in a base frame) | medium | yes, for DUO containers on rails/rollers; harder for COMBI | best of the three — industrial load cells are typically ≤1 % as a system *(assumption; no retrofit-specific test data found)* | a US patent describes exactly this retrofit for waste compactors |
| **Hydraulic pressure of the lift arm / truck hook** (on the operator's vehicle) | medium–expensive (per truck, not per container) | yes, but on the hauler's fleet, not ours | ~1 % of **gross** vehicle weight (vendor claim) → worse on the net payload | data is owned by the operator, so it's not independent from the weighbridge |
| **Bolt-on strain gauges on the frame/legs** | cheap | yes, just bolted on | 3–5 % (vendor specs; ±1–2 % only with high strain at the mount) | proven on silos/hoppers, not compactors; temperature and press vibration add error |
| *(not a real option)* fill % / packing pressure → estimated weight | free | yes | poor — a patent calls it guessing weight "from past experience" | this is what devices without a weight sensor do today |

Sources: [US11162834B2 – Weight-measurement retrofitting for waste compactors](https://patents.google.com/patent/US11162834), [US12379240B1 – container weighing with load cells](https://patents.google.com/patent/US12379240), [Vulcan roll-off on-board scale (Trailer/Body Builders)](https://www.trailer-bodybuilders.com/archive/article/21723735/vulcan-offers-on-board-scale-for-roll-offs), [Recycling Product News – on-board scale for roll-offs](https://www.recyclingproductnews.com/article/8417/on-board-scale-built-for-roll-offs), [Anderson-Negele Microcell bolt-on sensor](https://www.anderson-negele.com/uk/wp-content/uploads/sites/11/2021/04/Microcell_L-Cell_at_a_glance_60034_1.0_en_eu.pdf), [Applied Measurements bolt-on sensors](https://directindustry.com/prod/applied-measurements/product-11673-862661.html), [Bolt-on force sensors for retrofit weighing (automation.com)](https://www.automation.com/article/bolt-on-force-sensors-for-reliable-retrofit-weighi)

### U12 · Our weighing accuracy target 

- **Concept:** load-pin load cells in a retrofit base frame / roller axles under the container — the only one of the three that is ours (not the hauler's) and plausibly reaches ~1–1.5 %.
- **Accuracy:** design target **σ = 1.5 % of the load (15 kg floor)** → 97–98 % of 3 t loads within ±100 kg, median €/t error ~1.1 % (U10 table); σ 1.75 % is the minimum that still hits the ~95 % challenge target.
- **What it lets the customer check:** flag ~95 % of invoices where tonnage is overbilled by +10 %, with ~1 % false alarms, and see their real cost per tonne per container — as an independent check against the operator's weighbridge, never as the billing basis.

## Customer value

## Business model

## Open questions
- U12 concept and σ target were proposed during the Epic 1 analysis and still need a team decision.
- U11 accuracy figures are vendor/patent claims; none are independent tests on a compactor.
- Should combined-load tickets be excluded from any reconciliation, or re-split using device weights?
