# 3 · Customer value and business case: SMART Weight Check

*Brief deliverable 3. Customer value is **estimated** from the synthetic competition data (52 public customers, 447 devices). Prices, costs, adoption and realisation shares are **hypothetical**: our own parameters, each justified in `configs/our_params.yaml`. Nothing here is a Europress price, a market finding or a demonstrated saving. Europress is not a party to waste transport or treatment today.*

## The service

**SMART Weight Check** is a SMART add-on for customers who own Europress compactors. Every month it:
1. **Weighs** every lift at the source, with the SMART weigh frame (`1_WEIGHING_CONCEPT.md`).
2. **Checks** every lift and every per-tonne invoice line against the device weight, the operator's ticket and the customer's contract.
3. **Proposes** actions with a reason and a check before acting. The customer approves, rejects or undoes each one: dispute a line, ask for a ticket, re-split a combined load, change a threshold or schedule, check the scale.

The operator's weighbridge stays the billing basis. The device weight is the customer's independent check.

## Measurable customer benefit (estimated, synthetic)

| | all 52 customers, per year |
|---|---|
| annual waste spend | €5.19 M |
| value identified by the checks | €1.18 M (22.8 % of spend) |
| value we assume is realisable | **€332 k (6.4 % of spend)** |
| median realisable value per device-month | **€36** (25th–75th percentile €20–72) |

Where it comes from (realisable, per year): contestable service charges €102 k · avoided unnecessary lifts €81 k · contract terms on recyclables €60 k · tendering or renegotiation €58 k · billing corrections €31 k. Contamination is out of scope: quality is graded only by the operator, and weight cannot see it.

**How it is measured per customer:**
- € per tonne per container, before and after;
- € of invoice lines corrected by credit notes;
- lifts avoided at low weight;
- share of lifts with a shared ticket.

The app reports all four from records, so a pilot customer can see the benefit directly instead of relying on our estimate.

**A concrete case** (FINDINGS C03): compactor CMP-00046 paid €258 per tonne, 2.3× its contract benchmark, plus €346 for four wasted trips. Those trips happened while its fill reading was stuck at 88 % and its scale read ~0 kg.

## Commercial model for Europress

| element | proposal | why |
|---|---|---|
| **Free value scan** | contracts + invoices + SMART fill data + no-scale weight estimate (7 % per lift) | shows each customer its € per tonne and identified value **before** any hardware; finds where a scale pays |
| **Weighing hardware** | factory option on new compactors (~€1,200), retrofit kit (~€3,400 installed) | sold as equipment, Europress's core business |
| **Subscription** | **€15 per device-month**; alternative 20 % of verified savings | priced from value: the median customer keeps 2.4× the fee |
| **Analyst support** | included for fleets from ~6 devices; self-service below | small fleets cost more to support than they pay |
| *Hypothesis* | per-tonne full service, transport procurement, materials marketplace | needs verified weight **and** a role Europress does not have today |

**How the price was set:**
1. Compute each customer's realisable value per device-month.
2. Assume a customer buys only if its value is at least 3× the fee.
3. Sweep prices from €5 to €60. Fee revenue peaks at **€15**.

**Base case (€15, 25 % of eligible customers adopt):**
- 23 of 52 customers are eligible; 5.8 adopt (61 devices).
- Revenue €11.0 k/year; operating and support costs €5.7 k; one-off onboarding €10.7 k.
- Year 1: **−€5.4 k**; then **+€5.4 k/year**; payback **2.0 years**.

### Sensitivity (B08): yearly profit after onboarding, € (hypothetical)

| price €/device-month | adoption 10 % | adoption 25 % | adoption 40 % |
|---|---|---|---|
| 10 | 943 | 2,358 | 3,773 |
| **15** | 2,148 | **5,370** | 8,592 |
| 25 | 1,735 | 4,338 | 6,941 |

- **Price matters most.** Swing in 3-year profit, one assumption at a time: price €16.5 k > support cost €12.4 k > operating cost €11.0 k > value realisation €6.9 k ≈ onboarding €6.9 k > adoption €6.5 k > purchase rule €5.4 k.
- **Who to serve:** at €15, a 16+ device customer brings ~€4.0 k profit a year, a 6–15 device customer ~€0.7 k, and a 2–5 device customer loses ~€0.2 k.
- **Hardware payback for the customer** (after the fee):

  | | installed cost | payback at the median device | devices paying back within 3 years | within 5 years |
  |---|---|---|---|---|
  | factory option | €1,200 | 2.9 years | 50 % | 62 % |
  | retrofit frame | €3,400 | 8.2 years | 17 % | 29 % |

  → **weigh where it pays.**

Full tables: `our_business_case/sensitivity.md`. Reproduce:

```bash
python baselines/business_case.py competition --params configs/our_params.yaml --out our_business_case
python notes/business_case_sensitivity.py
```

### Being honest about the size

On this synthetic sample the subscription earns only thousands of euros a year. It is a low-risk first step that fits Europress's role today. The larger value for Europress is:
1. **Weighing as a reason to buy a Europress compactor.** A factory option that pays back for half of the devices within 3 years.
2. **Verified weight as the entry ticket to per-tonne models.** As a hypothesis, a 3 % margin on customer spend in a tonne-based full service would be ≈ €156 k/year on this same sample. That gross margin is about 30× the subscription's yearly profit, but it needs verified weight, legal-for-trade questions answered and a new role.

## How it becomes part of SMART (productisation)

1. **Now:** the value scan runs on existing SMART data plus uploaded invoices. The "Weight" tab is in the SMART customer portal (the Streamlit demo is its prototype).
2. **Next 6 months:** weigh-frame yard test and 20-site pilot (`1_WEIGHING_CONCEPT.md`). Weight Check sold to pilot customers at €15 per device-month, or 20 % of verified savings.
3. **Next 12–18 months:** factory weighing option on new compactors; retrofit offered where the value scan shows payback within 5 years; proposal API for customers' purchasing systems.
4. **Later, hypothesis:** offer a per-tonne service once verified weight and operator agreements exist.

**Data ownership:** the weight is the customer's own measurement. Europress processes it for the customer. It is shared with the operator only with the customer's consent.

**Neutral by design:** combined loads, side waste and device scale issues are explained and kept apart from billing questions. A difference is a question, not an accusation.

## Assumptions (all hypothetical, see `configs/our_params.yaml`)
- Realisation shares: billing 0.7, over-servicing 0.35, contract 0.25, operator performance 0.25, tendering 0.4, contamination 0. They come from the dataset's published rules (dispute recovery 0.9, renegotiation success 0.5, tender success 0.8) and its simulated counterfactuals (cutting lifts realises 30–39 % of the naive saving).
- Cost to serve: €800 onboarding per customer, €100 per device, €3 per device-month for cloud, €50 per customer-month for an analyst.
- Adoption: 10 / 25 / 40 % of eligible customers; a customer buys only if value ≥ 3× fee.
- No churn over the 3-year view.
- Hardware costs are an indicative BOM.

## What remains untested
- **Willingness to pay** €15 per device-month: no customer was interviewed.
- **Real savings:** the world is synthetic and tariffs are hypothetical. Simulated counterfactuals are not causal evidence (`docs/ECONOMIC_MODEL.md` §6).
- **Hardware accuracy** σ 1.5 % on a real compactor, in winter, under hooklift loading; and the **hardware cost**.
- **Operator acceptance:** of device weight as evidence, of ticket requests (the dataset assumes 60 % comply), and of re-split combined loads.
- **Safety of avoiding "early" lifts:** hygiene, overflow and site reasons make some of them right.
- **Future models:** billing on device weight would need a legal-for-trade instrument (EU directive 2014/31/EU on non-automatic weighing instruments) and a new role for Europress.
