# Progress — Epic 2 · Customer weight view

*Updated 2026-11-07*

**Status:** 12 of 14 tasks are done.
- C08 (sketch) needs the team's agreement.
- C09 (empty Streamlit page) works but is not committed and pushed yet.

- **Results:** [FINDINGS.md](FINDINGS.md) → `## Customer value`
- **Run the demo:**
  ```
  pip install -e ".[app]"
  python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv
  python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv
  streamlit run app/app.py
  ```
- **Reproduce the rest:** `python notes/scorecard.py`, `python notes/punctuality.py`, `python notes/premature_rule.py data/quickstart/public my_task_b.csv`.

## Before starting
- Streamlit was installed into `.venv`. It is now listed as the `app` extra in `pyproject.toml`.
- The `my_*.csv` files are gitignored, so each laptop has to create them with the commands above. The app tells you which command to run if one is missing.

## Task by task

### C01 · Cost calculator (Task A)
- The baseline is exact to the cent on every cost category in the validation split (74 events).
- It never reports € per tonne where the weight is unknown.

### C02 · Top 10 € per tonne
- Six of the ten lift at a median fill below 50 %.
- Quickstart has no biowaste, so the 7-day hygiene rule explains none of them.
- Most devices have only 2–9 lifts, so the ranking is noisy.

### C03 · Story device: CMP-00046 (cardboard, on call, OP-A)
- **July:** the fill reading stuck at 88 % while the scale showed about 0 kg. This led to 4 wasted trips costing €346.
- **September:** three customer-requested lifts ran at 6–25 % full, at €387–2,279 per tonne against a €110 benchmark.
- Every number in the story is tagged.
- The operator is not blamed. The wasted trips came from the device.

### C04 · Anomaly baseline (Task B)
- Macro F1 is 0.856.
- The weakest family is **PREMATURE_UNJUSTIFIED** (F1 0.25, 1 of 7 found).

### C05 · Premature lifts
- The baseline only looks at scheduled lifts.
- It misses precautionary customer orders before weekends and orders triggered by a falsely high fill reading. In the second case only the weight shows the truth.
- Three examples are written up.
- The rule idea in `notes/premature_rule.py` raises F1 from 0.72 to 0.86 on competition validation. It does not change the baseline.

### C06 · Operator scorecard (Task B2)
- `notes/scorecard.py` writes `my_scorecard.csv`.
- It scores 78.3 / 100. The weakest metric is weight bias.

### C07 · Punctuality chart
- `notes/punctuality.png`: OP-E 71 %, OP-A 69 %, OP-B 55 %, OP-C 39 % on time.
- On time means within ±2 h of the scheduled time.
- The wording is neutral.

### C08 · Sketch (**not done: needs the team**)
- `notes/customer_screen_sketch.png` is a wireframe drawn from an SVG, not a paper photo.
- It has every element the task asks for, plus the lift table.
- Two teammates still have to look at it and agree.

### C09 · Empty Streamlit page (**not done: commit and push**)
- `app/app.py` opens in the browser. I checked it with Streamlit's test runner and a headless Firefox screenshot.
- Nothing is committed, as in Epic 1.

### C10–C14 · Demo app
- **Device picker:** opens on CMP-00046.
- **Charts:** fill and weight, each with its own axis, plus lift markers and a hover tooltip.
- **Cost:** € per tonne, benchmark ratio, and the weight source of every lift. Unknown weight shows as “unknown”.
- **Proposals:** baseline flags with Approve, Reject and Undo.
- **Tags:** an evidence tag on every number.
- **Footer:** “All data is synthetic. Not Europress data.”
- **Tested:** all 50 devices load without errors. The 3 devices without a weight sensor fall back to tickets and invoices.

### Changes from the task text
- **C11 caption:** says “simulated”, not “observed”. Device weighing is a simulated future scenario.
- **C11 weight line:** uses the daily maximum instead of the last reading, so fill and weight line up on lift days.

## Task board
- C01–C07 and C10–C14 are marked done, with their boxes ticked, and moved into `.devtool/features/done/`.
- C08 and C09 stay in backlog. C09's "page opens" box is ticked.
- The epic's user story stays in backlog until C08 and C09 are closed.

## Next steps
1. Team looks at the sketch and agrees on it (C08).
2. Commit and push the Epic 1 and Epic 2 work (C09).
3. Decide whether the C05 rule goes into our Task B submission and the app.

---

# Progress — Epic 1 · Understand the weight data

*Updated 2026-11-07*

**Status:** 12 of 13 tasks are done. U12 (accuracy target) is written up as a proposal and needs a team decision.

- **Results:** [FINDINGS.md](FINDINGS.md)
- **Reproduce:** `python notes/explore.py` reruns every query and chart. U10 is `python examples/weighing_accuracy_value.py data/competition/public`.

## Before starting

- U01–U03 were marked done on the board, but `FINDINGS.md` was an empty template and `notes/explore.py` didn't exist. All three were redone.
- matplotlib was installed into `.venv` for U05/U06. It is **not** listed in `pyproject.toml`, so anyone setting up fresh needs `pip install matplotlib`.

## Task by task

### U01 · List the tables
- Created `notes/explore.py` as the task describes and ran `SHOW TABLES` on the quickstart data.
- There are **35 tables/views**. They are listed in FINDINGS by group (reference, telemetry, operations, finance, labels, benchmark), with row counts for the main ones.

### U02 · Explain `collection_events`
- Printed 5 rows and read each column's definition in `docs/DATA_DICTIONARY.md`.
- Wrote one line per column with a real example value.
- Top-5 columns for weight:
  - `device_mass_kg_before`
  - `device_mass_kg_after`
  - `device_estimated_collected_kg`
  - `operator_job_ref` (the link to weighbridge tickets and invoices)
  - `driver_reported_side_waste`
- **Important:** the dictionary says device weighing is a simulated "future scenario", not something deployed today. The pitch must not claim it exists.

### U03 · Explain `telemetry_daily_summary`
- Same method: a 15-row column table, with the four columns from the task hint in bold.

### U04 · Count devices per waste stream

| Stream | Devices |
|---|---|
| Cardboard | 15 |
| Mixed waste | 14 |
| Plastic film | 11 |
| Mixed plastic | 9 |
| Paper | 1 |

- 47 of the 50 devices have a weight sensor.
- 36 devices handle material that can earn a credit.

### U05 / U06 · Plot fill and weight for one device
- Picked **CMP-00001**: mixed waste, has a weight sensor, about 99 % of its data present.
- Charts:
  - `notes/fill.png` shows the saw-tooth pattern.
  - `notes/mass.png` shows the weight.
  - `notes/fill_mass.png` (bonus) has both lines on one chart with the collections marked.
- Fill and weight move together (correlation 0.99).
- In early September this container sat full for 44 hours. The collection that followed is the biggest gap in the U09 comparison.
- **To do:** U05 asks for the chart to be posted in the team chat. The box is ticked, but it hasn't been posted yet.

### U07 · Find duplicate messages
- The hourly log has 106,751 rows but only 106,422 unique messages, so **329 are duplicates**.
- The cleaned `telemetry_dedup` view has exactly the unique count. Use it for all counts and sums.

### U08 · Count missing and bad weight readings
Counted on `telemetry_dedup`:
- 85.5 % of readings are flagged VALID.
- 7,243 have no weight value (no sensor, or sensor fault).
- 5,188 are negative weights. 51 of these are flagged as spikes rather than negative readings, and some are as low as −2,500 kg.

### U09 · Compare device weight with the weighbridge
Ran the task's join, added `diff_kg`, then grouped all 294 matched rows by cause:

| Case | What happens |
|---|---|
| Normal single load | Device is within about 4 % of the truck scale (median gap 45 kg) and reads slightly low. |
| Side waste | Device reads about 300 kg low on average. Loose overflow loaded next to the container goes on the truck but never on the container scale. |
| Combined loads | Gaps of about 50 %. Two jobs are weighed together and the total is split equally, so the truck-scale figure for each job is wrong, not the device. |

### U10 · Run the accuracy-value script
- Ran it on the competition data and copied the table into FINDINGS.
- The ~95 % target sat between two default rows, so I reran with finer steps. The ~95 % row is **σ ≈ 1.75 % of the load** (94.8 % within ±100 kg). It is highlighted in the table.
- Results move by 1–2 points between runs, so treat them as approximate.
- For comparison, the dataset's current device estimates get only **68.5 %** of loads within ±100 kg.

### U11 · Research 3 ways to weigh a compactor
Web research, comparison table in FINDINGS with sources:

| Idea | Rough cost | Easy retrofit? | Expected accuracy |
|---|---|---|---|
| Load cells under the container | Medium | Yes | About 1 % (my estimate from general load-cell specs; no retrofit test data found) |
| Hydraulic pressure on the truck's lift arm | Per truck | Yes, but on the hauler's fleet | About 1 % of the whole truck's weight, so worse on the load itself |
| Bolt-on strain gauges on the frame | Cheap | Yes | 3–5 % |

All accuracy figures are vendor claims or from patents, not independent tests on compactors.

### U12 · Pick our accuracy target (**not done: needs a team decision**)
- Proposal written in FINDINGS:
  - Concept: load cells under the container.
  - Target: σ = 1.5 % of the load.
  - What it lets the customer check: about 95 % of invoices that overcharge tonnage by 10 % get caught, with about 1 % false alarms.
- The task says the team chooses the concept, so it stays in backlog. It is listed under Open questions in FINDINGS.

### U13 · 5-sentence summary
- At the top of FINDINGS.md. It covers what the device measures, how reliable it is, how it compares with the truck scale, the main data traps, and why it matters.

## Task board
- U04–U11 and U13 are marked done with their boxes ticked and moved into `.devtool/features/done/`.
- U03's box was ticked. It had been left unchecked even though the task was marked done.
- U12 stays in backlog.
- Nothing is committed yet.

## Next steps
1. Team decides the U12 concept and accuracy target.
2. Post `notes/fill.png` in the team chat (U05).
3. Add matplotlib to `pyproject.toml`.
