# Our pitch in one sentence (P01)

> For businesses that pay for waste by the lift and by the tonne but only ever see the weight their operator reports, **SMART Weight Check** uses an independent scale in the Europress compactor to check every lift and every per-tonne invoice line against the contract, and turns each difference into a proposal a human approves, so they pay for the service they actually received.

*All data is synthetic. Every € figure below is estimated from synthetic records or a hypothetical assumption, not a demonstrated saving.*

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

### U12 · Our weighing accuracy target (decided)

- **Concept:** a **load-cell weigh frame** under the container's standing position: two low-profile rails with four 10 t shear-beam load cells, read by a 4-channel module in the SMART cabinet. Retrofit kit for the installed base, factory option on new compactors. It is the only one of the U11 options that is owned by Europress/the customer (not the hauler) and plausibly reaches 1–1.5 %. Full concept: `submission/1_WEIGHING_CONCEPT.md`.
- **Accuracy:** design target **σ = 1.5 % of the load (15 kg floor)** → 97–98 % of 3 t loads within ±100 kg, median €/t error ~1.1 % (U10 table). σ 1.75 % is the minimum that still hits the ~95 % challenge target, and above ~2.5 % the overbilling check stops working.
- **What it lets the customer check:** flag ~95 % of invoices where tonnage is overbilled by +10 %, with ~1 % false alarms, and see their real cost per tonne per container, as an independent check against the operator's weighbridge, never as the billing basis.

### Weighing without a scale on every container (research) — `notes/weight_without_scale.py`, `notes/rotation_experiments.py`, `notes/precision_experiments.py`, competition data
Truth = shared single-load weighbridge net (no side waste). Leave-device-out, so a device never trains on itself.

| variant | median abs error per lift | 3 t loads within ±100 kg |
|---|---|---|
| A stream profile, no ML (density × volume × fill) | 14.1 % | 16 % |
| B ML (gradient boosting: stream, press data, sector) | 8.6 % | 27 % |
| C rotation kit, 3 months on each device | 6.9 % | 31 % |
| f learn density from the device's last 5 shared tickets (no kit) | 7.0 % | – |
| D integrated scale on every device (dataset reference) | 2.7 % | 68 % |
- Errors shrink when summed: 7.2 % per lift → 5.8 % per device-month → **4.3 % per device-year** (rotation method b). Good enough for a €/t trend, **not** for checking an invoice line (needs σ ≤ ~2.5 %, U10). *(estimated)*
- The error is worst at low fill (< 40 %: 14 %), exactly the lifts where "was this lift necessary?" matters. The fill sensor alone jitters by σ 2.3 points between quiet hours.
- ML beats the transparent density rule (8.6 % vs 14.1 %), so we use ML only here, for the no-hardware estimate; every proposal stays rule-based and explainable.
- Averaging quiet readings or a rolling gain correction does not push the simulated scale below ~1.7 % median error, and the weighbridge itself (σ 12 kg + 20 kg resolution ≈ 0.5 % on 3 t) cannot verify anything better than ~1 %. → **Decision:** a real scale is needed for invoice checks; the no-scale model becomes the free "value scan" that shows where a scale pays.

## Customer value

Evidence tags used from here on (rubric in docs/BENCHMARK.md):
- **observed**: read straight from a record (collection event, weighbridge ticket, invoice line, site calendar).
- **simulated**: comes from the SMART device (fill %, container mass, device-estimated kg). Device weighing is a simulated future scenario.
- **estimated**: our calculation from records, e.g. € per tonne or a median.
- **hypothetical**: an assumption. All tariffs in the dataset are hypothetical customer–operator prices.
- All data is synthetic. Not Europress data.

### C01 · Cost calculator (Task A) — `baselines/b1_economic_calculator.py` → `my_task_a.csv`, quickstart, validation split
| metric | score |
|---|---|
| events scored / coverage | 74 / 1.0 |
| collection_cost_eur exact to the cent | 1.0 |
| processing_cost_eur exact to the cent | 1.0 |
| penalties_eur exact to the cent | 1.0 |
| material_credit_eur exact to the cent | 1.0 |
| net_material_contribution_eur exact to the cent | 1.0 |
| €/t within 5 % (weighbridge / invoice tonnage) | 1.0 / 1.0 |
| €/t made up where the reference is NULL | 0 |
- The baseline is exact on quickstart, so the demo app reuses `my_task_a.csv` for € per tonne. — `python -m europress_data.evaluate --task A ...`
- Mass basis of all 465 events: 323 weighbridge, 52 invoice quantity, 11 device estimate, 79 not a lift. — b1 output

### C02 · 10 most expensive devices per tonne — `examples/first_analysis.py data/quickstart/public`
🔻 = median fill before lift below 50 %. All € figures **estimated** (contract calculation with hypothetical tariffs). Lifts and mass basis **observed**, fill **simulated**.

| device | stream | policy | lifts | t | €/t | benchmark €/t | vs benchmark | median fill before | mass basis |
|---|---|---|---|---|---|---|---|---|---|
| CMP-00016 | mixed_plastic | ON_CALL | 7 | 1.82 | 618.8 | 98.4 | 6.29× | 56.8 % | WB 6, invoice 1 |
| CMP-00037 🔻 | plastic_film | ON_CALL | 5 | 2.08 | 436.5 | 106.7 | 4.09× | 39.4 % | WB 3, invoice 2 |
| CMP-00029 🔻 | plastic_film | ON_CALL | 3 | 1.02 | 531.4 | 143.1 | 3.71× | 39.2 % | WB 3 |
| CMP-00004 | plastic_film | ON_CALL | 9 | 5.24 | 377.3 | 105.6 | 3.57× | 56.5 % | WB 7, device 2 |
| CMP-00049 🔻 | mixed_plastic | ON_CALL | 6 | 1.90 | 471.9 | 145.4 | 3.25× | 34.7 % | WB 5, invoice 1 |
| CMP-00010 | plastic_film | ON_CALL | 4 | 3.94 | 185.9 | 60.5 | 3.08× | 66.8 % | WB 3, invoice 1 |
| CMP-00046 🔻 | cardboard | ON_CALL | 5 | 4.08 | 257.9 | 110.0 | 2.34× | 25.1 % | WB 4, device 1 |
| CMP-00017 🔻 | plastic_film | ON_CALL | 3 | 1.18 | 433.7 | 189.0 | 2.29× | 41.6 % | WB 3 |
| CMP-00050 🔻 | paper | HYBRID | 2 | 1.56 | 126.7 | 58.9 | 2.15× | 38.1 % | WB 1, invoice 1 |
| CMP-00040 | mixed_plastic | ON_CALL | 4 | 1.62 | 790.3 | 386.4 | 2.05× | 52.4 % | WB 2, invoice 2 |
- 6 of the top 10 lift at a median fill below 50 %. — first_analysis.py
- **No biowaste in the quickstart data** (streams are cardboard, mixed waste, plastic film, mixed plastic, paper), so none of these are explained by the 7-day hygiene rule. Other legitimate reasons still have to be checked per lift (max-interval rule, pre-closure, wasted trips). — `devices`
- Most devices have only 2–9 lifts in the quarter, so one cheap or expensive lift moves €/t a lot. CMP-00024 (cardboard, 5×/week fixed schedule) sits just outside the top 10 at 1.83× with 55 lifts at a median 28 % fill. It is the most robust over-servicing case. — first_analysis.py top 15

### C03 · The story of CMP-00046 (demo storyline)
CMP-00046 is a 10 m³ cardboard compactor at Lohja site 7 (customer ORG-0004), emptied on call at 76 % fill by operator OP-A *(observed: `devices`)*. On 13–15 July its fill reading stayed at 88 % for three days while the container scale never showed more than 35 kg *(simulated: `telemetry_daily_summary`)*, and the four on-call orders that followed all ended as wasted trips with “nothing to collect”, invoiced at €86.55 each, €346 in total *(observed: `collection_events`, `invoice_lines`)*. Between 1 and 11 September the customer then requested three lifts at only 6 %, 8 % and 25 % full *(simulated)*, which moved 85 kg *(simulated: device estimate, no ticket)*, 360 kg and 500 kg *(observed: weighbridge)*. Each of those lifts was invoiced €193.71 for the lift fee and 47 km of transport *(observed)*, which works out at €2,279, €538 and €387 per tonne against a contract benchmark of €110 per tonne *(estimated, hypothetical tariffs)*. Over its five lifts the device moved 4.08 t for €1,053 of collection cost, €258 per tonne or 2.3× the benchmark, before the €346 of wasted-trip fees *(estimated)*. A weight view would have shown the customer that the container was nearly empty each time, but we cannot prove the September orders were unnecessary: the customer may have had reasons we cannot see, and labels for that period are hidden *(hypothetical)*.
- Neutral reading: the July wasted trips are **device-caused** (a fill reading that stayed falsely high), not operator-caused. The operator did what was ordered.

### C04 · Anomaly baseline (Task B) — `baselines/b2_rules_anomaly.py` → `my_task_b.csv`, quickstart, validation split
| family | cases | flagged | correct | precision | recall | F1 |
|---|---|---|---|---|---|---|
| **PREMATURE_UNJUSTIFIED** ⚠ weakest | 7 | 1 | 1 | 1.00 | 0.14 | **0.25** |
| UNMATCHED_LINE | 4 | 2 | 2 | 1.00 | 0.50 | 0.67 |
| CONTAMINATION_VALUE_LOSS | 6 | 5 | 5 | 1.00 | 0.83 | 0.91 |
| COST_PER_T_HIGH | 8 | 7 | 7 | 1.00 | 0.88 | 0.93 |
| WEIGHT_DISCREPANCY | 9 | 8 | 8 | 1.00 | 0.89 | 0.94 |
| DELAYED_COLLECTION, WRONG_SURCHARGE, MISSING_LINE, UNINVOICED_COLLECTION | 1–3 each | all | all | 1.00 | 1.00 | 1.00 |
| REJECTED_LOAD, OUTDATED_TARIFF, WEIGHT_BASIS_MISMATCH | 0 | 0 | — | — | — | not scored |
| DUPLICATE_LINE | 0 | 2 | 0 | — | — | not scored (2 false alarms) |
- **macro F1 0.856** (detection only 0.849). Macro F1 averages only families that have cases in the split. — `python -m europress_data.evaluate --task B ...`
- **Weakest family: PREMATURE_UNJUSTIFIED** (unnecessary early lifts). The baseline finds only 1 of 7. On the competition data it is also weak: F1 0.72, recall 0.59.
- Validation has only 1–9 cases per family, so one case moves F1 a lot.

### C05 · Why premature lifts are missed — `anomaly_labels.parquet` ⨝ `collection_events`
The baseline rule only flags **scheduled** lifts below 40 % fill. The 41 dev labels come from three mechanisms: 22 schedule-driven (S01), 9 precautionary customer orders (S39), 10 false-high fill readings (S40). The baseline catches 21 of the 22 schedule-driven and none of the other 19.

1. **COL-00001-0001 · precautionary order (S39, clear, €175 at stake).** CMP-00001 is mixed waste on call. The customer ordered a lift on Friday 3 July and it happened on Saturday morning, when the site was closed for the weekend *(observed: `collection_events`, `site_calendar`)*. The container was only 15 % full and gave 530 kg *(simulated)* / 520 kg on the weighbridge *(observed)*, against a typical full load of about 2,140 kg for this device *(estimated)*. It is published as CUSTOMER_REQUEST, so a rule that only looks at SCHEDULED lifts can't see it.
2. **COL-00026-0006 · fill sensor reads falsely high (S40, clear, €219 at stake).** CMP-00026 (mixed waste, on call) showed 94.7 % fill without change from 26 August for about 2.5 days, while the mass stayed at 400–750 kg *(simulated)*. When it was really full on 24 August it weighed about 2,300 kg. Two on-call lifts followed, 23 hours apart: COL-00026-0005 took 720 kg and COL-00026-0006 only 220 kg *(observed: weighbridge)*. The fill reading says “94.7 % full” before both lifts, so any fill-based rule thinks they were justified. Only the weight shows the truth.
3. **COL-00006-0008 · schedule just above the cut-off (S01, borderline, €123 at stake).** CMP-00006 is cardboard on a hybrid schedule of 2 lifts a week. This scheduled lift ran at 41.1 % fill *(simulated)* with 540 kg on the weighbridge *(observed)*, just above the baseline's 40 % threshold, so it is missed.
- **Trap:** low fill alone is not enough. 23 early lifts are labelled EARLY_JUSTIFIED, i.e. not an anomaly (max-interval rule, minimum frequency, some customer requests), e.g. COL-00035-0001 at 7 % fill on the day before an 8-day summer shutdown. — `anomaly_labels`, `site_calendar`

**Idea for a better rule** (`notes/premature_rule.py`, adds to the baseline, does not replace it):
- *Precautionary:* on-call device, CUSTOMER_REQUEST, fill before < 45 %, and the lift is on a Fri/Sat/Sun or the site is closed the next day.
- *False-high fill:* ON_CALL_ORDER where the collected weight is < 40 % of the device's own typical full load (median kg on its lifts that started ≥ 70 % full). This is the weight data doing what fill cannot.

| PREMATURE_UNJUSTIFIED, validation | precision | recall | F1 | justified lifts wrongly flagged |
|---|---|---|---|---|
| quickstart baseline | 1.00 | 0.14 | 0.25 | 0 |
| quickstart + idea | 1.00 | 1.00 | 1.00 | 0 |
| competition baseline | 0.90 | 0.59 | 0.72 | 0 |
| competition + idea | 0.86 | 0.87 | **0.86** | 9 |
- Quickstart has only 7 validation cases, so trust the competition row. Macro F1 on competition validation goes from 0.731 to 0.742.
- Excluding lifts before closures of 3+ days made no difference, so the rule stays simple.

### C06 · Operator scorecard (Task B2) — `notes/scorecard.py` → `my_scorecard.csv`, split all
- 18 rows (operator × region × month). The evaluator scores only rows with ≥ 10 jobs and a label row, which leaves 5. **Score 78.3 / 100.** — `python -m europress_data.evaluate --task B2 ...`
- Exact on on-time rate, missed visits, ticket sharing and order-to-lift time. Weakest metrics: weight bias (score 0.26, MAE 3.0 points), discrepant line rate (0.32) and billing overcharge (0.49, MAE 0.84 points).

### C07 · Punctuality per operator — `notes/punctuality.py` → `notes/punctuality.png`
On time = the lift happened within ±2 h of the scheduled time. Mean of the monthly rates per region, Jul–Sep 2026 *(estimated from observed lift times)*.

| operator | on time | region-months |
|---|---|---|
| OP-E | 71 % | 3 |
| OP-A | 69 % | 6 |
| OP-B | 55 % | 6 |
| OP-C | 39 % | 3 |
- Monthly values swing widely: OP-B ranged from 33 % to 77 %, so a quarter is a short window. OP-D has no rows in quickstart. — `my_scorecard.csv`
- Neutral wording for the pitch: “OP-C was on time in 39 % of visits”, not a judgement of the operator. Lateness can come from orders placed late or access problems at the site.

### C08–C14 · Customer screen and demo app — `notes/customer_screen_sketch.png`, `app/app.py`
- **Sketch (C08):** one page, top to bottom: device picker → fill % chart and weight chart (two charts, one axis each) → € per tonne, benchmark ratio, lifts and tonnes, fees for trips without a lift → every lift with its weight source → proposals with Approve / Reject. Agreed: the built app follows it, with one addition (the weight check, below).
- **Run the app:** `pip install -e ".[app]"`, create `my_task_a.csv` (C01) and `my_task_b.csv` (C04), then `streamlit run app/app.py`. It opens on CMP-00046, the C03 story device.
- **Weight never made up:** € per tonne = lift cost ÷ tonnes, using only lifts with a weight source. A lift without one shows “unknown”. Quickstart has no such lift, but CMP-00049's first lift has a 0 kg ticket and shows “unknown”.
- **Proposals:** rule-based flags from the Task B baseline, each with what was seen, why and what to check before acting. Approve / Reject only records a demo decision, and Undo reverses it.
- **Evidence tags (C14):** every number has an observed / simulated / estimated / hypothetical caption or column tag. The footer says “All data is synthetic. Not Europress data.”
- The chart caption says **simulated**, not “observed” as the C11 task text suggests. Device weighing is a simulated future scenario (U02), so “observed” would over-claim.
- The chart uses the highest valid reading of the day for both fill and weight. The C11 hint used `mass_kg_last_valid`, which drops on lift days while fill does not (U06).
- **C05 decision:** the better premature rule is now in the app (`app/weight_rules.py`, shared with `notes/premature_rule.py`). Proposals always need a human, so finding 111 more real cases is worth 9 more questions on justified lifts. CMP-00046's lifts on 4 and 11 September now appear as proposals; the 1 September lift (a Tuesday, site open next day) still does not.

### Weight check — the product feature (`app/weight_rules.py` → app section "Weight check"), quickstart, all 50 devices
Per lift: invoiced tonnes (per-tonne lines: processing, haul per tonne, material credit, rejection) *(observed)* vs device weight *(simulated)* vs the operator's ticket *(observed, when shared)*. Tolerance max(100 kg, 3.3 %), the dataset's accuracy target *(hypothetical)*. € at stake = difference × the invoice's own € per kg *(estimated)*.

| result | lifts | what it means |
|---|---|---|
| agrees | 205 | invoice and device weight within tolerance |
| device differs from ticket | 58 | invoice = ticket, the device disagrees → a question about the **device scale**, not the operator |
| explained: combined load | 29 | two jobs weighed together, net split equally; the device shows the real per-container split |
| no device weight | 28 | no sensor or a sensor fault |
| explained: side waste | 9 | loose waste loaded next to the container; the container scale cannot see it |
| in the customer's favour | 8 | no action |
| review: no ticket / invoice vs ticket | 4 | the only lift-level billing questions |
- 341 lifts carry per-tonne lines. Only **4** become billing questions; **13 of 47** weighing devices get one "check the scale" proposal because their device repeatedly disagrees with a matching invoice and ticket. That fits U10: the simulated sensor is below target, which is why the concept has a rolling weighbridge-referenced span check.
- **Combined loads answer an open question:** don't drop them, re-split them by device weight. Example *(observed tickets, simulated device)*: CMP-00042 and CMP-00034 (same customer) shared a truck; the equal split billed CMP-00042's site for 2.94 t when its container held 580 kg, about €299 of per-tonne charges at the wrong site. The customer's total is right; each site's € per tonne is not. Nobody did anything wrong.
- CMP-00046 (the story device) has no per-tonne lines: its contract bills per lift and per km, so the weight changes its € per tonne, not its invoice. The demo switches to CMP-00042 and CMP-00047 for the weight check.

## Business model

### B01 · Rubric for Task D and E (docs/BENCHMARK.md) — and where we meet it
- [x] **Evidence separation:** every figure tagged observed / estimated / simulated / hypothetical (app captions and column help, this file, `configs/our_params.yaml` comments).
- [x] **Traceability:** row-level: lift → job ref → weighbridge ticket → contract → invoice lines (Task A baseline; app lift table and weight check show each step).
- [x] **Constraints and uncertainty:** quantified: hygiene/overflow limits via simulated counterfactuals (over-servicing realises 30–39 %), sensor quality (85.5 % VALID), missing tickets (63 of 465), side waste, combined loads, tolerance ±100 kg / 3.3 %, run-to-run noise ±1–2 points.
- [x] **Pricing and adoption reasoning:** prices from the value per device-month distribution, a price sweep and a price × adoption sensitivity table (B04, B08).
- [x] **Human approval:** every proposal has a rationale, a "check before acting" step and Approve / Reject / Undo; nothing executes.
- [x] **Avoids over-claiming:** B09 list below; "synthetic" on the app, the docs and the money slides.
- [x] **Neutral tone towards operators:** combined loads, side waste and device scale issues are separated from billing questions; P09 wording check done.

### B02 · Five service ideas and the choice
No team vote was possible, so the ideas were scored 1–3 on five criteria.

| # | idea | who pays and why | value in the data | uses the weight | today's role | revenue | total |
|---|---|---|---|---|---|---|---|
| 1 | **SMART Weight Check**: check every lift and per-tonne invoice line against device weight and contract, proposals a human approves | customer, per device-month: billing corrections, avoided lifts, better terms | 3 | 3 | 3 | 2 | **11** |
| 2 | Monthly weight and €/t report per site (also for sustainability reporting) | customer: transparency | 2 | 2 | 3 | 1 | 8 |
| 3 | Operator tendering help: scorecard + verified tonnage for the tender pack | customer, per tender | 2 | 2 | 2 | 1 | 7 |
| 4 | Weighing as a compactor option (factory) and retrofit kit | customer, as equipment | 2 | 3 | 3 | 2 | 10 |
| 5 | *Hypothesis:* per-tonne full service, Europress procures transport and treatment | customer, one €/t price | 3 | 3 | 1 | 3 | 10 |
- **Chosen: #1 SMART Weight Check**, with #2 as the free entry tier ("value scan", no hardware), #4 as the hardware that enables it, and #5 kept as a clearly labelled long-term hypothesis.
- **Who pays and why:** the waste-producing customer pays **€15 per device per month** because the check returns a median **€36 per device-month** of realisable value *(estimated)*, about 2.4× the fee, from billing corrections, avoided lifts, contestable service charges and better contract terms.

### B03–B06 · Our parameters — `configs/our_params.yaml` (all hypothetical, each with its reason in the file)
| parameter | value | why |
|---|---|---|
| price per device-month | **10 / 15 / 25 €** | realisable value per device-month: 25th / 50th / 75th percentile €20 / €36 / €72; €15 maximises fee revenue under the 3× rule (B08 sweep); €25 ≈ 75th percentile / 3 |
| outcome-based alternative | 20 % of verified savings | for customers who won't pay up front |
| onboarding | €800 per customer, €100 per device | ~1 analyst day to load contracts and map invoice lines; ~1.5 h per device incl. a scale check against first tickets |
| operating cost | €3 per device-month | cloud compute and storage; SMART modem and data plan already exist |
| support | €50 per customer-month | ~1 h of an analyst who reviews proposals before the customer sees them |
| adoption | 10 / 25 / 40 % of eligible | existing SMART customers via account managers (warm channel) |
| purchase rule | value ≥ 3× fee | B2B rule of thumb; 2× and 4× tested |
| realisation | billing 0.7 · over-servicing 0.35 · contamination 0 · contract 0.25 · operator performance 0.25 · tendering 0.4 | from the dataset's published rules (dispute recovery 0.9, renegotiation success 0.5, tender success 0.8) and simulated counterfactuals (lift cuts realise 30–39 % of the naive saving); contamination is out of scope because weight cannot see quality |
| future models | off in the main case | reported separately as hypotheses |

### B07 · Calculator result — `python baselines/business_case.py competition --params configs/our_params.yaml --out our_business_case`
Competition data, 52 public customers, 447 devices, annual waste spend €5.19 M *(estimated)*.
- **Customer value:** identified **€1.18 M/year (22.8 % of spend)**, realisable with our shares **€332 k/year (6.4 % of spend)** *(estimated)*. Biggest realisable levers: operator performance €102 k, over-servicing €81 k, contract review €60 k, tendering €58 k, billing review €31 k.
- **Base case (€15, 25 % adoption):** 23 of 52 customers eligible, 5.8 adopt (61 devices). Revenue **€11.0 k/year**, operating + support €5.7 k, one-off onboarding €10.7 k → year 1 **−€5.4 k**, then **+€5.4 k/year**, **payback 2.0 years** *(hypothetical)*. Per adopting device: €180 revenue vs ~€92 cost to serve per year.
- **The money is small on this sample, and we say so.** The subscription is a beachhead. The larger value for Europress is (1) weighing as a reason to choose a Europress compactor (factory option), and (2) verified weight as the prerequisite for the per-tonne models in B08 §9 (≈ €156 k/year gross margin on this same sample at 3 %, a hypothesis).
- Outputs: `our_business_case/business_case.md`, `business_case_customers.csv`, `business_case_scenarios.csv`.

### B08 · Sensitivity — `python notes/business_case_sensitivity.py` → `our_business_case/sensitivity.md`
Yearly profit after onboarding (steady state: fee revenue − operating cost − support), EUR, hypothetical:

| price €/device-month | adoption 10 % | adoption 25 % | adoption 40 % |
|---|---|---|---|
| 10 | 943 | 2,358 | 3,773 |
| **15** | 2,148 | **5,370** | 8,592 |
| 25 | 1,735 | 4,338 | 6,941 |
- **Which assumption matters most? Price.** At €10 the service takes 6.5 years to pay back its onboarding, because it attracts small customers who cost more to support than they pay; at €15–25 it pays back in 1–2 years. One-at-a-time swing in 3-year profit: price €16.5 k > support cost €12.4 k > operating cost €11.0 k > value realisation €6.9 k ≈ onboarding €6.9 k > adoption €6.5 k > purchase rule €5.4 k.
- **Who to sell to:** at €15, customers with 16+ devices bring ~€4.0 k/year profit each, 6–15 devices ~€0.7 k, and 2–5 devices lose ~€0.2 k (support > fee). → Analyst-supported service from ~6 devices; self-service for small fleets.
- **Hardware payback for the customer** (value after the €15 fee): factory option €1,200 → 2.9 years at the median device, 50 % of devices within 3 years; retrofit frame €3,400 → 8.2 years at the median, only 29 % within 5 years. → **Weigh where it pays:** factory option on new compactors, retrofit only where the value scan shows high value.
- **Future hypotheses** (not today's role, all 52 customers, per year): transport procurement €96 k customer value (5 % × 0.5), materials marketplace €59 k customer value (+€5/t × 0.5), tonne-based full service €156 k gross margin for Europress (3 % of spend).

### B09 · What we have NOT proven (docs/ECONOMIC_MODEL.md §6, docs/ASSUMPTIONS_AND_LIMITATIONS.md)
- We have not shown that **any customer would pay €15 per device-month**: no customer was interviewed; the price is derived from synthetic value.
- We have not shown that the **identified value is real**: tariffs are hypothetical, the world is synthetic, and realisation shares are our assumptions. Only over-servicing is grounded in simulated counterfactuals, and a simulated counterfactual is not causal evidence.
- We have not shown that a **load-cell frame reaches σ 1.5 % on a real compactor**, in a Finnish winter, under hooklift loading: the accuracy budget is an engineering estimate, nothing was built or tested, and the dataset cannot validate hardware.
- We have not shown the **hardware costs** (€1,200 factory, €3,400 retrofit): indicative BOM, no supplier quotes.
- We have not shown that **operators accept device weight as evidence**, share tickets on request (the dataset assumes 60 %), or re-split combined loads.
- We have not shown that **avoiding "early" lifts is safe**: hygiene rules, overflow and site reasons make some of them right (23 EARLY_JUSTIFIED labels in quickstart).
- We have not shown that the **future models** are possible: billing on device weight would need a legal-for-trade scale (EU non-automatic weighing instruments directive 2014/31/EU) and a role Europress does not have today.

## Open questions
- U11 accuracy figures are vendor/patent claims; none are independent tests on a compactor. → Phase 1 yard test in the validation plan.
- C03: are CMP-00046's September low-fill lifts really unnecessary? Their labels are in the hidden test period. The app asks, it does not decide.
- Would a customer pay €15 per device-month? Only customer interviews can answer this (next step 1 in the pitch).

### Resolved
- U12 concept and σ target: decided (load-cell weigh frame, σ 1.5 %).
- Combined-load tickets: re-split by device weight for cost allocation between sites; don't drop them.
- C08 sketch: the built app follows it.
- C05 rule: in the app, because proposals always need a human.
