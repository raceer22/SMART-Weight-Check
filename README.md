# SMART Weight Check: our solution to the Europress challenge

**Weigh at source. Check every tonne.** For businesses that pay for waste by the lift and by the tonne but only ever see the weight their operator reports, SMART Weight Check uses an independent scale in the Europress compactor to check every lift and every per-tonne invoice line against the contract, and turns each difference into a proposal a human approves.

## Our solution

**Jury: start at [`submission/README.md`](submission/README.md).** It maps the brief's three deliverables and every evaluation criterion to a file.

| | |
|---|---|
| Weighing concept (part 1) | [`submission/1_WEIGHING_CONCEPT.md`](submission/1_WEIGHING_CONCEPT.md): load-cell weigh frame, σ 1.5 % target, €1,200 factory / €3,400 retrofit, calibration, validation plan |
| Software demo (part 2) | [`submission/2_SOFTWARE_DEMO.md`](submission/2_SOFTWARE_DEMO.md): `app/app.py`, traceable economics, SMART integration pathway |
| Business case | [`submission/3_BUSINESS_CASE.md`](submission/3_BUSINESS_CASE.md): €15 per device-month priced from value, sensitivity, what is not proven |
| Pitch | [`submission/pitch_deck.pdf`](submission/pitch_deck.pdf) / [`.pptx`](submission/pitch_deck.pptx) with speaker notes; 1:50 video [`submission/pitch_video.mp4`](submission/pitch_video.mp4) |
| Licences | [`submission/THIRD_PARTY.md`](submission/THIRD_PARTY.md) |

### Run the demo

You need Python 3.11 or newer and git. From a terminal:

```bash
git clone https://github.com/raceer22/Since-AI.git
cd Since-AI
python -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -e ".[dev,app]"               # project + streamlit + matplotlib
streamlit run app/app.py
```

A browser tab opens on the **decision inbox** of one fictional customer: 25 compactors at 8 sites. Every finding of the quarter is a decision, ranked by the euros it is about: trucks that came for nothing, shared trucks split equally, invoiced tonnage without a ticket, lifts at low fill. **Approve** sends a question to the account manager, **Reject** dismisses it, and both can be undone. **Why?** opens the evidence: the compactor's fill and weight, its cost per tonne, and the lifts the decision is about. To show one compactor only, use `http://localhost:8501/?device=CMP-00042`.

The Task A and Task B output files used by the scripts below:

```bash
python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv
python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv
```

### Reproduce the analysis

```bash
python notes/explore.py                                                   # tables and charts of the weight data (quickstart)
python examples/weighing_accuracy_value.py data/competition/public        # what each scale accuracy is worth
python notes/weight_without_scale.py data/competition/public              # can software replace the scale? (~2 min)
python notes/premature_rule.py data/quickstart/public my_task_b.csv       # weight-based early-lift rule vs baseline
python baselines/business_case.py competition --params configs/our_params.yaml --out our_business_case   # ~1 min
python notes/business_case_sensitivity.py                                 # price x adoption, payback, hypotheses
```

All findings, with the table or script each comes from, are in [`notes/FINDINGS.md`](notes/FINDINGS.md).

*All data is synthetic. Not Europress data. Built with help from Claude (Anthropic) via Claude Code; see `submission/THIRD_PARTY.md`.*

---

*Everything below is the organisers' documentation of the dataset.*

# Europress × Since AI Hackathon 2026: SMART Material Value Engine synthetic data

> **SYNTHETIC DATA. Reviewed by Europress Group Oy on 30 Oct and 4 Nov 2026; all requested changes are implemented in v1.0.1.**
> This repository contains no Europress customer data, device readings, product specifications, contracts or
> validated prices. Every customer, site, contract, cost and invoice is invented. The data does not show that
> affordable compactor-integrated weighing is technically feasible, and it does not show real-world savings.

**Challenge:** *From smart device data to a stronger customer position in the waste value chain.* How can
trustworthy device data (precise operating status today, and weight in the future) give customers an
independent, explainable view of the waste services they buy, support decisions that a human approves, and
enable new Europress business models?
Since AI Hackathon 2026, Turku, 6–8 November 2026. Challenge partner: Europress Group Oy.

New here? Open **`START_HERE.html`** (or `START_HERE.md`): a plain-language overview with a glossary.

## Relation to SMART

Today Europress delivers the collection equipment, and most of the downstream service is defined by the waste
operator. Our strategy is to become a more integral part of the waste value chain and to give customers
better tools to steer and verify the waste services they buy. A smart device that knows its own operating
status precisely, and in future its weight, can give the customer an independent, trustworthy view of what
actually happened, and opens the way to entirely new business models. This is the core of the challenge.

More about Europress and SMART: [europressgroup.com](https://www.europressgroup.com) and [epsmart.fi](https://epsmart.fi).

## How this dataset supports the two-part challenge brief

The official challenge brief has two connected parts. This dataset is the shared evidence base for both.

| Brief part | What the dataset gives you |
|---|---|
| **1. Get the weight**: an affordable, sufficiently accurate, scalable and retrofit-friendly way to weigh in the compactor | The accuracy target used in the simulation (about ±100 kg on a 3 t cardboard load in normal operation), realistic sensor faults (drift, calibration errors, fault periods, replacements), and `examples/weighing_accuracy_value.py`, which shows what a given accuracy is worth: €/t precision and the ability to verify operator tonnage. The dataset does not contain or prove a weighing design; that is your concept. |
| **2. Create value from the weight**: customer value and new Europress business models | Device telemetry (fill, mass, status), collections, operator weighbridge tickets (when shared), quality grades, contracts, invoices and price indices for about 500 fictional compactors over one year, plus Tasks A–E below |

## Prices and roles

Europress is currently not a party to waste transport or treatment. Tariffs, processing fees and material
credits are agreed between the customer and the waste operator. All prices in this dataset are hypothetical.
Europress's goal is to bring transparency to the waste value chain and to develop value-added services based
on weight data.
In the data, contracts and invoices are information the customer hands over to the service (or estimates),
and weighbridge tickets and quality grades are operator data that are visible only when the operator shares
them. Only cardboard and plastics can earn a material credit; all other streams, including paper, are
chargeable to the customer. Material quality is assessed only by the waste operator at its facility.

## What is in the box

| Deliverable | Path |
|---|---|
| Generator (stateful event-driven simulator, chunked, deterministic for a given seed) | `src/europress_data/` |
| Profiles: quickstart (50 devices × 90 days), competition (about 500 × 365), enterprise (5,000 × 730, stress test) | `configs/profiles/*.yaml`, assumptions in `configs/assumptions.yaml` |
| Validator (release-blocking invariants, plausibility, scenario coverage) | `python -m europress_data.validate` |
| Scoring harness for Tasks A, B, B2, C, C2 | `python -m europress_data.evaluate` |
| Baselines B1–B6 and a business-case calculator that takes **your** parameters | `baselines/` |
| Tests (golden cases, determinism, chunk invariance, validator mutation tests, Europress review checks) | `tests/` |
| Documentation | `docs/` (start with `QUICKSTART_FOR_BUILDERS.md`) |
| Examples (SQL queries, first analysis, weighing-accuracy explorer, recommendation API mock) | `examples/` |

## Tasks

| Task | Question |
|---|---|
| A | What should each collection cost under the customer–operator contract? Collection €/t, net material contribution |
| B | Which collections and invoice lines are actionable irregularities (unnecessary lifts, delays, weight differences, billing discrepancies)? |
| **B2** | **Operator performance scorecard**: punctuality, missed visits, weighbridge-data sharing, billing accuracy and weight differences per operator, region and month |
| C | Operational decisions for a device (schedule and threshold changes are SMART's existing domain and serve as context) |
| **C2** | **Operator and contract actions**: dispute an invoice, request weighbridge data, renegotiate, or tender / switch the operator |
| D | Business case for a new service or business model: pricing and adoption assumptions are **part of your answer** |
| E | Explainability and traceability |

Details, metrics and baseline results: `docs/BENCHMARK.md`.

## Commands

```bash
pip install -e ".[dev]"
python -m pytest                                        # about 5 minutes
python -m europress_data.validate --profile competition
python baselines/run_all.py competition                 # all baselines, scored on the public validation labels
python baselines/business_case.py competition --params configs/business_case_example_params.yaml --out my_business_case
python examples/weighing_accuracy_value.py data/competition/public
python examples/run_queries.py data/quickstart/public
# generate your own synthetic world (any seed); the official packages use organiser-held seeds
python -m europress_data.generate --profile quickstart --seed 12345 --out my_world
```

Output layout: `data/<profile>/public/` is the distributable package. `data/<profile>/private_evaluation/`
is **not for distribution** and holds truth, test labels, hold-out customers and private golden cases. The
official packages were generated with undisclosed seeds; the public manifest records only a SHA-256
commitment of the seed, so the private evaluation data cannot be regenerated from the public package.

## Documentation map

| Document | Content |
|---|---|
| `START_HERE.md` / `START_HERE.html` | Plain-language overview and glossary |
| `docs/QUICKSTART_FOR_BUILDERS.md` | 15-minute start |
| `docs/SCHEMA.md` | Tables, keys, joins, time semantics |
| `docs/DATA_DICTIONARY.md` | Every column: type, unit, nullability, allowed values |
| `docs/DATA_GENERATION_METHODOLOGY.md` | Causal model, distributions, observation models, splits |
| `docs/ECONOMIC_MODEL.md` | Exact formulas, rounding, worked examples, who agrees which price |
| `docs/SCENARIO_CATALOG.md` | 40 scenario families and their generated coverage |
| `docs/BENCHMARK.md` | Tasks, metrics, leakage precautions, baseline results, failure cases |
| `docs/DATA_QUALITY_REPORT.md` | Actual validation outcomes, row counts, sizes, distributions |
| `docs/ASSUMPTIONS_AND_LIMITATIONS.md` | Europress-confirmed facts vs synthetic assumptions, limitations |
| `docs/EUROPRESS_REVIEW.md` | Europress review of 30 Oct 2026: every change request and where it is implemented |
| `docs/GAP_ANALYSIS.md` | What was wrong with the v0 starter pack and what changed |

## Principles

* Simulate first, then observe. Every public value goes through a measurement or recording model.
* Never fabricate missing values. Unknown mass gives a NULL €/t.
* Labels come from simulator truth. They include explained cases (false-positive traps), and some actions are
  harmful or neutral.
* Operators are fictional and are described neutrally. Billing discrepancies are discrepancies, not intent,
  and part of every difference has causes other than the operator (device sensors, combined loads, data gaps).
* All recommendations are proposals that need human approval.

Use of the data and of team results follows the Since AI Hackathon 2026 rules. During the event, ask questions
in the Europress challenge channel on the event Discord or at the Europress Q&A point (see the Since AI Field Guide).
