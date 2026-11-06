# Benchmark: tasks, evaluation and baselines

**Challenge:** *From smart device data to a stronger customer position in the waste value chain.* The benchmark
rewards **reasoning about cause, evidence and constraints**: device data as an independent, explainable view of
the waste services a customer buys. It does not reward aggressive optimisation. Every task can be solved with
SQL and rules, with classical ML, or with agents under human approval. No task requires an LLM.

> Europress is currently not a party to waste transport or treatment. Tariffs, processing fees and material
> credits are agreed between the customer and the waste operator. All prices in this dataset are hypothetical.
> Do not assume that Europress knows these prices: in a real service they come from the customer (contracts,
> invoices) or from the operator (weighbridge, quality), or they are estimates.

## Tasks and metrics

| Task | Question | Unit | Metric (`python -m europress_data.evaluate`) |
|---|---|---|---|
| **A: Financial reconstruction** | What should each event cost under the customer–operator contract (all statuses, including cancellation and wasted-trip fees)? What is collection €/t and the net material contribution? Prices are hypothetical customer–operator tariffs; Europress is not a party. | collection_id | Share exact to the cent per category (missing predictions count as wrong); coverage; €/t accuracy per **observable mass source** (published ticket, invoice tonnage, device estimate only); **€/t reported where no mass source is observable** (`observable_mass_source = NONE`, should be 0) |
| **B: Anomaly detection** | Which collections and invoice lines are actionable irregularities (unnecessary lifts, delays, device-vs-weighbridge differences, billing discrepancies against the customer–operator contract)? | (entity_type, entity_id, label_family) | Per-family precision, recall and F1; **explained cases flagged as anomalies** (false-positive traps); value-weighted recall; macro-F1 |
| **B2: Operator performance scorecard** | For each fictional operator × region × month: punctuality, missed visits, weighbridge-data sharing and lag, billing over/undercharge, discrepant lines, weight bias (operator net vs true mass), order-to-lift time. Operators serve overlapping regions, so they can be compared. Billing accuracy is measured against the customer–operator contract; Europress is not a party. | (operator_id, region_code, month) in `benchmark/task_b2_scorecard_rows` | Per metric: `1 − min(1, |error| / tolerance)` averaged over rows with ≥ 10 jobs, plus within-region rank correlation; overall score 0–100 (`--task B2`) |
| **C: Operational decisions (context)** | Which candidate action should a human approve at `decision_at`: schedule and threshold changes, mass-based triggers, sorting interventions; are diagnostics warranted? Fill thresholds and schedules are SMART's existing domain and serve as context. | case_id | **Acceptable share and mean regret in €** (expected over paired replications, 500 € penalty for impermissible or non-candidate actions). Best-action share is reported but noisy. Diagnostics precision and recall |
| **C2: Operator and contract actions** | Which of `DISPUTE_INVOICE`, `REQUEST_WEIGHBRIDGE_DATA`, `RENEGOTIATE_CONTRACT`, `TENDER_OR_SWITCH_OPERATOR` should a human approve for each active contract? Choose any subset (renegotiate and tender are exclusive). Valuation rules: `ECONOMIC_MODEL.md` §7 | case_id in `benchmark/operator_action_cases` | **Mean regret €** (best set value − value of your set) and value-capture share; per-action precision and recall (`--task C2`) |
| **D: Business case for a new service or business model** | Where could a customer gain, and what could Europress offer and charge? **Pricing and adoption assumptions are part of the task**: choose them, justify them with value evidence from the data, and show their sensitivity. Future models where Europress sits in the middle of the value chain (procuring transport for the customer, a tonne-based full service, operator tendering as a service, a materials marketplace) are welcome as clearly labelled hypotheses. Prices in the data are hypothetical customer–operator tariffs; Europress is not a party today. | customer / site / portfolio | Judged with the rubric below; calculator: `baselines/business_case.py --params your.yaml` |
| **E: Explainability** | Can every conclusion be traced to source rows, assumptions and formulas? | any output | Judged with the rubric below |

### Rubric for D and E (judges)

| Criterion | 0 | 1 | 2 |
|---|---|---|---|
| Evidence separation | mixes observed, estimated and simulated | partially labelled | every figure tagged *observed / estimated / simulated / hypothetical* |
| Traceability | totals only | links to tables | row-level audit trail (job ref → ticket → contract version → lines) |
| Constraints and uncertainty | ignored | mentioned | quantified (hygiene max days, overflow risk, sensor quality, missing tickets) |
| Pricing and adoption reasoning (D) | prices asserted | prices given with a story | prices and adoption derived from customer value in the data, with sensitivity analysis |
| Human approval | auto-executes | approval implied | explicit proposal + rationale + reversal path |
| Avoids over-claiming | claims real savings | hedged | states what remains unproven (see ECONOMIC_MODEL §6) |
| Neutral tone towards operators | blames operators | mostly neutral | neutral; separates operator-caused from device- or data-caused differences |

## Splits and leakage precautions

* **Time split** (`metadata/dataset_manifest.json → label_periods`): `train` and `validation` labels are public
  in `labels_dev/`. `test` labels are private.
* **Customer hold-out**: about 10 % of devices (whole customers) are absent from the public package. Their
  full data and their `as-of` snapshot exist only in `private_evaluation/`.
* **No regeneration of the private data**: the official packages were generated with organiser-held seeds. The
  public manifest records only a SHA-256 commitment of the seed and a configuration hash without the seed.
  Running the generator with any other seed produces a different synthetic world.
* **Task C, leak-free**: private decision cases sit at a single cutoff. Solutions see only
  `holdout_asof_<cutoff>/`, the data received before the cutoff. Public dev cases are for learning, and the
  public data contains their future, so **solutions must filter with `as_of` themselves**
  (`europress_data.sdk.open_dataset(root, as_of=...)`). Organisers should spot-check this.
* **Task B2**: a month is a dev month only if its jobs and its invoices (issued by the 15th of the next month)
  lie before the end of the validation period; later months are test months.
* **Task C2**: customers are split 40 % dev / 60 % test. Dev cases are valued as of the first day of the last
  month whose invoices lie inside the validation period (competition: 1 Jul 2026), using only earlier events;
  test cases are valued at the data extraction time. Dev values therefore never contain test-period information.
* `collection_events.weight_reconciliation_status` and `invoice_match_status` are naive statuses computed at extraction time. They can reflect tickets and invoices published after a decision, so recompute them as-of (Baseline 3 does).
* Labels are derived from simulator truth and operator records, not from customer-side features. Some families
  are nearly a direct read of a public operator record: REJECTED_LOAD and CONTAMINATION_VALUE_LOSS (published
  grades). The evaluator therefore also reports `macro_f1_detection_only`, which excludes them. In Task B2,
  punctuality, missed visits and order-to-lift time are the customer's own records; billing accuracy and weight
  bias need reconciliation.
* Billing reference data (`reference_economics`, `reference_charge_lines`) and collection-level billing labels
  are public only if the **invoice that bills them** was issued in train or validation. This stops test-period
  invoice lines from being reconstructable from public dev answers.
* Device-period labels (sensor drift, calibration, density shifts, fill-sensor false highs) are public only if
  the episode **ended** before the test period.
* `true_*` columns exist only in truth and label tables.
* Golden cases: `benchmark/golden_cases_public.json` (public) and `private_evaluation/benchmark/golden_cases_private.json`.

## Baselines (`baselines/`)

| # | File | Idea |
|---|---|---|
| B1 | `b1_economic_calculator.py` | Applies the contract rules. Mass fallback chain: published ticket → invoice tonnage → device estimate → NULL |
| B2 | `b2_rules_anomaly.py` | One readable rule per family (low fill on a scheduled lift, €/t > 2× benchmark, full hours before a lift, device vs ticket > 10 %, grade C/R, invoice vs B1 line comparison) |
| B3 | `b3_next_best_action.py` | Rules on as-of features (median fill before lift, full hours, skips, reconciliation share) |
| B4 | `b4_ml_models.py` | scikit-learn gradient boosting: per-family classifiers (Task B) and a best-action classifier restricted to the candidates (Task C) |
| B5 | `b5_operator_scorecard.py` | Task B2 from the customer's records: timestamps, shared tickets, invoices vs B1, operator net vs device estimate |
| B6 | `b6_operator_actions.py` | Task C2 rules: dispute B2-flagged recent lines, request data for unshared per-tonne contracts without device weight, renegotiate at ≥ 12 % gap to public peer-median terms, tender at ≥ 25 % |
| ref | `run_all.py` | Also scores *always NO_ACTION*, a *naive aggressive saver* (Task C) and *act on everything* (Task C2) |
| D | `business_case.py` | Calculator that takes **your** parameters (`--params`); refuses to run without them |

Run them all: `python baselines/run_all.py competition` writes `reports/baselines_competition.json`.

<!-- BASELINES:START -->
### Baseline results (competition profile, public validation labels)

Scores on the private test period are kept by the organisers and are not shown here, so that nobody calibrates against the test period. Score yourself on the validation period with the commands in `QUICKSTART_FOR_BUILDERS.md`.

**Task A — financial reconstruction (B1)**

| split | net exact to cent | collection cost exact | €/t coverage | €/t within 5 % | fabricated €/t |
|---|---|---|---|---|---|
| validation | 0.964 | 0.998 | 0.997 | 0.976 | 3 |

Mass basis used by B1: {'WEIGHBRIDGE': 15905, 'INVOICE_QUANTITY': 3717, 'NOT_A_LIFT': 3040, 'DEVICE_ESTIMATE': 1271, 'UNKNOWN': 63}

**Task B — anomaly detection (macro-F1 over families with positives)**

| model | validation |
|---|---|
| B2_rules | 0.7309 |
| B4_gradient_boosting | 0.3518 |
| hybrid_ml_plus_rules | 0.7818 |

Per-family (B2 rules, validation):

| family | positives | precision | recall | F1 | explained cases flagged |
|---|---|---|---|---|---|
| PREMATURE_UNJUSTIFIED | 404 | 0.9023 | 0.5941 | 0.7164 | 0 |
| COST_PER_T_HIGH | 371 | 0.7538 | 0.7925 | 0.7727 | 90 |
| DELAYED_COLLECTION | 466 | 0.7714 | 0.7747 | 0.773 | 0 |
| WEIGHT_DISCREPANCY | 189 | 0.8643 | 0.9101 | 0.8866 | 27 |
| CONTAMINATION_VALUE_LOSS | 345 | 1.0 | 0.6174 | 0.7634 | 0 |
| REJECTED_LOAD | 27 | 1.0 | 1.0 | 1.0 | 0 |
| OUTDATED_TARIFF | 1 | 0.0 | 0.0 | 0.0 | 0 |
| DUPLICATE_LINE | 24 | 0.8571 | 1.0 | 0.9231 | 0 |
| WRONG_SURCHARGE | 22 | 0.9167 | 1.0 | 0.9565 | 0 |
| WEIGHT_BASIS_MISMATCH | 10 | 0.4286 | 0.6 | 0.5 | 0 |
| UNMATCHED_LINE | 31 | 0.8182 | 0.871 | 0.8438 | 0 |
| MISSING_LINE | 25 | 1.0 | 1.0 | 1.0 | 0 |
| UNINVOICED_COLLECTION | 11 | 0.2245 | 1.0 | 0.3667 | 0 |

**Task B2 — operator performance scorecard (B5 from public records; score 0–100, per-metric score 1 = exact, 0 = error ≥ tolerance; B5 has no trained parameters, so its 'validation' row uses all public dev months)**

| split | rows | score | on-time | missed | shared ≤7 d | share lag | overcharge % | undercharge % | discrepant lines | weight bias % | order→lift |
|---|---|---|---|---|---|---|---|---|---|---|---|
| validation | 126 | 67.75 | 0.9998 | 0.9993 | 0.9998 | 0.9977 | 0.3309 | 0.3935 | 0.3548 | 0.0214 | 1.0 |

**Task C — operational decisions (context)**

| policy | split | cases | best share | acceptable share | mean regret € | impermissible |
|---|---|---|---|---|---|---|
| always_no_action | validation | 876 | 0.3961 | 0.6301 | 166.74 | 0.0 |
| naive_aggressive_saver | validation | 876 | 0.2295 | 0.5582 | 191.86 | 0.2717 |
| B3_rules | validation | 876 | 0.21 | 0.5811 | 150.36 | 0.1027 |
| B4_gradient_boosting | validation | 876 | 0.5205 | 0.7226 | 100.08 | 0.1347 |

B3 diagnostics (validation): verify_weight_sensor precision 0.1143, recall 0.4615; review_invoices precision 0.5321, recall 0.9312.

**Task C2 — operator and contract actions** (regret = best action set value − value of the chosen set, € per case)

| policy | split | cases | mean regret € | value captured | dispute P/R | request P/R | renegotiate P/R | tender P/R |
|---|---|---|---|---|---|---|---|---|
| no_action | dev | 207 | 1063.91 | 0.0 | None/0.0 | None/0.0 | None/0.0 | None/0.0 |
| act_on_everything | dev | 207 | 658.05 | 0.3815 | 0.1063/1.0 | 0.1111/1.0 | 0.2696/1.0 | None/0.0 |
| B6_rules | dev | 207 | 240.07 | 0.7743 | 0.3043/0.6364 | 1.0/0.2857 | 0.8571/0.4364 | 0.7647/0.4561 |
<!-- BASELINES:END -->

### Known failure cases (where teams can do better)

* **B1** uses device estimates when neither a ticket nor invoice tonnage exists. It inherits sensor drift and
  side-waste bias. Grade is inferred only from penalty and rejection lines, so grade B credit reductions are missed.
  It takes invoice tonnage at face value, so on unshared jobs a tonnage that differs from the weighbridge record looks correct. When the operator's
  ticket shows 0 kg net (an outdated stored tare larger than a small load) the reference €/t is NULL, but B1 falls
  back to the device estimate and reports a €/t (counted as "fabricated").
* **B2** only flags low-fill lifts on *scheduled* collections. On on-call devices it misses precautionary customer
  orders before weekends (published as CUSTOMER_REQUEST, S39) and lifts triggered by a fill sensor that reads
  falsely high while the mass is low (S40). It flags lifts as expensive even when hygiene or a contractual minimum
  explains them (watch `explained_flagged_as_anomaly`) and cannot tell drift from tare errors.
* **B3** ignores overflow risk when reducing frequency. That causes most of its impermissible choices and
  shows the hidden-cost traps (S35).
* **B4** has fixed thresholds, no calibration and no as-of feature engineering beyond B3's features.
* **B5** measures weight bias against the device's own estimate (sensor drift, calibration errors) and underestimates
  sharing lags (tickets shared after extraction are invisible).
* **B6** uses B1 masses for repricing (inheriting invoice tonnages that differ from the weighbridge record) and ignores operator
  billing quality when tendering.
* The naive aggressive saver shows that cutting lifts everywhere is harmful; *act on everything* shows that
  disputes and requests without evidence cost money.
