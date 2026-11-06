# Data dictionary

Generated from `src/europress_data/schema.py` (the single source of truth; the validator fails if a published column is missing here).
Types: `str`, `int16/32/64`, `float32/64`, `bool`, `date` (local date), `ts` (timestamp, ms, UTC). Money columns `*_eur` are exact to the cent; `*_cents` are integers.

## Public package

### `reference/customers`

Fictional customer organisations (no real companies).

Primary key: `customer_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `customer_id` | str |  | no | Customer organisation id ORG-nnnn. |  |
| `customer_name` | str |  | no | Generated fictional name. |  |
| `primary_sector` | str |  | no | Main sector of the organisation. | grocery_retail, nonfood_retail, shopping_center, logistics_warehouse, manufacturing, hospitality_hotel, food_processing, office_services |
| `n_sites` | int64 | count | no | Number of sites of this customer in this package. |  |
| `synthetic` | bool |  | no | Always true: the record is invented. |  |

### `reference/sites`

Customer sites/facilities. Municipality is real geography; everything else is invented.

Primary key: `site_id` · Foreign keys: `customer_id` → `reference/customers.customer_id`, `region_code` → `reference/regions.region_code`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `site_id` | str |  | no | Site id SITE-nnnnn. |  |
| `customer_id` | str |  | no | Owning customer. |  |
| `site_name` | str |  | no | Generated label (municipality + ordinal). |  |
| `sector` | str |  | no | Site sector (drives generation rhythm and material mix). |  |
| `region_code` | str |  | no | Region code (FI-xx). |  |
| `municipality` | str |  | no | Municipality name. |  |
| `billable_round_trip_km` | int64 | km | no | Round-trip distance used by contracts for transport charges. |  |
| `outdoor_material_staging` | bool |  | no | Material is staged outdoors before compaction (rain adds water mass). |  |
| `opening_days_mon_sun` | str |  | no | 7-char mask Mon..Sun, 1 = normally open. |  |
| `opening_hours_local` | str | local time | no | Normal opening hours HH-HH (local). |  |
| `timezone` | str |  | no | IANA timezone of local times. |  |
| `synthetic` | bool |  | no | Always true: the record is invented. |  |

### `reference/site_calendar`

Daily operating calendar per site (holidays, summer shutdowns, planned closures).

Primary key: `site_id, date` · Foreign keys: `site_id` → `reference/sites.site_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `site_id` | str |  | no | Site. |  |
| `date` | date | local date | no | Local calendar date. |  |
| `is_open` | bool |  | no | Site operates (generates material) on this date. |  |
| `open_hour_local` | float64 | hour | yes | Opening hour; NULL when closed. |  |
| `close_hour_local` | float64 | hour | yes | Closing hour (exclusive); NULL when closed. |  |
| `closure_reason` | str |  | yes | Why closed. | WEEKLY_CLOSED, PUBLIC_HOLIDAY, SUMMER_SHUTDOWN, PLANNED_CLOSURE |
| `public_holiday_name` | str |  | yes | Finnish public holiday name, if any. |  |

### `reference/devices`

Fictional compactors. equipment_class uses Europress machine-type categories (COMBI, DUO); no model names, model numbers or model-specific technical data. The dataset depicts a future scenario in which most devices have integrated weighing; sensor install dates are synthetic and do not imply that weighing has been deployed in the past.

Primary key: `device_id` · Foreign keys: `site_id` → `reference/sites.site_id`, `customer_id` → `reference/customers.customer_id`, `contract_id` → `reference/contracts.contract_id`, `operator_id` → `reference/operators.operator_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `device_id` | str |  | no | Device id CMP-nnnnn. |  |
| `site_id` | str |  | no | Installed site. |  |
| `customer_id` | str |  | no | Customer. |  |
| `equipment_class` | str |  | no | Europress machine-type category. COMBI = compactor and container permanently joined, emptied as one unit; DUO = stationary compactor, the detachable container is emptied. No model-specific data. | COMBI, DUO |
| `container_volume_m3` | float64 | m3 | no | Physical container volume. |  |
| `material_stream` | str |  | no | Material stream handled. | cardboard, paper, plastic_film, mixed_plastic, mixed_waste, biowaste |
| `commissioned_on` | date |  | no | Commissioning date. |  |
| `lifecycle_status` | str |  | no | Status at extraction. | ACTIVE, DECOMMISSIONED |
| `active_from` | date |  | yes | First active date within the data window (NULL = before window). |  |
| `active_to` | date |  | yes | Last active date if decommissioned in window. |  |
| `weight_measurement` | str |  | no | Assumed integrated weight measurement availability (future scenario, simulated; not evidence that weighing exists today). | INTEGRATED_SIMULATED, NONE |
| `fill_measurement` | str |  | no | Fill-level estimate source (simulated). |  |
| `collection_policy` | str |  | no | Current collection policy. | FIXED_SCHEDULE, ON_CALL, HYBRID |
| `fixed_schedule_per_week` | float64 | lifts/week | yes | Booked lifts per week (fixed/hybrid). |  |
| `fixed_schedule_weekdays` | str |  | yes | Comma list of weekdays 0=Mon (fixed/hybrid). |  |
| `on_call_threshold_pct` | float64 | % | yes | Fill threshold that triggers an order (on-call). |  |
| `hybrid_skip_below_pct` | float64 | % | yes | Hybrid: booked lift is skipped if fill is below this ~26 h before. |  |
| `operator_id` | str |  | no | Hauler serving this device. |  |
| `synthetic` | bool |  | no | Always true: the record is invented. |  |
| `contract_id` | str |  | no | Contract covering this stream. |  |
| `has_weight_measurement` | bool |  | no | Convenience flag: weight_measurement != NONE. |  |

### `reference/device_installations`

Installation history (one installation per device in v1).

Primary key: `installation_id` · Foreign keys: `device_id` → `reference/devices.device_id`, `site_id` → `reference/sites.site_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `installation_id` | str |  | no | Installation id. |  |
| `device_id` | str |  | no | Device. |  |
| `site_id` | str |  | no | Site. |  |
| `installed_on` | date |  | no | Installation date. |  |
| `removed_on` | date |  | yes | Removal date if removed within the window. |  |

### `reference/sensor_registry`

Simulated integrated weight sensors (future scenario). A replacement creates a new sensor id. Install dates are synthetic and do not imply that weighing has been deployed in the past. Nominal noise is a challenge simulation target (about 100 kg on a 3 t load), not a specification of any Europress weighing solution.

Primary key: `sensor_id` · Foreign keys: `device_id` → `reference/devices.device_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `sensor_id` | str |  | no | Sensor id WS-nnnnn-k. |  |
| `device_id` | str |  | no | Device. |  |
| `sensor_type` | str |  | no | Generic, simulated. |  |
| `nominal_sigma_kg` | int64 | kg | no | Nominal absolute 1-sigma noise. |  |
| `nominal_sigma_rel` | float64 | fraction | no | Nominal relative 1-sigma noise. |  |
| `installed_at` | ts | UTC | no | Installation time. |  |
| `removed_at` | ts | UTC | yes | Removal (replacement) time. |  |

### `reference/contracts`

HYPOTHETICAL service contracts between a customer site and a waste operator (one per device stream). Europress is currently not a party to waste transport or treatment: tariffs, processing fees and material credits are agreed between the customer and the waste operator. In a real service this is data the customer hands over to the service, or an estimate. All prices are hypothetical.

Primary key: `contract_id` · Foreign keys: `device_id` → `reference/devices.device_id`, `operator_id` → `reference/operators.operator_id`, `site_id` → `reference/sites.site_id`, `customer_id` → `reference/customers.customer_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `contract_id` | str |  | no | Contract id. |  |
| `customer_id` | str |  | no | Customer. |  |
| `site_id` | str |  | no | Site. |  |
| `device_id` | str |  | no | Device/stream covered. |  |
| `material_stream` | str |  | no | Material. |  |
| `operator_id` | str |  | no | Hauler. |  |
| `pricing_model_initial` | str |  | no | Pricing model of version 1. | FIXED_PER_LIFT, PER_TONNE, HYBRID, HYBRID_MIN |
| `contract_start` | date |  | no | Start date (before the data window). |  |
| `notice_period_days` | int64 | days | no | Notice period. |  |
| `price_index_id` | str |  | yes | Material index used for credits (credit-eligible streams only: cardboard and plastics). |  |
| `synthetic` | bool |  | no | Always true: the record is invented. |  |
| `note` | str |  | no | Status note: HYPOTHETICAL customer-operator tariff; Europress is not a party; not an actual operator contract. |  |

### `reference/contract_versions`

Customer-operator tariff versions (HYPOTHETICAL; agreed between customer and operator, Europress is not a party). In a real service this is data the customer hands over to the service or the operator shares, or an estimate. Validity [effective_from, effective_to). Integer cents / basis points for exact arithmetic. See docs/ECONOMIC_MODEL.md.

Primary key: `contract_version_id` · Foreign keys: `contract_id` → `reference/contracts.contract_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `contract_version_id` | str |  | no | Version id <contract>-Vn. |  |
| `contract_id` | str |  | no | Contract. |  |
| `version_no` | int64 |  | no | 1..n. |  |
| `effective_from` | date | local date | no | First valid local date (inclusive). |  |
| `effective_to` | date | local date | yes | End (exclusive); NULL = open. |  |
| `change_reason` | str |  | no | Why this version exists. | INITIAL, ANNUAL_INDEXATION, AMENDMENT_LIFT_FEE, AMENDMENT_FUEL, AMENDMENT_CREDIT_SHARE, AMENDMENT_PROCESSING, AMENDMENT_MIN_CHARGE |
| `pricing_model` | str |  | no | Pricing model. | FIXED_PER_LIFT, PER_TONNE, HYBRID, HYBRID_MIN |
| `lift_fee_cents` | int64 | EUR cents/lift | no | Fixed fee per completed lift. |  |
| `per_km_cents` | int64 | EUR cents/km | no | Transport rate per billable km. |  |
| `free_km` | int64 | km | no | Km included before transport is charged. |  |
| `contract_km` | int64 | km | no | Contracted billable round-trip km. |  |
| `remote_surcharge_cents` | int64 | EUR cents/lift | no | Regional remote surcharge per lift. |  |
| `fuel_surcharge_bp` | int64 | basis points | no | Fuel surcharge on (lift + transport + remote). |  |
| `haul_fee_cents_per_t` | int64 | EUR cents/t | no | Per-tonne haulage fee (PER_TONNE model). |  |
| `processing_fee_cents_per_t` | int64 | EUR cents/t | no | Treatment / gate fee per tonne. |  |
| `min_charge_cents` | int64 | EUR cents/lift | no | Minimum charge per lift (0 = none). |  |
| `credit_share_bp` | int64 | basis points | no | Share of index price credited to the customer for credit-eligible streams (0 = operator keeps the value). |  |
| `credit_floor_cents_per_t` | int64 | EUR cents/t | no | Floor of the credit price before quality factor. |  |
| `contamination_penalty_cents` | int64 | EUR cents/lift | no | Penalty for grade C loads. |  |
| `rejection_fee_cents_per_t` | int64 | EUR cents/t | no | Reprocessing fee for rejected (grade R) credit-eligible loads. |  |
| `cancellation_fee_cents` | int64 | EUR cents | no | Fee for customer cancellation with < 24 h notice. |  |
| `wasted_trip_fee_cents` | int64 | EUR cents | no | Fee when the operator arrives but cannot lift. |  |
| `side_waste_fee_cents` | int64 | EUR cents/lift | no | Fee when loose side waste is loaded at a lift. |  |
| `emergency_surcharge_cents` | int64 | EUR cents/lift | no | Surcharge for ad-hoc emergency lifts. |  |
| `rental_cents_per_month` | int64 | EUR cents/month | no | Monthly equipment rental billed by the operator. |  |
| `default_weight_kg` | int64 | kg | no | Contractual default billing weight when no weighbridge ticket exists. |  |
| `target_collection_cost_cents_per_t` | int64 | EUR cents/t | no | Site/contract benchmark for collection cost per tonne (KPI, not a price). |  |

### `reference/operators`

Fictional haulers/treatment operators.

Primary key: `operator_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `operator_id` | str |  | no | Operator id. |  |
| `operator_name` | str |  | no | Fictional name. |  |
| `regions_served` | str |  | no | Comma list of region codes. |  |
| `weighbridge_data_shared` | bool |  | no | Operator shares weighbridge tickets with customers at all. |  |
| `api_feed` | bool |  | no | Shares via near-real-time feed. |  |
| `synthetic` | bool |  | no | Always true: the record is invented. |  |

### `reference/regions`

Regions with illustrative distance and surcharge assumptions.

Primary key: `region_code`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `region_code` | str |  | no | Code. |  |
| `region_name` | str |  | no | Name. |  |
| `median_billable_km` | int64 | km | no | Median billable km assumption. |  |
| `remote_surcharge_eur` | int64 | EUR | no | Remote surcharge assumption per lift. |  |

### `reference/price_index_monthly`

SYNTHETIC monthly reference prices for credit-eligible streams (cardboard, plastic film, mixed plastic); not market data. Includes a cardboard value collapse and a film price spike. Material credits are agreed between customer and operator; Europress is not a party. In a real service, credit prices come from the customer's operator contract (customer-provided or operator-shared) or are an estimate.

Primary key: `index_id, month`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `index_id` | str |  | no | Index id. |  |
| `material` | str |  | no | Material. |  |
| `month` | str | YYYY-MM | no | Month the price applies to (collection month). |  |
| `price_eur_per_t` | float64 | EUR/t | no | Reference price (can be negative for mixed plastics). |  |
| `published_on` | date |  | no | Date the price becomes known (3rd of next month). |  |
| `source` | str |  | no | Always 'SYNTHETIC illustrative index'. |  |

### `reference/material_classes`

Illustrative material assumptions. Only cardboard and plastics can earn a material credit; all other streams, including paper, are chargeable to the customer.

Primary key: `material_stream`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `material_stream` | str |  | no | Material. |  |
| `credit_eligible` | bool |  | no | TRUE only for cardboard and plastics: the operator may credit the customer for material value (if the contract has a credit share). FALSE = chargeable stream: the customer pays a treatment fee. |  |
| `typical_compacted_density_kg_m3` | int64 | kg/m3 | no | Typical compacted density assumption (devices vary). |  |
| `max_days_between_collections` | int64 | days | no | Hygiene/fire-safety/contract maximum interval. |  |
| `customer_economics` | str |  | no | CREDIT_ELIGIBLE (credit possible) or CHARGEABLE (customer pays treatment). | CREDIT_ELIGIBLE, CHARGEABLE |
| `price_index_id` | str |  | yes | Index for credits. |  |
| `assumption_note` | str |  | no | Status note. |  |

### `reference/quality_grade_rules`

Operator quality grading rules for credit-eligible loads. Quality is determined only by the waste operator at its facility, using its own assessment; Europress has no technology to determine material quality before the facility.

Primary key: `grade`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `grade` | str |  | no | Grade. | A, B, C, R |
| `max_contamination_pct` | float64 | % | no | Upper contamination bound. |  |
| `credit_quality_factor` | float64 | fraction | no | Multiplier on the credit price. |  |
| `consequence` | str |  | no | Economic consequence. |  |

### `telemetry/telemetry_hourly`

Hourly device messages AS DELIVERED (ingest log): includes duplicates (same message_id), out-of-order and buffered delivery, gaps. Partitioned by local month of measured_at (hive key 'month').

Primary key: `delivery_id` · Foreign keys: `device_id` → `reference/devices.device_id`, `sensor_id` → `reference/sensor_registry.sensor_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `message_id` | int64 |  | no | Measurement id (device-hour). NOT unique: re-sent duplicates share it. |  |
| `device_id` | str |  | no | Device. |  |
| `sensor_id` | str |  | yes | Weight sensor id; NULL if no weight sensor. |  |
| `measured_at` | ts | UTC | no | Measurement time (end of the hour). |  |
| `received_at` | ts | UTC | no | Ingest time. received_at >= measured_at. |  |
| `fill_pct` | float32 | % | no | Assumed fill-level estimate (noisy, 0-100). |  |
| `mass_kg` | float32 | kg | yes | Assumed measured container mass. NULL if sensor fault or no sensor. May be negative near empty, may be drifted/biased. |  |
| `mass_uncertainty_kg` | float32 | kg | yes | Device-reported 1-sigma uncertainty (does not know about drift). |  |
| `compaction_cycles` | int16 | count | no | Compaction cycles in the hour. |  |
| `press_load_index` | float32 | 0-100 | yes | Generic normalised peak press load (NULL if no cycle). |  |
| `operational_state` | str |  | no | Device state. | IDLE, ACTIVE, FULL, DOWN |
| `sensor_status` | str |  | no | Weight sensor self-diagnosis. | OK, DEGRADED, FAULT, NOT_INSTALLED |
| `quality_flag` | str |  | no | Quality flag of mass_kg. | VALID, LOW_CONFIDENCE, NEGATIVE_READING, SUSPECT_SPIKE, SENSOR_FAULT, NO_WEIGHT_SENSOR |
| `delivery_mode` | str |  | no | LIVE or BUFFERED (sent after a connectivity outage). | LIVE, BUFFERED |
| `ingest_seq` | int64 |  | no | Per-device ingest order (by received_at). |  |
| `delivery_id` | int64 |  | no | Unique delivery id (primary key). |  |

### `telemetry/telemetry_daily_summary`

Per device and local date, derived ONLY from published telemetry (deduplicated by message_id).

Primary key: `device_id, date` · Foreign keys: `device_id` → `reference/devices.device_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `device_id` | str |  | no | Device. |  |
| `date` | date | local date | no | Local date of measured_at. |  |
| `n_messages` | int64 | count | no | Unique messages. |  |
| `fill_pct_first` | float32 | % | yes | First fill of the day. |  |
| `fill_pct_last` | float32 | % | yes | Last fill of the day. |  |
| `fill_pct_max` | float32 | % | yes | Max fill. |  |
| `fill_pct_min` | float32 | % | yes | Min fill. |  |
| `mass_kg_last_valid` | float32 | kg | yes | Last VALID/LOW_CONFIDENCE mass. |  |
| `mass_kg_max_valid` | float32 | kg | yes | Max valid mass. |  |
| `n_valid_mass` | int64 | count | no | Messages with valid mass. |  |
| `compaction_cycles` | int64 | count | no | Sum of cycles. |  |
| `hours_down` | int64 | h | no | Messages in DOWN state. |  |
| `hours_full` | int64 | h | no | Messages in FULL state. |  |
| `n_buffered` | int64 | count | no | Buffered messages. |  |
| `data_completeness_pct` | float64 | % | no | n_messages / 24 (capped at 100). |  |

### `operations/collection_events`

Every scheduled/ordered collection event and its outcome, with device-side before/after observations.

Primary key: `collection_id` · Foreign keys: `device_id` → `reference/devices.device_id`, `contract_id` → `reference/contracts.contract_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `collection_id` | str |  | no | Event id COL-nnnnn-ssss. |  |
| `device_id` | str |  | no | Device. |  |
| `site_id` | str |  | no | Site. |  |
| `customer_id` | str |  | no | Customer. |  |
| `contract_id` | str |  | no | Contract. |  |
| `operator_id` | str |  | no | Hauler. |  |
| `operator_job_ref` | str |  | no | Hauler's job reference; the join key to weighbridge tickets and invoice lines. |  |
| `trigger_type` | str |  | no | Why the event exists. | SCHEDULED, ON_CALL_ORDER, MAX_INTERVAL_RULE, AD_HOC_CUSTOMER, CUSTOMER_REQUEST, CUSTOMER_REQUEST_PRE_CLOSURE, DECOMMISSION, RESCHEDULED |
| `original_trigger_type` | str |  | no | For RESCHEDULED events: the trigger of the event that was rescheduled; otherwise = trigger_type. | SCHEDULED, ON_CALL_ORDER, MAX_INTERVAL_RULE, AD_HOC_CUSTOMER, CUSTOMER_REQUEST, CUSTOMER_REQUEST_PRE_CLOSURE, DECOMMISSION |
| `status` | str |  | no | Outcome. | COMPLETED, PARTIAL, SKIPPED_LOW_FILL, CANCELLED_BY_CUSTOMER, MISSED_BY_OPERATOR, WASTED_TRIP |
| `cancellation_notice_hours` | float64 | h | yes | Notice given for cancellations/skips. |  |
| `wasted_trip_reason` | str |  | yes | Reason for wasted trip. | ACCESS_BLOCKED, NOTHING_TO_COLLECT |
| `vehicle_id` | str |  | yes | Vehicle (from the operator ticket, if any). |  |
| `driver_reported_side_waste` | bool |  | yes | Driver loaded loose side waste (overflow) at this lift. |  |
| `driver_reported_partial` | bool |  | no | Container could not be fully emptied. |  |
| `device_fill_pct_before` | float64 | % | yes | Device fill reading for the hour before the lift (NULL if not delivered). |  |
| `device_fill_pct_after` | float64 | % | yes | Device fill reading for the hour of the lift. |  |
| `device_mass_kg_before` | float64 | kg | yes | Valid device mass before the lift. |  |
| `device_mass_kg_after` | float64 | kg | yes | Valid device mass after the lift. |  |
| `device_estimated_collected_kg` | float64 | kg | yes | before - after; NULL if either is missing. A device-side estimate, not a weighbridge value. |  |
| `weight_reconciliation_status` | str |  | no | Naive pipeline status (device vs published weighbridge) computed AT EXTRACTION TIME — recompute as-of for decision features. | WITHIN_10PCT, DIFFERENCE_GT_10PCT, WEIGHBRIDGE_NOT_AVAILABLE, DEVICE_ESTIMATE_MISSING, NOT_APPLICABLE, UNKNOWN_AS_OF |
| `invoice_match_status` | str |  | no | Naive exact job-ref match against invoice lines, computed AT EXTRACTION TIME. | MATCHED_BY_JOB_REF, NOT_FOUND_ON_INVOICES, NO_CHARGE_EXPECTED, UNKNOWN_AS_OF |
| `order_placed_at` | ts | UTC | yes | Order time (on-call / ad-hoc / requests). |  |
| `scheduled_at` | ts | UTC | no | Planned service time. |  |
| `actual_at` | ts | UTC | yes | Actual service time (completed, partial, wasted trip). |  |

### `operations/weighbridge_tickets`

Operator weighbridge tickets SHARED with the customer and published before extraction (operator data, visible only when the operator shares it). Some operators never share; others share late.

Primary key: `ticket_id` · Foreign keys: `operator_id` → `reference/operators.operator_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `ticket_id` | str |  | no | Ticket (one per job; combined loads get -1/-2). |  |
| `weighing_event_id` | str |  | no | Physical weighing event (shared by combined loads). |  |
| `operator_id` | str |  | no | Operator. |  |
| `operator_job_ref` | str |  | no | Job reference. |  |
| `vehicle_id` | str |  | no | Vehicle. |  |
| `facility_id` | str |  | no | Receiving facility. |  |
| `arrival_at` | ts | UTC | no | Weighing time. |  |
| `gross_kg` | int64 | kg | no | Gross weight (20 kg resolution). |  |
| `tare_kg` | int64 | kg | no | Tare used. |  |
| `tare_method` | str |  | no | WEIGHED or STORED tare. | WEIGHED, STORED |
| `net_kg` | int64 | kg | no | gross - tare of the weighing event (all loads on the vehicle). |  |
| `allocated_net_kg` | int64 | kg | no | Net allocated to this job (billing basis). |  |
| `allocation_method` | str |  | no | Allocation. | SINGLE_LOAD, EQUAL_SPLIT_COMBINED_LOAD |
| `loads_on_vehicle` | int64 | count | no | Jobs weighed together. |  |
| `material_declared` | str |  | no | Declared material. |  |
| `published_at` | ts | UTC | no | When the ticket became available to the customer. |  |

### `operations/quality_assessments`

Operator quality grading of credit-eligible loads (published subset). The operator's own assessment at its facility; not measured by the device.

Primary key: `quality_assessment_id` · Foreign keys: `ticket_id` → `operations/weighbridge_tickets.ticket_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `quality_assessment_id` | str |  | no | Assessment id. |  |
| `ticket_id` | str |  | no | Ticket. |  |
| `operator_id` | str |  | no | Operator. |  |
| `assessed_at` | ts | UTC | no | Assessment time. |  |
| `published_at` | ts | UTC | no | Publication time. |  |
| `material_declared` | str |  | no | Material. |  |
| `contamination_pct_est` | float64 | % | no | Operator's visual contamination estimate (whole %). |  |
| `grade` | str |  | no | Grade. | A, B, C, R |
| `rejected` | bool |  | no | Grade R. |  |
| `remark_code` | str |  | yes | Remark. | WET_MATERIAL, REJECTED_CONTAMINATION |

### `operations/maintenance_work_orders`

Maintenance and configuration work orders (context for interpreting anomalies; not a PdM task).

Primary key: `work_order_id` · Foreign keys: `device_id` → `reference/devices.device_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `work_order_id` | str |  | no | Work order id. |  |
| `device_id` | str |  | no | Device. |  |
| `work_order_type` | str |  | no | Type. | PREVENTIVE, CORRECTIVE, SENSOR_RECALIBRATION, SENSOR_REPLACEMENT, CONFIG_CHANGE |
| `downtime_hours` | float64 | h | no | Compactor unavailable hours. |  |
| `description_code` | str |  | no | Code. |  |
| `reported_at` | ts | UTC | no | Reported. |  |
| `started_at` | ts | UTC | no | Started. |  |
| `completed_at` | ts | UTC | no | Completed. |  |

### `finance/invoices`

Monthly invoices sent by a fictional waste operator to the customer, per contract (issued before extraction). Customer-operator data that the customer hands over to the service; Europress is not a party. total_eur == sum(lines.amount_eur).

Primary key: `invoice_id` · Foreign keys: `contract_id` → `reference/contracts.contract_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `invoice_id` | str |  | no | Invoice id. |  |
| `contract_id` | str |  | no | Contract. |  |
| `customer_id` | str |  | no | Customer. |  |
| `operator_id` | str |  | no | Operator. |  |
| `billing_period` | str | YYYY-MM | no | Service month. |  |
| `currency` | str |  | no | EUR. |  |
| `vat_excluded` | bool |  | no | Always true. |  |
| `total_eur` | float64 | EUR | no | Signed total (exact to the cent). |  |
| `n_lines` | int64 | count | no | Line count. |  |
| `dispute_status` | str |  | no | Customer dispute status (a dispute is not proof of an error). | NONE, OPEN, RESOLVED_CREDIT_NOTE, RESOLVED_NO_CHANGE, UNKNOWN_AS_OF |
| `issued_at` | ts | UTC | no | Issue time. |  |
| `record_note` | str |  | no | Always: SYNTHETIC invoice from a fictional operator to a fictional customer; not a real invoice. |  |
| `synthetic` | bool |  | no | Always true: the record is invented. |  |

### `finance/invoice_lines`

Lines of the SYNTHETIC operator-to-customer invoices: customer-operator data that the customer hands over to the service; Europress is not a party. Charges > 0, credits < 0. Matching to collections only via operator_job_ref (which may contain typos) and service_date.

Primary key: `invoice_line_id` · Foreign keys: `invoice_id` → `finance/invoices.invoice_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `invoice_line_id` | str |  | no | Line id. |  |
| `invoice_id` | str |  | no | Invoice. |  |
| `line_no` | int64 |  | no | Line number. |  |
| `line_type` | str |  | no | Line type. | LIFT_FEE, TRANSPORT, REMOTE_SURCHARGE, FUEL_SURCHARGE, HAUL_PER_TONNE, PROCESSING, REJECTION_REPROCESSING, MIN_CHARGE_TOPUP, MATERIAL_CREDIT, CONTAMINATION_PENALTY, SIDE_WASTE_FEE, EMERGENCY_SURCHARGE, CANCELLATION_FEE, WASTED_TRIP_FEE, RENTAL |
| `service_date` | date | local date | no | Service date (1st of month for rental). |  |
| `operator_job_ref` | str |  | yes | Job reference (NULL for rental). |  |
| `quantity` | float64 |  | no | Quantity in `unit` (t with 3 decimals; pct for fuel). |  |
| `unit` | str |  | no | Unit. | lift, km, t, pct_of_base, event, month |
| `unit_price_eur` | float64 | EUR | no | Unit price (for FUEL_SURCHARGE: the base amount the pct applies to). |  |
| `amount_eur` | float64 | EUR | no | Signed amount, exact to the cent. |  |
| `synthetic` | bool |  | no | Always true: the record is invented. |  |

### `labels_dev/anomaly_labels`

Ground-truth labels for train+validation periods (Task B). Includes explained/non-actionable labels (false-positive traps).

Primary key: `entity_type, entity_id, label_family`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `entity_type` | str |  | no | Entity labelled. | collection, invoice_line, device_period, device |
| `entity_id` | str |  | no | collection_id, invoice_line_id or device-period key. |  |
| `device_id` | str |  | yes | Device. |  |
| `label_family` | str |  | no | Label family (see SCENARIO_CATALOG). |  |
| `severity` | str |  | no | borderline or clear. | borderline, clear |
| `is_actionable` | bool |  | no | Whether a customer/operator action is warranted (False = explained, e.g. hygiene rule). |  |
| `explanation_code` | str |  | yes | Cause / explanation. |  |
| `value_at_stake_eur` | float64 | EUR | yes | Illustrative value at stake (signed for billing deltas: + = overcharge). |  |
| `scenario_id` | str |  | yes | Scenario family id. |  |
| `parameter` | float64 |  | yes | Episode parameter. |  |
| `benchmark_eur_per_t` | float64 | EUR/t | yes | Contract benchmark (COST_PER_T_HIGH). |  |
| `reference_eur_per_t` | float64 | EUR/t | yes | Reference collection cost per t (COST_PER_T_HIGH). |  |
| `true_moisture_extra_pct` | float64 | % | yes | Extra water mass share (MOISTURE). |  |
| `full_hours_before_collection` | float64 | h | yes | Hours container was full (DELAYED). |  |
| `true_contamination_pct` | float64 | % | yes | True contamination (quality labels). |  |
| `device_minus_weighbridge_kg` | float64 | kg | yes | Device estimate minus allocated net (WEIGHT_DISCREPANCY). |  |
| `event_at` | ts | UTC | no | Event time / period start. |  |
| `end_at` | ts | UTC | yes | Period end. |  |
| `eval_at` | ts | UTC | no | Evaluation time that defines the split: for collections max(event, issue of the invoice that bills it); otherwise event_at. |  |

### `labels_dev/reference_economics`

Reference (correct) charges per collection event from contract terms and operator billing basis (Task A answers for dev periods).

Primary key: `collection_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `collection_id` | str |  | no | Event. |  |
| `device_id` | str |  | no | Device. |  |
| `contract_id` | str |  | no | Contract. |  |
| `contract_version_id` | str |  | no | Applicable version (by local service date). |  |
| `service_date` | date | local date | no | Service date. |  |
| `status` | str |  | no | Event status. |  |
| `billing_mass_kg` | float64 | kg | yes | Billing mass; NULL if not a lift. |  |
| `billing_mass_basis` | str |  | yes | Basis. | WEIGHBRIDGE_NET, CONTRACT_DEFAULT_WEIGHT |
| `grade_applied` | str |  | yes | Grade applied (recyclables). |  |
| `index_price_eur_per_t` | float64 | EUR/t | yes | Index price of the service month. |  |
| `collection_cost_eur` | float64 | EUR | no | Logistics cost category. |  |
| `processing_cost_eur` | float64 | EUR | no | Processing category. |  |
| `penalties_eur` | float64 | EUR | no | Penalties category. |  |
| `material_credit_eur` | float64 | EUR | no | Credit (positive number). |  |
| `net_material_contribution_eur` | float64 | EUR | no | credit - collection - processing - penalties. |  |
| `total_customer_cost_eur` | float64 | EUR | no | -net_material_contribution. |  |
| `expected_invoice_amount_eur` | float64 | EUR | no | Sum of expected lines (== total_customer_cost). |  |
| `collection_cost_eur_per_t` | float64 | EUR/t | yes | collection_cost / t; NULL if mass unknown or 0. |  |
| `total_cost_eur_per_t` | float64 | EUR/t | yes | total_customer_cost / t; NULL if mass unknown or 0. |  |
| `observable_mass_source` | str |  | yes | Best mass source a customer could see at extraction (lifts only). NONE = a correct submission reports NULL EUR/t. | WEIGHBRIDGE_PUBLISHED, INVOICE_TONNAGE, DEVICE_ESTIMATE_ONLY, NONE |
| `event_at` | ts | UTC | no | Event time (actual or scheduled). |  |
| `eval_at` | ts | UTC | no | Evaluation time defining the split: max(event, issue of the billing invoice); extraction time if charged but not yet invoiced. |  |

### `labels_dev/reference_economics_monthly`

Reference economics aggregated per device and month (events within this package's label periods). Site-, material-, customer- and contract-level figures are group-bys of this table. Rental is excluded (monthly contract line).

Primary key: `device_id, month`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `device_id` | str |  | no | Device. |  |
| `site_id` | str |  | no | Site. |  |
| `customer_id` | str |  | no | Customer. |  |
| `material_stream` | str |  | no | Material. |  |
| `contract_id` | str |  | no | Contract. |  |
| `month` | str | YYYY-MM | no | Local service month. |  |
| `n_events` | int64 | count | no | All events incl. cancellations. |  |
| `n_lifts` | int64 | count | no | Completed + partial lifts. |  |
| `billing_mass_kg` | float64 | kg | yes | Sum of billing mass. |  |
| `collection_cost_eur` | float64 | EUR | no |  |  |
| `processing_cost_eur` | float64 | EUR | no |  |  |
| `penalties_eur` | float64 | EUR | no |  |  |
| `material_credit_eur` | float64 | EUR | no |  |  |
| `net_material_contribution_eur` | float64 | EUR | no |  |  |
| `collection_cost_eur_per_t` | float64 | EUR/t | yes | NULL if no mass. |  |
| `total_cost_eur_per_t` | float64 | EUR/t | yes | NULL if no mass. |  |

### `labels_dev/reference_charge_lines`

Expected invoice lines per event (dev periods).

Primary key: `collection_id, line_no`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `collection_id` | str |  | no | Event. |  |
| `line_no` | int64 |  | no | Line no. |  |
| `line_type` | str |  | no | Line type. |  |
| `quantity` | float64 |  | no | Quantity. |  |
| `unit` | str |  | no | Unit. |  |
| `unit_price_eur` | float64 | EUR | no | Unit price. |  |
| `amount_eur` | float64 | EUR | no | Signed amount. |  |

### `labels_dev/decision_truth`

Per decision case: best permissible action by simulated counterfactual (Task C, dev periods).

Primary key: `case_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `case_id` | str |  | no | Case. |  |
| `split` | str |  | no | Split. |  |
| `best_action` | str |  | no | Lowest adjusted simulated cost among permissible actions. |  |
| `best_benefit_cents` | int64 | EUR cents | no | Benefit of best vs NO_ACTION over the horizon. |  |
| `acceptable_actions` | str |  | no | Permissible actions within tolerance of best. |  |
| `no_action_acceptable` | bool |  | no | NO_ACTION within tolerance. |  |
| `near_threshold` | bool |  | no | Best action's benefit is within tolerance (ambiguous). |  |
| `constraint_conflict` | bool |  | no | The raw cheapest action is not permissible. |  |
| `hidden_cost_trap_present` | bool |  | no | Some action looks cheaper by lift count but costs more. |  |
| `tolerance_cents` | int64 | EUR cents | no | max(EUR 25, 3 % of best); an action is also acceptable within 2 paired standard errors of the best. |  |
| `truth_sensor_issue_active` | str |  | yes | Hidden sensor issue active at decision time (VERIFY_WEIGHT_SENSOR is warranted). |  |
| `truth_invoice_overcharge_90d_eur` | float64 | EUR | no | Overbilling in the prior 90 days (REVIEW_INVOICES value). |  |

### `labels_dev/decision_outcomes`

Simulated counterfactual outcome of every candidate action (NOT real-world causal evidence).

Primary key: `case_id, action`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `case_id` | str |  | no | Case. |  |
| `action` | str |  | no | Action. |  |
| `sim_cost_cents` | int64 | EUR cents | no | Simulated customer cost over horizon incl. one-off action cost. |  |
| `one_off_cost_cents` | int64 | EUR cents | no | Illustrative one-off cost of the action. |  |
| `n_replications` | int64 | count | no | Paired operational replications averaged (replication 0 = realised random stream). |  |
| `n_completed_lifts` | float64 | count | no | Mean lifts in horizon. |  |
| `collected_kg` | int64 | kg | no | Mean mass handled. |  |
| `overflow_open_hours` | float64 | h | no | Mean hours the container was full while the site was open. |  |
| `max_interval_violations` | float64 | count | no | Mean number of intervals exceeding max days + 1. |  |
| `end_state_mass_kg` | float64 | kg | no | Mass left in container + side stock at horizon end. |  |
| `terminal_value_cents_per_kg` | float64 | EUR cents/kg | no | Contract-based marginal cost used to value end-state mass differences. |  |
| `adjusted_cost_cents` | int64 | EUR cents | no | sim_cost + (end_state_mass - NO_ACTION end_state_mass) x terminal_value_cents_per_kg. |  |
| `permissible` | bool |  | no | Satisfies max-interval and overflow constraints. |  |
| `adjusted_cost_sd_cents` | int64 | EUR cents | no | Std. dev. of adjusted cost across replications. |  |
| `benefit_vs_no_action_cents` | int64 | EUR cents | no | Mean paired NO_ACTION adjusted cost minus this. |  |
| `benefit_se_cents` | int64 | EUR cents | no | Standard error of the paired benefit. |  |
| `diff_to_best_se_cents` | int64 | EUR cents | no | Standard error of the paired difference to the best permissible action. |  |
| `naive_lift_saving_cents` | int64 | EUR cents | no | Saving estimated from lift count alone (naive). |  |
| `hidden_cost_trap` | bool |  | no | Naive saving > EUR 50 but real benefit < 0. |  |
| `split` | str |  | no | Split. |  |

### `benchmark/decision_cases`

Decision cases (inputs only). Solutions may use only data observable before decision_at.

Primary key: `case_id` · Foreign keys: `device_id` → `reference/devices.device_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `case_id` | str |  | no | Case id. |  |
| `device_id` | str |  | no | Device. |  |
| `horizon_days` | int64 | days | no | Evaluation horizon. |  |
| `split` | str |  | no | Split. | train, validation, test, test_private |
| `candidate_actions` | str |  | no | Operational actions to choose from. |  |
| `diagnostic_actions` | str |  | no | Diagnostic actions that may be recommended in addition. |  |
| `decision_at` | ts | UTC | no | Decision time. |  |

### `benchmark/task_ab_test_collections`

Collection ids of the public test period to score (answers private).

Primary key: `collection_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `collection_id` | str |  | no | Event. |  |
| `device_id` | str |  | no | Device. |  |
| `status` | str |  | no | Status. |  |

### `benchmark/task_b_test_invoice_lines`

Invoice lines of the public test period to score.

Primary key: `invoice_line_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `invoice_line_id` | str |  | no | Line. |  |
| `invoice_id` | str |  | no | Invoice. |  |

### `labels_dev/operator_scorecard`

Task B2 truth for train+validation months: operator performance scorecard per fictional operator x region x month, computed from simulator truth. Operators are fictional; part of every difference has causes other than the operator.

Primary key: `operator_id, region_code, month`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `operator_id` | str |  | no | Fictional operator. |  |
| `region_code` | str |  | no | Region of the customer sites. |  |
| `month` | str | YYYY-MM | no | Local month (jobs: scheduled time; invoices: billing period). |  |
| `split` | str |  | no | Label period of the month. | train, validation, test |
| `n_operator_jobs` | int64 | count | no | Jobs the operator had to perform (completed, partial, missed, wasted trip). |  |
| `n_completed_lifts` | int64 | count | no | Completed or partial lifts. |  |
| `billed_eur` | float64 | EUR | yes | Invoiced total for the billing month. |  |
| `on_time_rate` | float64 | fraction | yes | Completed lifts within 2 h of the scheduled time. |  |
| `missed_visit_rate` | float64 | fraction | yes | MISSED_BY_OPERATOR / operator jobs. |  |
| `weighbridge_shared_7d_rate` | float64 | fraction | yes | Completed lifts whose weighbridge ticket was shared with the customer within 7 days. |  |
| `median_share_lag_days` | float64 | days | yes | Median days from weighing to sharing (shared tickets). |  |
| `billing_overcharge_pct` | float64 | % | yes | Overbilled amount as % of the contract-correct amount (billing discrepancies, not intent). |  |
| `billing_undercharge_pct` | float64 | % | yes | Underbilled amount (missing lines, uninvoiced lifts) as % of the correct amount. |  |
| `discrepant_line_rate` | float64 | fraction | yes | Invoice lines (incl. missing ones) with a billing discrepancy. |  |
| `weight_bias_pct` | float64 | % | yes | 100 x (operator allocated net - true collected mass) / true mass, all tickets incl. unshared. |  |
| `median_order_to_lift_hours` | float64 | h | yes | Median hours from order to lift (ordered collections). |  |

### `benchmark/task_b2_scorecard_rows`

Task B2 test rows (operator x region x month) to predict. No answers.

Primary key: `operator_id, region_code, month`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `operator_id` | str |  | no | Operator. |  |
| `region_code` | str |  | no | Region. |  |
| `month` | str | YYYY-MM | no | Month. |  |
| `n_operator_jobs` | int64 | count | no | Jobs in the row. |  |

### `benchmark/operator_action_cases`

Task C2 cases: one per active public contract at the extraction time. Choose any subset of the candidate actions (empty = no action). split=dev cases have public values in labels_dev/operator_action_values.

Primary key: `case_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `case_id` | str |  | no | Case id OC-nnnnn. |  |
| `contract_id` | str |  | no | Contract. |  |
| `device_id` | str |  | no | Device. |  |
| `customer_id` | str |  | no | Customer. |  |
| `operator_id` | str |  | no | Current operator. |  |
| `region_code` | str |  | no | Region. |  |
| `split` | str |  | no | dev (values public) or test (values private). | dev, test |
| `candidate_actions` | str |  | no | Comma list of allowed actions (from DISPUTE_INVOICE, REQUEST_WEIGHBRIDGE_DATA, RENEGOTIATE_CONTRACT, TENDER_OR_SWITCH_OPERATOR). |  |
| `notice_period_days` | int64 | days | no | Contract notice period. |  |
| `as_of_at` | ts | UTC | no | Case date (data extraction time). |  |

### `labels_dev/operator_action_values`

Task C2 truth (dev cases): simulated value of each operator/contract action under the published rules in configs/assumptions.yaml -> operator_actions. Synthetic-world value, not evidence of real savings.

Primary key: `case_id, action`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `case_id` | str |  | no | Case. |  |
| `split` | str |  | no | dev|test |  |
| `action` | str |  | no | Action. | DISPUTE_INVOICE, REQUEST_WEIGHBRIDGE_DATA, RENEGOTIATE_CONTRACT, TENDER_OR_SWITCH_OPERATOR |
| `value_eur` | float64 | EUR | no | Expected value of the action (positive = worth doing). |  |
| `positive` | bool |  | no | value_eur > 0. |  |
| `annual_contract_cost_eur` | float64 | EUR/year | no | Contract-correct annual cost at current terms (annualised). |  |
| `recoverable_overbilling_eur` | float64 | EUR | yes | DISPUTE_INVOICE: documented overbilling on undisputed invoices of the last 90 days. |  |
| `renegotiated_annual_cost_eur` | float64 | EUR/year | yes | RENEGOTIATE_CONTRACT: annual cost at peer-median terms. |  |
| `peer_level` | str |  | yes | Peer group used (L1 region+material+model+size ... L4 material+model). |  |
| `best_alternative_operator` | str |  | yes | TENDER_OR_SWITCH_OPERATOR: alternative used. |  |
| `best_set_value_eur` | float64 | EUR | no | Value of the best action set for the case (renegotiate and tender are exclusive). |  |

## Private evaluation package (NOT FOR DISTRIBUTION)

### `truth/facilities`

Fictional treatment facilities. Operator-side information: Europress does not know where the operator takes the material, so this table is not published. Public weighbridge tickets (records the operator chooses to share) carry the facility id.

Primary key: `facility_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `facility_id` | str |  | no | Facility id. |  |
| `operator_id` | str |  | no | Operator. |  |
| `region_code` | str |  | no | Region. |  |
| `facility_type` | str |  | no | Type. |  |

### `truth/truth_hourly_state`

PRIVATE simulator ground truth per device-hour. Never a model input.

Primary key: `device_id, hour_start_at`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `device_id` | str |  | no | Device. |  |
| `true_container_mass_kg` | float32 | kg | no | Mass in container at hour end. |  |
| `true_fill_pct` | float32 | % | no | True volumetric fill. |  |
| `true_inflow_kg` | float32 | kg | no | Material generated in the hour. |  |
| `true_side_stock_kg` | float32 | kg | no | Loose side waste waiting (overflow/downtime). |  |
| `true_container_full` | bool |  | no | Container at capacity. |  |
| `true_compactor_down` | bool |  | no | Downtime. |  |
| `true_sensor_gain` | float32 |  | no | Weight sensor gain. |  |
| `true_sensor_offset_kg` | float32 | kg | no | Sensor offset. |  |
| `hour_start_at` | ts | UTC | no | Hour start. |  |

### `truth/truth_collections`

PRIVATE truth for completed/partial lifts.

Primary key: `collection_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `collection_id` | str |  | no |  |  |
| `device_id` | str |  | no |  |  |
| `true_mass_before_kg` | float64 | kg | no |  |  |
| `true_fill_before_pct` | float64 | % | no |  |  |
| `true_collected_kg` | float64 | kg | no |  |  |
| `true_residual_kg` | float64 | kg | no | Left in container (partial). |  |
| `true_side_waste_collected_kg` | float64 | kg | no |  |  |
| `true_side_stock_before_kg` | float64 | kg | no |  |  |
| `true_contamination` | float64 | fraction | no |  |  |
| `true_moisture_extra` | float64 | fraction | no | Water mass / dry mass. |  |
| `hours_since_last` | int64 | h | no |  |  |
| `cycle_overflow_kg` | float64 | kg | no |  |  |
| `cycle_full_hours` | int64 | h | no |  |  |
| `delay_h` | float64 | h | yes | actual - scheduled. |  |

### `truth/truth_sensor_episodes`

PRIVATE sensor episodes (drift, calibration, faults...).

Primary key: `device_id, episode_type, start_at`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `device_id` | str |  | no |  |  |
| `episode_type` | str |  | no |  |  |
| `parameter` | float64 |  | no |  |  |
| `start_at` | ts | UTC | no |  |  |
| `end_at` | ts | UTC | yes |  |  |

### `truth/truth_device`

PRIVATE device truth and mass-balance totals.

Primary key: `device_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `device_id` | str |  | no |  |  |
| `true_mean_density_kg_m3` | float64 | kg/m3 | no |  |  |
| `true_daily_generation_kg` | float64 | kg/day | no |  |  |
| `true_capacity_mass_kg` | float64 | kg | no |  |  |
| `true_contamination_base` | float64 | fraction | no |  |  |
| `true_misallocated_recyclable_share` | float64 | fraction | no |  |  |
| `split` | str |  | no | public|holdout |  |
| `n_messages_lost` | int64 | count | no |  |  |
| `n_duplicates` | int64 | count | no |  |  |
| `true_total_inflow_kg` | float64 | kg | no |  |  |
| `true_end_container_kg` | float64 | kg | no |  |  |
| `true_end_side_stock_kg` | float64 | kg | no |  |  |
| `episodes` | str |  | no | Scenario episodes (repr). |  |

### `truth/weighbridge_all`

PRIVATE: all tickets incl. unshared/unpublished, with tare error and true net.

Primary key: `ticket_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `ticket_id` | str |  | no |  |  |
| `weighing_event_id` | str |  | no |  |  |
| `operator_id` | str |  | no |  |  |
| `operator_job_ref` | str |  | no |  |  |
| `collection_id` | str |  | no |  |  |
| `vehicle_id` | str |  | no |  |  |
| `facility_id` | str |  | no |  |  |
| `gross_kg` | int64 | kg | no |  |  |
| `tare_kg` | int64 | kg | no |  |  |
| `tare_method` | str |  | no |  |  |
| `net_kg` | int64 | kg | no |  |  |
| `allocated_net_kg` | int64 | kg | no |  |  |
| `allocation_method` | str |  | no |  |  |
| `loads_on_vehicle` | int64 | count | no |  |  |
| `material_declared` | str |  | no |  |  |
| `shared_with_customer` | bool |  | no |  |  |
| `public` | bool |  | no | Published before extraction. |  |
| `true_net_kg` | float64 | kg | no |  |  |
| `tare_error_kg` | int64 | kg | no |  |  |
| `arrival_at` | ts | UTC | no |  |  |
| `published_at` | ts | UTC | yes |  |  |

### `truth/quality_all`

PRIVATE: all quality assessments.

Primary key: `quality_assessment_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `quality_assessment_id` | str |  | no |  |  |
| `collection_id` | str |  | no |  |  |
| `ticket_id` | str |  | no |  |  |
| `operator_id` | str |  | no |  |  |
| `public` | bool |  | no |  |  |
| `material_declared` | str |  | no |  |  |
| `contamination_pct_est` | float64 | % | no |  |  |
| `grade` | str |  | no |  |  |
| `rejected` | bool |  | no |  |  |
| `remark_code` | str |  | yes |  |  |
| `assessed_at` | ts | UTC | no |  |  |
| `published_at` | ts | UTC | yes |  |  |

### `truth/invoice_line_labels`

PRIVATE: every injected billing discrepancy (line-level and missing/uninvoiced).

Primary key: `—`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `invoice_line_id` | str |  | yes | NULL for missing lines / uninvoiced collections. |  |
| `invoice_id` | str |  | no |  |  |
| `collection_id` | str |  | yes |  |  |
| `discrepancy_type` | str |  | no |  |  |
| `expected_amount_cents` | int64 | EUR cents | yes |  |  |
| `billed_amount_cents` | int64 | EUR cents | no |  |  |
| `delta_cents` | int64 | EUR cents | no | billed - expected (+ = overcharge). |  |

### `truth/vehicles`

PRIVATE vehicle tares.

Primary key: `vehicle_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `vehicle_id` | str |  | no |  |  |
| `operator_id` | str |  | no |  |  |
| `true_tare_kg` | int64 | kg | no |  |  |
| `stored_tare_kg` | int64 | kg | no |  |  |

### `benchmark/decision_cases_private`

Decision cases (inputs only). Solutions may use only data observable before decision_at.

Primary key: `case_id` · Foreign keys: `device_id` → `reference/devices.device_id`

| column | type | unit | nullable | description | allowed values |
|---|---|---|---|---|---|
| `case_id` | str |  | no | Case id. |  |
| `device_id` | str |  | no | Device. |  |
| `horizon_days` | int64 | days | no | Evaluation horizon. |  |
| `split` | str |  | no | Split. | train, validation, test, test_private |
| `candidate_actions` | str |  | no | Operational actions to choose from. |  |
| `diagnostic_actions` | str |  | no | Diagnostic actions that may be recommended in addition. |  |
| `decision_at` | ts | UTC | no | Decision time. |  |

`labels_test/*` have the same schemas as `labels_dev/*`; `benchmark/decision_cases_private` as `benchmark/decision_cases`.
