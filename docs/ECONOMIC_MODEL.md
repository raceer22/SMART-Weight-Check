# Economic model

All tariffs, prices and amounts are **hypothetical and synthetic**. They are illustrative assumptions chosen
by Since AI, not Europress, operator or market prices. The model's purpose is to make every euro in the
dataset traceable to an event, a contract version and a stated rule.

> **Europress is currently not a party to waste transport or treatment. Tariffs, processing fees and material
> credits are agreed between the customer and the waste operator. All prices in this dataset are hypothetical.**
> In a real service, the contract and invoice data used here are data the customer hands over to the service, or
> estimates. Europress does not know the actual prices; it can only estimate costs.

Who agrees what:

| Item | Agreed / determined by | In the data |
|---|---|---|
| Lift, transport, per-tonne, processing fees, surcharges, minimum charges | customer and waste operator | `contract_versions` (customer-provided) |
| Material credit (cardboard and plastics only) and its share of the index | customer and waste operator | `contract_versions.credit_share_bp`, `price_index_monthly` |
| Billing mass | waste operator (weighbridge at its facility) | `weighbridge_tickets` (only if shared) |
| Material quality grade | waste operator, its own assessment at its facility | `quality_assessments` (only if shared) |
| Device fill, mass and status | the device (Europress SMART) | `telemetry_*` |

Two independent implementations exist and are cross-checked on 90 golden unit cases in the test suite:

* `src/europress_data/economics.py`, which uses integer cents and basis points. The generator and the baselines use it.
* `src/europress_data/reference_decimal.py`, which uses `decimal.Decimal` and was written from this document.

## 1. Conventions

| Topic | Rule |
|---|---|
| Currency | EUR, VAT excluded |
| Sign | Invoice and reference line amounts are signed from the customer's view: **charges > 0, credits < 0** |
| Storage | Tariffs in `contract_versions` are integer **cents** (`*_cents`), cents per tonne (`*_cents_per_t`) and **basis points** (`*_bp`, 100 bp = 1 %) |
| Mass | Integer kg. Tonnes = kg / 1000, quoted with 3 decimals on invoices |
| Rounding | Each line is rounded **once** to the cent, half away from zero. Totals are sums of rounded lines and are never rounded again |
| Per-tonne ratios | `cents × 1000 / kg`, rounded half away from zero to the cent. Returned as **NULL when mass is unknown or 0**. Never divide by zero, never impute |
| Version selection | The contract version whose `[effective_from, effective_to)` contains the **local (Europe/Helsinki) service date**. For executed events (COMPLETED, PARTIAL, WASTED_TRIP) the service date is `actual_at`; otherwise it is `scheduled_at` |
| Index month | Material credits (credit-eligible streams: cardboard, plastic film, mixed plastic) use the index price of the service month (`price_index_monthly.month`). It becomes known on `published_on`. Paper, mixed waste and biowaste are chargeable: the customer pays a processing fee and earns no credit |

## 2. Billing basis (mass)

Per-tonne lines use the **operator's** billing basis, not the device reading:

1. The weighbridge ticket's `allocated_net_kg`. For combined loads (two jobs on one truck) operators split the net equally.
2. If the operator has no ticket, the contractual `default_weight_kg`.

Device-side mass is never a billing basis **in today's world** (and in this dataset's invoices). It is the
customer's own measurement and is what makes economics visible when the operator does not share weighbridge
data: an independent reference against the operator's weighbridge ticket.

### 2b. Hypothetical scenario: the device weight as a billing or verification basis

A future business model could use the device weight itself. Teams may explore this in Task D, clearly labelled
as a hypothesis that differs from today's situation:

| Variant | Rule | What it would take |
|---|---|---|
| **Verification basis** | the operator's weighbridge mass stays the billing basis, but invoices are checked against the device mass; a difference beyond an agreed tolerance (e.g. the accuracy target of about ±3.3 %) triggers a review | contract clause; agreed tolerance; device calibration records |
| **Billing basis** | per-tonne lines are billed on the device mass (`collection_events.device_estimated_collected_kg`, or a calibrated variant); the weighbridge becomes the audit reference | proven accuracy and calibration regime; operator and customer acceptance; legal metrology questions |

You can compute both variants from the public data: re-price per-tonne lines with the device estimate instead of
`allocated_net_kg` (economics.py functions accept any mass), and compare with the invoices. Report how often the
two bases differ by more than the tolerance and why (sensor faults, side waste on the same truck, combined loads,
stored tares). The dataset does not show that such a model is accepted by operators or legally possible.

## 3. Line rules for one event

Inputs: version `v`, event status, billing mass `kg`, grade `g` (credit-eligible streams), index price `I` (cents/t).

| Line type | When | Amount (cents) |
|---|---|---|
| `LIFT_FEE` | COMPLETED / PARTIAL and `lift_fee_cents > 0` | `lift_fee_cents` |
| `TRANSPORT` | lift, and billable km > 0 | `max(0, contract_km − free_km) × per_km_cents` |
| `REMOTE_SURCHARGE` | lift, remote region | `remote_surcharge_cents` |
| `FUEL_SURCHARGE` | lift, bp > 0 | `round((LIFT + TRANSPORT + REMOTE) × fuel_surcharge_bp / 10000)` |
| `HAUL_PER_TONNE` | lift, mass known | `round(kg × haul_fee_cents_per_t / 1000)` |
| `PROCESSING` | lift, mass known, not rejected | `round(kg × processing_fee_cents_per_t / 1000)` |
| `REJECTION_REPROCESSING` | credit-eligible lift graded **R** | `round(kg × rejection_fee_cents_per_t / 1000)` (replaces PROCESSING) |
| `MIN_CHARGE_TOPUP` | lift, `min_charge_cents > 0`, mass known | `max(0, min − (LIFT+TRANSPORT+REMOTE+FUEL+HAUL+PROCESSING+REJECTION))` |
| `MATERIAL_CREDIT` | credit-eligible lift (cardboard, plastics), not R, `credit_share_bp > 0`, **mass and index price known** | `−round(kg × P / 1000)` with `P = round(max(floor, round(I × share_bp / 10000)) × quality_bp / 10000)` |
| `CONTAMINATION_PENALTY` | credit-eligible lift graded **C** | `contamination_penalty_cents` |
| `SIDE_WASTE_FEE` | loose overflow loaded at the lift | `side_waste_fee_cents` |
| `EMERGENCY_SURCHARGE` | trigger `AD_HOC_CUSTOMER` | `emergency_surcharge_cents` |
| `CANCELLATION_FEE` | CANCELLED_BY_CUSTOMER with notice **< 24 h** | `cancellation_fee_cents` |
| `WASTED_TRIP_FEE` | WASTED_TRIP | `wasted_trip_fee_cents` |
| `RENTAL` | monthly contract line, **not allocated to events** | `rental_cents_per_month` |

Quality factors: A = 1.00, B = 0.85, C = 0.60 (+ penalty), R = rejected (no credit, reprocessing fee).
SKIPPED_LOW_FILL (hybrid policy, at least 26 h notice) and MISSED_BY_OPERATOR produce no charge.

## 4. Categories (no double counting)

Each line type belongs to exactly one category:

```
collection_cost  = LIFT_FEE + TRANSPORT + REMOTE_SURCHARGE + FUEL_SURCHARGE + HAUL_PER_TONNE
                   + MIN_CHARGE_TOPUP + SIDE_WASTE_FEE + EMERGENCY_SURCHARGE
processing_cost  = PROCESSING + REJECTION_REPROCESSING
penalties        = CONTAMINATION_PENALTY + CANCELLATION_FEE + WASTED_TRIP_FEE
material_credit  = −MATERIAL_CREDIT                         (a positive number)

net_material_contribution = material_credit − collection_cost − processing_cost − penalties
total_customer_cost       = −net_material_contribution      (= sum of the event's invoice lines)

collection_cost_eur_per_t = collection_cost / (kg / 1000)    NULL if kg unknown or 0
total_cost_eur_per_t      = total_customer_cost / (kg / 1000) NULL if kg unknown or 0
```

The brief's formula `material_credits − collection − processing − penalties` is exactly `net_material_contribution`.
The figures mean different things and are kept apart:

* **Customer cost** (`total_customer_cost`) is what the customer pays the operator for this event.
* **Credit** is revenue-like for the customer, but it is a share of an index price, not a sale price.
* **Avoided expenditure** (a decision's benefit) is a simulated difference between two cost paths. It is never "profit".
* **Rental** is a fixed monthly cost. It is reported at contract-month level only.

## 5. Worked examples (also in tests and golden cases)

**Example 1: fixed per-lift contract, mixed waste, 2,340 kg.**
Lift 312.75 € (processing included). Transport (34 − 10) km × 1.85 € = 44.40 €. Fuel 4.50 % × 357.15 € = 16.07175 → **16.07 €**.
Collection cost = **373.22 €**. €/t = 373.22 / 2.340 = 159.4957 → **159.50 €/t**.

**Example 2: hybrid contract, cardboard, 3,115 kg, grade B, index 96.40 €/t, credit share 75 %.**
Lift 98.50 € + transport 44.40 € + fuel 4.5 % × 142.90 € = 6.43 €. Collection cost is 149.33 €.
Credit price: 96.40 × 0.75 = 72.30 €/t, then × 0.85 = 61.455 → 61.46 €/t. Credit = 3.115 × 61.46 = 191.4479 → **191.45 €**.
Net material contribution = 191.45 − 149.33 = **+42.12 €** (the load more than pays for its collection).
Collection €/t = 47.94 €/t.

**Example 3: per-tonne contract with a 210 € minimum, mixed waste, 125 kg.**
Transport 44.40 €, fuel 2.00 €, haul 0.125 × 67.40 = 8.425 → 8.43 €, processing 0.125 × 118.25 = 14.78 €.
The subtotal is 69.61 €, so `MIN_CHARGE_TOPUP` = **140.39 €** and the event total is 210.00 €.
Collection €/t = **1,561.76 €/t**. This is a legitimate contractual effect and a false-positive trap for naive "expensive lift" rules.

**Example 4: mass unknown.**
The lift, transport and fuel lines are still computable (149.33 €). Per-tonne lines and €/t are **NULL**.
`MIN_CHARGE_TOPUP` cannot be determined without mass, so on HYBRID_MIN and PER_TONNE contracts the
mass-independent subtotal **understates** the true collection cost. Report it as a lower bound.
The correct output says "cannot be computed". It never fills in a guessed mass.

## 6. Potential savings: the required structure

Every saving the dataset or a solution reports must state:

| Element | In the dataset |
|---|---|
| Baseline case | `decision_outcomes` row `action = NO_ACTION` (simulated from the actual physical state at `decision_at`; orders in flight are not carried over) |
| Proposed alternative | one `action` row, policy changed as defined in `decisions.py` |
| Changed assumptions | action definition (e.g. `REDUCE_FREQUENCY` = one step down the 5/3/2/1/0.5/0.25 lifts per week ladder) |
| Constraints | `max_interval_violations` (hygiene / fire / contract maximum days), `overflow_open_hours`, `permissible` |
| Estimated impact | `benefit_vs_no_action_cents` (mean over paired replications, standard error `benefit_se_cents`) on `adjusted_cost_cents`, i.e. horizon cost corrected for different end-state mass at a **contract-based marginal cost per kg** (`terminal_value_cents_per_kg`) |
| Uncertainty | `near_threshold`, tolerance `max(25 €, 3 %)`, `acceptable_actions` |
| What remains unproven | a simulated counterfactual is **not causal evidence**. It assumes the synthetic world's demand, operator behaviour and tariff are right |

Some actions are harmful. `hidden_cost_trap = true` marks actions whose naive lift-count saving exceeds 50 €
but whose real simulated benefit is negative, because emergency lifts, side-waste fees or minimum charges appear.

## 7. Operator and contract actions (Task C2)

Valued per contract with the published rules in `configs/assumptions.yaml → operator_actions` (hypothetical
parameters; argue for others in your business case if you like). Values are in EUR; positive = worth doing.

| Action | Value |
|---|---|
| `DISPUTE_INVOICE` | `dispute_recovery_rate × documented overbilling` on invoices issued in the last `dispute_lookback_days` that are not already disputed or credited (`dispute_status` NONE or RESOLVED_NO_CHANGE) `− dispute_admin_cost_eur`. Tonnage claims (weight-basis mismatch) count only with independent evidence: a shared ticket or the device's own weight |
| `REQUEST_WEIGHBRIDGE_DATA` | candidate only if under 80 % of the contract's lifts have a shared ticket. `request_weighbridge_comply_prob × annual weight-related overbilling that is currently unverifiable` (tonnage mismatches without evidence, operator net above the true mass on per-tonne charges) `− request_admin_cost_eur` |
| `RENEGOTIATE_CONTRACT` | peer-median terms (median tariff of contracts with the same region, material, pricing model and container size; wider groups if fewer than 4 peers). The operator considers it only if the contract costs at least `renegotiation_min_gap_pct` more than at peer terms: `renegotiation_success_prob × annual gap − renegotiation_effort_eur`, else `− renegotiation_effort_eur` |
| `TENDER_OR_SWITCH_OPERATOR` | for the best alternative operator serving the region: its typical (median) terms and its billing accuracy. If the alternative is at least `tender_min_gap_pct` cheaper: `tender_success_prob × annual difference × (12 − notice months) / 12 − tender_switch_cost_eur`, else `− tender_switch_cost_eur` (you stay) |

Annual figures are the contract-correct costs of the trailing window (the reference economics, i.e. what the
customer *should* have paid), annualised. Renegotiation and tender are mutually exclusive; dispute and request
can be combined with either. The scorer (`--task C2`) computes the value of your chosen set against the best set.
