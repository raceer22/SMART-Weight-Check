# Europress reviews of 30 Oct and 4 Nov 2026 and what changed in v1.0.0 / v1.0.1

Europress Group Oy (Tommi Häkkinen) reviewed the v1.0.0rc1 data pack against the eight points of the approval
guide and returned "data-aineiston kommentit" on 30 Oct 2026. Every point was **approved with changes**; no
change was to be prioritised over another, all had to be implemented before publication. This document lists
every request, what was done and how it is verified. Numbers refer to the competition pack of v1.0.0.

## Point 1: Europress data, products or specifications must not be inferable

| # | Request | Implemented | Verified by |
|---|---|---|---|
| 1.1 | Equipment classes → **COMBI** (compactor and container joined, emptied as one unit) and **DUO** (stationary compactor, container detached and emptied); update validator, data dictionary, assumptions; drop "generic classes only" | `equipment_class ∈ {COMBI, DUO}` (v1.0.1 competition: 216 COMBI, 231 DUO public devices; see the 4 Nov review below). Biowaste only COMBI, mixed plastic only DUO. Text now: Europress machine-type categories, no model-specific data | validator `MAT:equipment_compatible`; test `test_equipment_classes_are_europress_machine_types` |
| 1.2 | Collection policy mostly ON_CALL, small FIXED share; check that unnecessary lifts (S01) still occur | Mix ON_CALL 78 % / FIXED 12 % / HYBRID 10 % (competition: 78.7 / 11.9 / 9.4 %). Two realistic on-call mechanisms added: precautionary customer orders before weekends and holidays (S39, published only as CUSTOMER_REQUEST) and fill sensors that read falsely high for 1–4 days (S40, the mass reveals it). Unnecessary lifts: **2,922** labelled (1,982 schedule-driven, 507 precautionary, 433 false-high fill), vs 3,465 in rc1 | validator `DEV:on_call_majority`; tests `test_collection_policy_is_mostly_on_call`, `test_unnecessary_lifts_still_exist_on_on_call_devices` |
| 1.3 | Roles: transport, treatment and material prices are agreed between customer and operator; Europress is not a party and does not know the prices; contract and invoice data are customer-provided or estimates; Europress's goal is transparency and weight-based value-added services | Role table in `ECONOMIC_MODEL.md`, `README.md → Prices and roles`, schema descriptions of contracts, contract_versions, invoices | test `test_role_notes_on_contracts_and_invoices` |
| 1.4 | Only cardboard and plastics earn a credit; other streams are chargeable; paper becomes chargeable | `material_classes.credit_eligible` (+ `customer_economics`), paper has a processing fee of 20–45 €/t and no index; the paper index was removed; no MATERIAL_CREDIT line on any chargeable stream. The synthetic index is kept (decided in point 4) | validator `MAT:credit_only_cardboard_plastics`, `MAT:no_credit_on_chargeable`; test `test_only_cardboard_and_plastics_earn_credits` |
| 1.5 | Europress has no technology to determine quality before the facility; the operator determines quality | Stated in `assumptions.yaml`, `quality_grade_rules` and `quality_assessments` descriptions, `ASSUMPTIONS_AND_LIMITATIONS.md §A` (the data already had this structure) | documentation |
| 1.6 | Facilities: mark as operator data or remove from public data | `reference/facilities` removed from the public packages (now `private_evaluation/truth/facilities`); the facility id remains only on weighbridge tickets the operator chooses to share | test `test_facilities_are_not_public` |
| 1.7 | Weighing accuracy: at most ~100 kg error on a 3 t cardboard load (±3.3 %) in normal state, ~95 % of readings; faults may exceed it; state that it is not a Europress specification | Normal state: reading noise max(15 kg, 1.4 %) plus installation calibration (gain sd 0.4 %, offset sd 6 kg) ≈ 1.5 % total. Measured on the test dataset: ≥ 94 % of normal-state readings above 1 t within 3.33 %. Drift, calibration errors and fault states still exceed it. "Not a specification of any Europress weighing solution" in assumptions, sensor registry and data dictionary | test `test_weighing_accuracy_target_in_normal_state` |
| — | Accepted as is: fill-estimate accuracy (~±4 pp) and fault rate (~1.2 fault visits per device per year); customers, sites, calendars, installations, material classes, operators, regions; no product names or model numbers | unchanged | — |

## Point 2: SMART is described correctly and the challenge does not duplicate it

| # | Request | Implemented |
|---|---|---|
| 2.1 | Replace "Relation to SMART" with Europress's text; change the challenge question; neutral tone towards operators | `README.md` uses Europress's text verbatim and the new challenge question (point 7) |
| 2.2 | New task or Task B extension: operator performance scorecard (punctuality, missed visits, billing accuracy, weighbridge data sharing, weight differences) | **Task B2**: truth per operator × region × month (`labels_dev/operator_scorecard`, test rows in `benchmark/task_b2_scorecard_rows`), 9 metrics, scorer `--task B2`, baseline B5. Operators now also differ in punctuality and missed visits (`on_time_factor`, `missed_factor`) |
| 2.3 | Task C actions affecting the operator relationship: DISPUTE_INVOICE, REQUEST_WEIGHBRIDGE_DATA, TENDER_OR_SWITCH_OPERATOR, RENEGOTIATE_CONTRACT; fill thresholds and schedules stay as context | **Task C2**: 437 contract cases with the four actions, published valuation rules (`assumptions.yaml → operator_actions`, `ECONOMIC_MODEL.md §7`), scorer `--task C2` (regret of the chosen action set), baseline B6. Task C is kept and labelled as context |
| 2.4 | Business models with Europress in the middle of the value chain: transport procured for the customer, tonne-based full service, operator tendering as a service, materials marketplace; all hypotheses | `commercial_assumptions.yaml → future_models`, `business_case.py` levers `operator_tendering`, future models `transport_procurement`, `tonne_based_full_service`, `materials_marketplace`; `BENCHMARK.md → Task D` |
| 2.5 | Remove the service name "Premium SMART 'Material Value' service" | Removed everywhere; text speaks of a new service or business model | test `test_removed_service_name_and_wording` |
| 2.6 | ECONOMIC_MODEL §2: hypothetical scenario where the device weight is a billing or verification basis | `ECONOMIC_MODEL.md §2b` (verification basis and billing basis variants) |
| 2.7 | SMART description status → "Europress-confirmed" | `ASSUMPTIONS_AND_LIMITATIONS.md §A` |
| — | Kept as is: SMART feature description, `examples/recommendation_api_mock.py` | unchanged |

## Point 3: weighing feasibility is not claimed

| # | Request | Implemented |
|---|---|---|
| 3.1 | State that the dataset depicts a future scenario in which most devices have integrated weighing (competition: 404 of 447, 90 %); install dates do not imply past deployment | Europress's sentence in `ASSUMPTIONS_AND_LIMITATIONS.md §A`, the `devices` and `sensor_registry` table descriptions and every package's `README_FIRST.txt` |
| — | Kept: "affordable" (Europress's own requirement), the README caution, README_FIRST wording, INTEGRATED_SIMULATED flags | unchanged |

## Point 4: prices and tariffs are clearly hypothetical

Standard sentence added: *"Europress is currently not a party to waste transport or treatment. Tariffs,
processing fees and material credits are agreed between the customer and the waste operator. All prices in
this dataset are hypothetical."*

| # | Where | Implemented |
|---|---|---|
| 4.1 | README.md | section "Prices and roles" |
| 4.2 | ECONOMIC_MODEL.md | opening disclaimer + role table |
| 4.3 | configs/assumptions.yaml | header comment and contracts comment |
| 4.4 | contracts.note | "HYPOTHETICAL illustrative customer–operator tariff. Europress is not a party. Not an actual operator contract." |
| 4.5 | invoices, invoice_lines | new `synthetic` column on both; `invoices.record_note` = "SYNTHETIC invoice from a fictional waste operator to a fictional customer; not a real invoice" |
| 4.6 | DATA_DICTIONARY (contracts, contract_versions, invoices, invoice_lines, price_index_monthly, facilities) | table descriptions say who agrees and who shares the data |
| 4.7 | BENCHMARK.md tasks A, B, D | sentence in each task description |
| 4.8 | new business models | labelled future hypotheses that differ from today |
| — | Kept: tariff levels and ranges, synthetic index (no public market quotes), simulated price events, pricing models | unchanged |

## Point 5: commercial hypotheses

| # | Request | Implemented |
|---|---|---|
| 5.1–5.3 | Replace service prices (15/29/49 €/device/month, 120 €/site/month, 20 % savings share), costs (400 € + 60 €, 4 €/device/month, 25 €/customer/month), adoption (5/15/30 %) and the "value ≥ 3 × fee" condition with neutral parameters | `configs/commercial_assumptions.yaml` is a parameter template with no values. A separate `business_case_example_params.yaml` is labelled "CALCULATION EXAMPLE — not a price estimate" and uses different round numbers |
| 5.4 | business_case.py becomes a calculator with team parameters; Task D says pricing and adoption are part of the task | `business_case.py --params`; it refuses to run without the team's parameters; `BENCHMARK.md → Task D` and rubric row "Pricing and adoption reasoning" |
| 5.5 | Business-case result reports not shared with participants | Removed from all participant material; organiser copy only |
| 5.6 | New value levers: operator performance monitoring, operator tendering, Europress as transport procurer | levers `operator_performance`, `operator_tendering`; future model `transport_procurement` |
| 5.7 | Update LUE_ENSIN (question 3) and the approval guide | The approval guide is replaced by this review record. LUE_ENSIN (the Finnish cover note of the rc1 review pack) is replaced by the Finnish response sent to Europress with v1.0.0: prices are not shown, they are parameters |
| — | Value realisation shares | also turned into neutral parameters, for consistency |

## Point 6: operators presented neutrally

No new requests. Kept: fictional names, descriptive discrepancy names, no "fraud", real regions with the
current split, "overcharge" terms, quality differences between operators. Added for the scorecard and C2: the
rubric row "Neutral tone towards operators" and the reminder that part of every difference has causes other
than the operator.

## Point 7: challenge wording matches the brief

| # | Request | Implemented |
|---|---|---|
| 7.1 | README challenge text replaced | Europress's text verbatim |
| 7.2 | Same question and focus in LUE_ENSIN, approval guide, QUICKSTART, BENCHMARK | README, QUICKSTART, BENCHMARK, START_HERE and the Finnish response; the rc1 LUE_ENSIN and approval guide are retired |
| 7.3 | Check whether a challenge description has already been published and align it | **Since AI action** (event page and Field Guide), outside this package |
| 7.4 | Brief and challenge text must not conflict | README section "How this dataset supports the two-part challenge brief": part 1 *Get the weight*, part 2 *Create value from the weight*; new `examples/weighing_accuracy_value.py` for part 1 |
| — | Kept: challenge name "SMART Material Value Engine", event details, principles | unchanged |

## Point 8: private material stays private

| # | Request | Implemented |
|---|---|---|
| 8.1 | Remove absolute generation paths from `dataset_manifest.json` | all manifest paths relative; test `test_manifests_contain_no_absolute_paths`; packaging scans every text file for absolute paths |
| 8.2 | Decide whether baseline results on the secret test period are shown | **Not shown.** Public `BENCHMARK.md` shows validation (and C2 dev) results only; test results are in the organiser package |
| 8.3 | Distribution of the private package | Only Since AI organisers hold it. Automatic scores, where used, are computed by Since AI; the Europress judge evaluates submissions in the Since AI app |
| Observation | The private evaluation data could be regenerated from the public package (public generator, deterministic, public seed 20261023) | **Confirmed and fixed.** Official packages now use organiser-held 62-bit seeds; the public manifest shows `UNDISCLOSED`, a SHA-256 commitment and a configuration hash without the seed. Packaging fails if a secret seed appears in any public file | test `test_undisclosed_seed_blocks_regeneration`; packaging check |

## Also changed

* Task B2/C2 dev labels are cut so that they never contain test-period information (`BENCHMARK.md → Splits`).
* `START_HERE.md/.html`: plain-language overview and glossary for participants of every background.
* Version 1.0.0; dataset status "reviewed by Europress (30 Oct 2026), all requested changes implemented".

## Second review, 4 Nov 2026 (v1.0.1)

Europress reviewed v1.0.0 on 4 Nov 2026: "mostly all ok"; approval once the following are changed.

| # | Request | Implemented | Verified by |
|---|---|---|---|
| R2.1 | Container size limits: COMBI at most 22 m³, DUO at most 30 m³ (31 COMBI units had 24 or 30 m³: competition 26, hold-out 4, quickstart 1). Fix the generator, add a blocking validator check for both limits, confirm that `equipment_class` is only a label, update class counts | `assumptions.yaml → equipment_max_volume_m3`; the generator labels any unit above 22 m³ as DUO without a random draw. **Confirmed:** `equipment_class` is a label only (used nowhere in the simulation), so regenerating with the same organiser seeds changed exactly these devices' class and nothing else: in the public packs only `reference/devices` (and `csv/devices.csv`), `README_FIRST.txt` (status line) and the scenario catalog text (R2.4) differ from v1.0.0. Competition: 216 COMBI / 231 DUO public (was 242 / 205), hold-out 22 / 31; largest COMBI container 20 m³, largest DUO 30 m³ | validator `MAT:equipment_volume_limit` (blocking); test `test_equipment_classes_are_europress_machine_types` |
| R2.2 | Europress's goal in README → Prices and roles | "Europress's goal is to bring transparency to the waste value chain and to develop value-added services based on weight data." (also in the event-page challenge text) | test `test_neutral_wording_and_review_additions` |
| R2.3 | Links at the end of README → Relation to SMART | "More about Europress and SMART: europressgroup.com and epsmart.fi." | same test |
| R2.4 | S40 (fill sensor reads 88–97 % for 1–4 days) is outside the accepted ±4 pp accuracy: keep it, but state that it is synthetic | `ASSUMPTIONS_AND_LIMITATIONS.md §B.8` and the S40 scenario-catalog entry: "Scenario S40 and its frequency are synthetic assumptions and do not describe the performance of the SMART fill measurement." | same test |
| R2.5 | `invoice_lines` description: customer-provided, Europress not a party | done (also `contract_versions`, `price_index_monthly`) | `test_role_notes_on_contracts_and_invoices` |
| R2.6 | Replace "inflated tonnage" with neutral wording (START_HERE, BENCHMARK, B5, B6) | "a tonnage that differs from the weighbridge record" everywhere | same test as R2.2 |
| R2.7 | Remove the remnant "Premium-service prices" (`scripts/handover_report.py`) | removed | same test as R2.2 |

Version 1.0.1; dataset status "reviewed by Europress (30 Oct and 4 Nov 2026), all requested changes implemented".

