# Pitch: SMART Weight Check

Deck: `submission/pitch_deck.pptx` (PDF copy: `submission/pitch_deck.pdf`). Speaker notes are in the deck.

**One sentence (P01):** For businesses that pay for waste by the lift and by the tonne but only ever see the weight their operator reports, SMART Weight Check uses an independent scale in the Europress compactor to check every lift and every per-tonne invoice line against the contract, and turns each difference into a proposal a human approves.

## Outline (P02)

The kanban's 6 slides, plus a title slide, an integration slide (brief: 15 % of the score) and an accuracy slide (20 %: analytical reasoning). Two appendix slides are not presented.

| # | slide | 3 points | fed by (FINDINGS.md) |
|---|---|---|---|
| 1 | **Title**: SMART Weight Check. Weigh at source, check every tonne | the one sentence · synthetic data · Europress challenge | P01 |
| 2 | **Problem**: the customer pays per lift and per tonne, but only the operator knows the weight | CMP-00046: €258/t, 2.3× the benchmark · 4 wasted trips (€346) while the fill reading was stuck at 88 % and the scale read ~0 kg · customer lifts at 6–25 % full | C03, C02 |
| 3 | **Solution**: weigh → check → propose | load-cell frame in the compactor · every lift and per-tonne line checked against device weight, ticket and contract · each difference becomes a proposal with a reason, a check and Approve / Reject / Undo | C08–C14, weight check |
| 4 | **Live demo** | CMP-00046 story · CMP-00042: combined load split equally, re-split by device weight · CMP-00047: no ticket shared → ask for it · 341 lifts checked: 205 agree, 38 explained, 4 billing questions | Customer value |
| 5 | **From load cell to decision** (SMART integration) | 4-ch ADC in the SMART cabinet, existing modem · fields map 1:1 to the dataset schema · proposals as an API payload with `requires_human_approval: true` | 2_SOFTWARE_DEMO.md |
| 6 | **Weight concept** | 4 load cells in low-profile rails under the container · σ 1.5 % target, ~1.0 % accuracy budget · €1,200 factory / €3,400 retrofit · auto-zero every lift + weighbridge span check · 3-phase validation | U11, U12, 1_WEIGHING_CONCEPT.md |
| 7 | **Accuracy is value** (why a real scale) | σ ≤ 1.75 % keeps ≥ 95 % of 3 t loads within ±100 kg · overbilling detection collapses above ~2.5 % · best no-scale model: 7 % → value scan only | U10, research |
| 8 | **Business model** | €15/device-month (median value €36 → 2.4×) · sensitivity table: price matters most · weigh where it pays · per-tonne service = hypothesis | B02–B08 |
| 9 | **Limits and next steps** | not proven: willingness to pay, real savings, hardware accuracy · next: 10 customer interviews, yard test, 20-site pilot | B09 |
| A1 | Appendix: demo screenshots (backup) | | P06 |
| A2 | Appendix: run it, sources, licences | | P07, 3_BUSINESS_CASE.md |

## Speaker script (P10): 5 minutes

Ask the organisers for the exact time limit. **For a 3-minute slot, cut slides 5 and 7 and shorten the demo to step 1 and step 2.**

| slide | time | say |
|---|---|---|
| 1 | 0:00–0:15 | "Customers pay for waste by the lift and by the tonne, but the only scale they ever see belongs to their operator. SMART Weight Check puts an independent scale in the Europress compactor and checks every lift and every invoice line." |
| 2 | 0:15–0:50 | "Meet compactor 46, a cardboard press in Lohja. In July its fill reading stuck at 88 % while the container scale read almost nothing. Four trucks came for nothing: €346 of wasted-trip fees. In September the customer ordered three lifts at 6 to 25 % full. Over the quarter it paid €258 per tonne, 2.3 times its contract benchmark. Nobody did anything wrong. Nobody could see it. All of this is synthetic data." |
| 3 | 0:50–1:15 | "Our answer has three steps. Weigh: four load cells under the container. Check: every lift and every per-tonne invoice line against the device weight, the operator's ticket and the contract. Propose: every difference becomes a proposal with a reason and a check, and a human approves it. Nothing runs by itself." |
| 4 | 1:15–2:30 | **Live demo** (`streamlit run app/app.py`). 1) CMP-00046 opens: point at the stuck fill line vs the flat weight line, then € per tonne 2.3×. 2) Switch to CMP-00042: "This site was invoiced 2.94 tonnes for a container that held 580 kg. Two containers shared a truck and the net was split equally. The customer's total is right, but this site's € per tonne is wrong. The device weight re-splits it. That's a fact, not blame." 3) CMP-00047: "No ticket was shared, and the invoice says 425 kg more than the container weighed. Proposal: ask for the ticket." 4) Click Approve, then Undo. "A human decides, and it can always be undone." *(If the demo fails, use the backup screenshots on slide A1.)* |
| 5 | 2:30–2:50 | "It fits SMART as it is: the weighing module sits in the SMART cabinet, uses the existing modem, and its fields map one-to-one onto SMART telemetry and collection events. Proposals leave as an API payload that says: requires human approval." |
| 6 | 2:50–3:25 | "The scale: four 10-tonne load cells in low-profile rails under the container. Every time the truck takes the container away, the frame reads zero, a free calibration check on every lift. Each lift is also compared with the operator's own ticket to catch drift. Target accuracy 1.5 %. €1,200 as a factory option, €3,400 as a retrofit. Validation: a yard test with water tanks, a 20-site pilot, then a winter." |
| 7 | 3:25–3:50 | "Why a real scale? At 1.5 % accuracy, 98 % of 3-tonne loads land within ±100 kg and 95 % of 10 % overbilling is caught. Above 2.5 % that collapses. We tried estimating weight without a scale: 7 % at best. That's good for a trend, so it becomes our free value scan, but it's not good enough to check an invoice." |
| 8 | 3:50–4:30 | "Price: €15 per device per month. The median customer can realise about €36 per device-month, so they keep 2.4 times the fee. Price matters most: at €10 it takes six and a half years to earn back the onboarding, at €15 two years. And the scale should go where it pays: the factory option pays back in under three years for half the devices, a retrofit only for the top ones. The big prize, a per-tonne full service with Europress in the middle, needs verified weight first. That's a hypothesis, and we label it that way." |
| 9 | 4:30–5:00 | "What we have not proven: that customers pay, that the savings are real, and that the frame reaches 1.5 % in a Finnish winter. So the next steps are ten customer interviews, a two-week yard test and a 20-site pilot. Weigh at source, check every tonne. Thank you." |

## Rehearsal log (P10)

The pitch has to be rehearsed by a person, twice, with a timer.

| run | date | time | what to cut or fix |
|---|---|---|---|
| 1 | | | |
| 2 | | | |

## Demo checklist
- Before the pitch: `streamlit run app/app.py`. It opens on CMP-00046. Keep the tab open, then reload once to warm the cache.
- Direct links: `http://localhost:8501/?device=CMP-00042`, `http://localhost:8501/?device=CMP-00047`.
- Backup: `notes/screenshots/` (also on appendix slide A1).
