# Start here

**Europress × Since AI Hackathon 2026: SMART Material Value Engine**
Turku · 6–8 November 2026 · challenge partner Europress Group Oy · synthetic data v1.0.1

## The challenge in one minute

Shops, warehouses, factories and hotels press their cardboard, plastic and waste into **compactors**. A truck
from a **waste operator** empties them, weighs the load at the operator's facility and sends the customer an
invoice. Today the operator holds the weight, judges the material quality and defines most of the service. The
customer has little independent evidence of what actually happened.

Europress makes the compactors. Its SMART service already knows each device's fill level and operating status,
and in future the device could also know its **weight**. The question:

> **From smart device data to a stronger customer position in the waste value chain.** How can trustworthy
> device data (precise operating status today, and weight in the future) give customers an independent,
> explainable view of the waste services they buy, support decisions that a human approves, and enable new
> Europress business models?

The official brief has two parts: **1. Get the weight** (an affordable, accurate, retrofit-friendly weighing
concept) and **2. Create value from the weight** (software, analytics and business models). This dataset is
the evidence base for both.

Everything here is **synthetic**: about 500 invented compactors over one year, invented customers, contracts
and invoices. You can use it freely; nothing in it is real Europress, customer or operator data.

## Who is who

| Party | Role in reality | In the data |
|---|---|---|
| Customer (fictional shops, factories, …) | owns the waste, signs the contract with the operator, pays | `customers`, `sites`, `contracts`, `invoices` (the customer's own papers) |
| Waste operator (fictional "Hauler Alpha–Epsilon") | empties, transports, weighs, judges quality, invoices | `collection_events`, `weighbridge_tickets` and `quality_assessments` (only when the operator shares them) |
| Europress | makes the device; SMART monitors it | `devices`, `telemetry_hourly` (fill, mass, status) |

Europress is currently **not a party** to transport or treatment: prices are agreed between the customer and
the operator, and every price in this dataset is hypothetical.

## The two machine types

| Type | What it is |
|---|---|
| **COMBI** | compactor and container permanently joined; the whole unit is taken away and emptied (all biowaste units) |
| **DUO** | the compactor stays on site; only the detachable container is emptied (all mixed-plastic units) |

## What can go wrong (and is in the data)

* **Unnecessary lifts**: a container emptied half-empty, because a schedule is too frequent, a customer orders
  "to be safe" before the weekend, or a fill sensor reads "full" while the weight shows it is not.
* **Late lifts**: the container overflows, side waste piles up, emergency fees follow.
* **Weight differences**: the device weight and the operator's weighbridge disagree (sensor drift, an outdated
  vehicle tare, two loads on one truck, side waste).
* **Billing discrepancies**: a duplicated line, a wrong surcharge, an old tariff, a tonnage that differs from the weighbridge record, a lift
  that was never invoiced. They are discrepancies, not accusations.
* **Value lost**: cardboard spoiled by contamination, a contract that gives the customer no material credit.

Only cardboard and plastics can earn a material credit; paper, mixed waste and biowaste cost money to treat.

## What you can build

| Task | In plain words |
|---|---|
| A | Recompute what every lift should have cost under the contract, and the cost per tonne |
| B | Find the irregular lifts and invoice lines (and do not flag the ones that have a good reason) |
| B2 | Build an **operator scorecard**: punctuality, missed visits, data sharing, billing accuracy, weight differences |
| C | Operational decisions for a device (context: schedules and thresholds are SMART's existing domain) |
| C2 | Recommend **dispute an invoice / request weighbridge data / renegotiate / tender the operator** |
| D | A business case for a new Europress service: **you choose and justify the price and adoption** |
| E | Explain everything so a human can check and approve it |

A strong solution combines device data with the customer's own papers, shows its evidence, states its
uncertainty, stays neutral towards operators and never acts without human approval.

## Your first 30 minutes

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python examples/first_analysis.py data/quickstart/public
python baselines/run_all.py quickstart
```

Then read `docs/QUICKSTART_FOR_BUILDERS.md`. Spreadsheet users: the quickstart pack has every table as CSV in
`data/quickstart/public/csv/`.

## Where things are

| You want to… | Open |
|---|---|
| get going | `docs/QUICKSTART_FOR_BUILDERS.md`, `examples/` |
| know the tables and columns | `docs/SCHEMA.md`, `docs/DATA_DICTIONARY.md` |
| understand the money | `docs/ECONOMIC_MODEL.md` |
| know the tasks, metrics and baselines | `docs/BENCHMARK.md` |
| see what is assumed and what is not known | `docs/ASSUMPTIONS_AND_LIMITATIONS.md` |
| see how the data were made | `docs/DATA_GENERATION_METHODOLOGY.md`, `docs/SCENARIO_CATALOG.md` |
| see what Europress asked to change | `docs/EUROPRESS_REVIEW.md` |

## Ground rules

* **Synthetic data only.** Never present a number from it as a real saving or a real price.
* **Advice only.** Your system proposes; a human approves.
* **Neutral towards operators.** They are fictional; part of every difference is caused by sensors or data gaps.
* **Do not tune on the test period.** Score yourself on the validation labels.

## Glossary

| Term | Meaning |
|---|---|
| Compactor | machine that presses waste into a container to fit more in |
| Lift / collection | the operator empties the container |
| Fill level | how full the container is (%), estimated by the device |
| On call | the device or customer orders a lift when the container is full enough (most devices) |
| Fixed schedule | lifts on booked weekdays, whether full or not |
| Weighbridge | the scale at the operator's facility that weighs the truck in and out |
| Tare | the weight of the empty truck; an outdated stored tare biases every net weight |
| Net weight | gross minus tare = the material's weight |
| Material credit | money the operator credits the customer for valuable material (cardboard, plastics) |
| Processing fee | money the customer pays for treating the material (per tonne) |
| Contamination | wrong material in a load (e.g. food in cardboard); lowers the quality grade A/B/C/R |
| €/t | euros per tonne, the key cost measure; needs a known mass |
| Side waste | material left next to a full container |
| Peer median terms | the typical tariff of similar contracts (same region, material, pricing model, size) |
| Dev / test labels | answers you may use (dev) and answers the organisers keep (test) |
