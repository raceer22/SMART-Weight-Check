# SMART Weight Check

**Weigh at source. Check every tonne.** An independent scale in the Europress compactor checks every lift and every per-tonne invoice line against the contract, and turns each difference into a proposal a human approves.

*Europress challenge, Since AI Hackathon 2026. All data is synthetic, not Europress data. Every number is tagged observed / simulated / estimated / hypothetical.*

## Contents

| deliverable | file |
|---|---|
| (1) Illustrated weighing concept: principle, placement, BOM and cost, installation, calibration, error sources, validation plan | [1_WEIGHING_CONCEPT.md](1_WEIGHING_CONCEPT.md) |
| (2) Working software demo: setup, walkthrough, traceable economics, SMART integration pathway | [2_SOFTWARE_DEMO.md](2_SOFTWARE_DEMO.md) |
| (3) Customer value and business case: service, benefit, commercial model, productisation, assumptions, what remains untested | [3_BUSINESS_CASE.md](3_BUSINESS_CASE.md) |
| Pitch deck, with speaker notes | [pitch_deck.pdf](pitch_deck.pdf) · [pitch_deck.pptx](pitch_deck.pptx) |
| Pitch video, 1:50 | [pitch_video.mp4](pitch_video.mp4) |
| Third-party libraries, data, models and services, with licences | [THIRD_PARTY.md](THIRD_PARTY.md) |

## Where each evaluation criterion is answered

| weight | criterion | main evidence | where |
|---|---|---|---|
| 25 % | Weighing concept | Load-cell weigh frame: σ 1.5 % target, ~1.0 % accuracy budget, €1,200 factory option / €3,400 retrofit. Auto-zero on every lift plus a span check against the operator's weighbridge. Three-phase validation plan. Software-only alternatives tested: 7 % error at best | [1](1_WEIGHING_CONCEPT.md) |
| 25 % | Customer and business value | €332 k/year realisable on €5.19 M of waste spend (6.4 %, estimated). Compactor CMP-00046 paid 2.3× its contract benchmark per tonne, plus €346 for wasted trips | [3](3_BUSINESS_CASE.md) |
| 20 % | Data-driven value and analytical reasoning | Accuracy-vs-value curve; no-scale weight experiments; value per lever with grounded realisation shares; price sweep and sensitivity; a weight-based early-lift rule raises F1 from 0.72 to 0.86 | [1](1_WEIGHING_CONCEPT.md) · [2](2_SOFTWARE_DEMO.md) · [3](3_BUSINESS_CASE.md) |
| 15 % | Software workflow and SMART integration | Streamlit decision inbox: every finding ranked by € at stake, approved or rejected by a human, with the evidence one click away. Device → SMART → engine → proposal API pathway, with the dataset schema as the integration contract | [2](2_SOFTWARE_DEMO.md) |
| 10 % | Commercial productisation | Free value scan → hardware where it pays → €15 per device-month subscription; per-tonne service as a labelled hypothesis | [3](3_BUSINESS_CASE.md) |
| 5 % | Clarity, uncertainty and limits | A list of what is not proven in every document; an evidence tag on every number | all |

## Run the demo (about 5 minutes)

Python 3.11 or newer, from the repository root:

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev,app]"
streamlit run app/app.py
```

The browser opens on the decision inbox of one fictional customer: 25 compactors at 8 sites. The walkthrough is in [2_SOFTWARE_DEMO.md](2_SOFTWARE_DEMO.md#demo-path-about-75-seconds). Each document lists the scripts that reproduce its numbers.
