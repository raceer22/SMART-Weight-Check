# SMART Weight Check: submission

**Weigh at source. Check every tonne.** An independent scale in the Europress compactor checks every lift and every per-tonne invoice line against the contract, and turns each difference into a proposal a human approves.

*Europress challenge, Since AI Hackathon 2026. All data is synthetic, not Europress data. Every number is tagged observed / simulated / estimated / hypothetical.*

## The three deliverables the brief asks for

| brief deliverable | where |
|---|---|
| (1) Illustrated weighing concept: principle, placement, BOM and cost, installation, calibration, error sources, validation plan | [1_WEIGHING_CONCEPT.md](1_WEIGHING_CONCEPT.md) |
| (2) Working software demo with setup notes, traceable economics and a SMART integration pathway | [2_SOFTWARE_DEMO.md](2_SOFTWARE_DEMO.md) · app: `streamlit run app/app.py` · screenshots: [../notes/screenshots/](../notes/screenshots/) |
| (3) Customer value and business case: service, benefit, commercial model, productisation, assumptions, what remains untested | [3_BUSINESS_CASE.md](3_BUSINESS_CASE.md) |
| Third-party libraries, data, models and services with licences | [THIRD_PARTY.md](THIRD_PARTY.md) |
| Pitch deck (with speaker notes) | [pitch_deck.pptx](pitch_deck.pptx) · [pitch_deck.pdf](pitch_deck.pdf) · script: [../notes/PITCH.md](../notes/PITCH.md) |

## Where each evaluation criterion is answered

| weight | criterion | main evidence |
|---|---|---|
| 25 % | Weighing concept | load-cell weigh frame. σ 1.5 % target, ~1.0 % accuracy budget; €1,200 factory / €3,400 retrofit. Auto-zero on every lift plus a weighbridge-referenced span check. Three-phase validation plan. Software-only alternatives tested: 7 % at best (concept doc) |
| 25 % | Customer and business value | €332 k/year realisable on €5.19 M spend (6.4 %, estimated). CMP-00046 story: 2.3× benchmark €/t and €346 of wasted trips (business case) |
| 20 % | Data-driven value and analytical reasoning | accuracy-vs-value curve; no-scale experiments; value per lever with grounded realisation shares; price sweep and sensitivity; weight-based early-lift rule raises F1 from 0.72 to 0.86 (`notes/FINDINGS.md`) |
| 15 % | Software workflow and SMART integration | Streamlit demo with weight check and human-approved proposals; device → SMART → engine → proposal API pathway with the dataset schema as the contract (software doc) |
| 10 % | Commercial productisation | free value scan → hardware where it pays → €15 per device-month subscription; per-tonne service as a labelled hypothesis (business case) |
| 5 % | Clarity, uncertainty and limits | "what we have not proven" lists in every document; evidence tags on every number |

## Five-minute quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev,app]"
python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv
python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv
streamlit run app/app.py
```

## Working notes behind the numbers
- [../notes/FINDINGS.md](../notes/FINDINGS.md): every finding with its source table or script (Epics 1–3).
- [../notes/PROGRES.md](../notes/PROGRES.md): what was done, task by task.
- [../configs/our_params.yaml](../configs/our_params.yaml): our business-case parameters, each with its reason.
- [../our_business_case/](../our_business_case/): calculator output and sensitivity tables.
- `.devtool/features/`: the team's task board.
