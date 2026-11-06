# Assumptions and limitations

## A. Europress-confirmed facts vs. synthetic assumptions

| Statement | Status | Source |
|---|---|---|
| Europress manufactures waste-handling equipment (compactors, balers) and offers the SMART service: equipment monitoring, fill-level estimation, collection ordering, maintenance information and reporting | **Europress-confirmed** (review 30 Oct 2026) | europressgroup.com, epsmart.fi; Europress review |
| Today Europress delivers the collection equipment, and most of the downstream service is defined by the waste operator. Europress's strategy is to become a more integral part of the waste value chain and to give customers better tools to steer and verify the services they buy | **Europress-confirmed** (README → Relation to SMART is Europress's own text) | Europress review |
| Europress is currently **not a party** to waste transport or treatment. Tariffs, processing fees and material credits are agreed between the customer and the waste operator; Europress does not know the actual prices and can only estimate costs | **Europress-confirmed** | Europress review |
| Only cardboard and plastics can earn a material credit; all other streams, including paper, are chargeable to the customer | **Europress-confirmed** | Europress review; `configs/assumptions.yaml → materials` |
| Material quality is determined only by the waste operator at its facility, using its own assessment. Europress has no technology to determine material quality before the facility | **Europress-confirmed**; the data reflects it (grades exist only in operator quality records) | Europress review |
| Europress does not know to which facility the operator takes the material | **Europress-confirmed**; facilities are not published, only the facility id on tickets the operator chooses to share | Europress review |
| Most devices are emptied on call (fill-triggered); only a small share runs on a fixed schedule | **Europress-confirmed** direction; the exact mix (78 % / 12 % / 10 % on-call / fixed / hybrid) is a synthetic choice | `assumptions.yaml → policies.mix` |
| Equipment classes **COMBI** (compactor and container permanently joined, emptied as one unit) and **DUO** (stationary compactor, the detachable container is emptied) | **Europress machine-type categories**. No model names, model numbers or model-specific technical data are represented | Europress review; `assumptions.yaml` |
| Affordable compactor-integrated weighing produces usable weight data | **Challenge assumption**. The dataset does *not* show it is technically feasible. "Affordable" is Europress's own requirement for a solution | Challenge brief |
| **The dataset depicts a future scenario in which most devices have integrated weighing.** In the competition pack about 91 % of devices have it | **Future scenario**. Sensor install dates are synthetic and do not imply that weighing has been deployed in the past | `devices.weight_measurement`, `sensor_registry` |
| Weighing accuracy in normal operation: at most about 100 kg error on a 3 t cardboard load (about ±3.3 %) for about 95 % of readings; simulated as reading noise max(15 kg, 1.4 %) plus a small installation calibration error | **Challenge simulation target set with Europress**, not a specification of any Europress weighing solution. Injected fault scenarios (drift, calibration errors, fault states) deliberately exceed it | `assumptions.yaml → telemetry` |
| Fill-estimate accuracy (about ±4 percentage points) and failure rate (about 1.2 fault visits per device per year) | **Accepted by Europress** as synthetic assumptions | `assumptions.yaml → telemetry`, `simulate.py` |
| Container volumes, compacted densities, compressibility | **Synthetic assumption**, not product data | `configs/assumptions.yaml` |
| Operator data sharing (0–97 %), lags (under half a day to 45 days) and invoice error rates (1.0–3.5 %) | **Synthetic assumption**. Operators are fictional (Hauler Alpha–Epsilon); differences between them are needed for the scorecard and tender tasks | `assumptions.yaml → operators` |
| Operators serve overlapping real Finnish regions with the current split; recognisability risk acknowledged and accepted by Europress | **Synthetic**, accepted | `assumptions.yaml → regions, operators` |
| Tariffs, gate fees, credit shares, surcharges, minimum charges (customer–operator) | **Hypothetical**. Used as such; Europress takes no position on price levels | `assumptions.yaml: contracts`, `materials.processing_fee` |
| Material price indices for cardboard and plastics (incl. a cardboard collapse and a film spike) | **Synthetic illustrative index**, not market data (Europress decided to keep the synthetic index) | `world._build_price_index` |
| Business-case prices, cost to serve, adoption and purchase conditions | **Not given**. They are neutral parameters that teams choose and justify (Task D) | `configs/commercial_assumptions.yaml` |
| Valuation rules of operator and contract actions (dispute recovery, renegotiation acceptance, tender cost) | **Hypothetical, published** so teams can reason about them | `assumptions.yaml → operator_actions` |
| Customers, sites, devices, contracts, invoices, people | **Entirely fictional**. Municipality and region names are real geography only | generator |

No external dataset was imported or calibrated against. No personal data exists: the validator scans every
public text column for e-mail, phone, Finnish personal-id and IBAN patterns, and the release fails on any hit.

## B. Modelling limitations

1. **Not calibrated.** Densities, generation rates, prices and fees are order-of-magnitude choices. Absolute
   €/t levels and saving sizes must not be quoted as market facts.
2. **Simplified logistics.** Each site has a single billable distance, routes are not optimised, the truck has
   no capacity limit, and combined loads only pair jobs of the same customer and material on the same day.
3. **One device per stream per site.** There are no relocations between sites (installation history has one
   row per device). Commissioning and decommissioning within the window are modelled.
4. **Contamination** is a scalar share per load. There are no images and no composition vectors. The quality
   grade is a noisy operator assessment, and only for credit-eligible streams.
5. **Counterfactuals** (Task C) use the same synthetic demand and operator behaviour. They are internally
   consistent but not causal evidence about the real world. Leftover mass is valued at a contract-based marginal
   cost per kg, which is an approximation. Orders in flight at the decision time are not carried over.
6. **Operator and contract actions** (Task C2) are valued with simple published rules (recovery rates,
   acceptance probabilities, effort costs, peer-median terms). Real negotiations and tenders depend on much
   more (volumes, relationships, service quality, market timing).
7. **Operator scorecard** (Task B2) metrics come from simulator truth; punctuality and missed visits are the
   customer's own records, billing accuracy and weight differences need reconciliation. Service quality effects
   of a switch of operator are not modelled.
8. **Device signals.** `press_load_index` is derived from the device's own (biased) fill estimate. Policies see
   the fill estimate with its systematics but ignore isolated message drops and value rounding. Fill sensors
   can read falsely high for a few days (S40); the mass reading reveals it. Scenario S40 and its frequency are
   synthetic assumptions and do not describe the performance of the SMART fill measurement.
9. **Maintenance** exists to provide context only. It is not a predictive-maintenance benchmark.
10. **Time.** Timestamps are UTC and local logic uses Europe/Helsinki, including DST. Telemetry is hourly.
11. **Enterprise profile.** It is generated with the same models, adds a second-year price regime shift, and is a
   stress test, not a distributed package.

## C. Release status

The dataset is **synthetic**. Europress reviewed it on 30 Oct 2026 (8 review points, all "approved with
changes"); every change request (30 Oct and 4 Nov 2026) is implemented in v1.0.1 and listed in `docs/EUROPRESS_REVIEW.md`. No figure
in it represents Europress customer data, verified commercial results or proven savings. Every automated
recommendation is a proposal that needs human approval.
