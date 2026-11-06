# Quickstart for builders (15 minutes)

**Challenge:** *From smart device data to a stronger customer position in the waste value chain.* How can
trustworthy device data (precise operating status today, and weight in the future) give customers an
independent, explainable view of the waste services they buy, support decisions that a human approves, and
enable new Europress business models?

Europress is currently not a party to waste transport or treatment. Tariffs, processing fees and material
credits are agreed between the customer and the waste operator. All prices in this dataset are hypothetical.

## 0. Setup (2 min)

```bash
pip install numpy pandas pyarrow duckdb pyyaml scikit-learn   # or: pip install -e ".[dev]"
```

Unzip the quickstart pack. It contains `public/` with Parquet files and `public/csv/` with the same tables as CSV (all except the benchmark id lists).
**Everything is synthetic.** It holds no Europress customer data and no real prices.

## 1. Load (2 min)

```python
import sys; sys.path.insert(0, "src")            # if you use the source repo
from europress_data.sdk import open_dataset
con = open_dataset("data/quickstart/public")      # one DuckDB view per table (+ telemetry_dedup)
con.sql("SHOW TABLES").show()
con.sql("SELECT * FROM collection_events LIMIT 5").show()
```

Without the SDK, use pandas: `pd.read_parquet("public/operations/collection_events.parquet")`. Telemetry is
partitioned: `pd.read_parquet("public/telemetry/telemetry_hourly")`.

## 2. The five joins you need (3 min)

```sql
-- device → site → customer
SELECT * FROM devices JOIN sites USING (site_id) JOIN customers USING (customer_id);
-- collection → weighbridge (operator_job_ref is the ONLY shared key; many lifts have no published ticket)
SELECT * FROM collection_events c LEFT JOIN weighbridge_tickets w USING (operator_job_ref);
-- ticket → quality grade
SELECT * FROM weighbridge_tickets w LEFT JOIN quality_assessments q USING (ticket_id);
-- collection → invoice lines (watch for job-ref typos; fall back to contract + service_date)
SELECT * FROM collection_events c JOIN invoice_lines l USING (operator_job_ref);
-- collection → valid tariff version (local date!)
SELECT c.collection_id, v.* FROM collection_events c JOIN contract_versions v ON v.contract_id = c.contract_id
 AND CAST(timezone('Europe/Helsinki', coalesce(c.actual_at, c.scheduled_at)) AS DATE) >= v.effective_from
 AND (v.effective_to IS NULL OR CAST(timezone('Europe/Helsinki', coalesce(c.actual_at, c.scheduled_at)) AS DATE) < v.effective_to);
```

## 3. First useful analysis: cost per tonne with honest mass (5 min)

```bash
python examples/first_analysis.py data/quickstart/public
```

The script computes collection €/t per device with the reference economics engine. It reports where the mass
comes from (weighbridge, invoice or device) and leaves €/t **NULL** when the mass is unknown. It then compares
each device with its contract benchmark. Read the output table, and look for devices that are expensive
*and* low-fill, and check whether hygiene rules explain them.

## 4. Check yourself against the dev labels (3 min)

```bash
python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv
python -m europress_data.evaluate --task A --pred my_task_a.csv --labels data/quickstart/public/labels_dev --split validation
python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv
python -m europress_data.evaluate --task B --pred my_task_b.csv --labels data/quickstart/public/labels_dev --split validation
```

## 5. Operator scorecard and operator/contract actions (Tasks B2, C2)

```bash
python baselines/run_all.py quickstart          # includes B5 (scorecard) and B6 (operator actions)
python -m europress_data.evaluate --task B2 --pred my_scorecard.csv --labels data/quickstart/public/labels_dev --split all
python -m europress_data.evaluate --task C2 --pred my_actions.csv  --labels data/quickstart/public/labels_dev --split dev
```

`my_scorecard.csv`: `operator_id, region_code, month` plus any of the scorecard metrics (see `DATA_DICTIONARY.md →
labels_dev/operator_scorecard`). `my_actions.csv`: `case_id, actions` with a `;`-separated subset of the case's
`candidate_actions` (empty = no action). The valuation rules are in `ECONOMIC_MODEL.md` §7.

## 6. Business case with your own parameters (Task D)

```bash
cp configs/commercial_assumptions.yaml my_params.yaml        # fill in your prices, costs, adoption, realisation
python baselines/business_case.py quickstart --params my_params.yaml --out my_business_case
python baselines/business_case.py quickstart --params configs/business_case_example_params.yaml   # calculation example only
```

No prices are given: pricing and adoption assumptions are part of your answer.

## 7. Weighing concept (brief part 1)

```bash
python examples/weighing_accuracy_value.py data/quickstart/public --sigmas 0.5,1,1.5,3,5
```

Shows what a given weighing accuracy is worth for cost-per-tonne reporting and for verifying operator tonnage.

## Traps worth knowing

* `telemetry_hourly` is an **ingest log**. It has duplicates (same `message_id`), late buffered messages and
  gaps. Deduplicate it and order by `measured_at`.
* `mass_kg` can be NULL (fault or no sensor), slightly negative, drifted or spiked. Read `quality_flag` and
  `sensor_status`.
* A low-fill lift is not always waste. Biowaste has a 7-day hygiene limit, other streams have a maximum
  interval, and pre-closure lifts exist. These appear as explained labels in `labels_dev`.
* Weighbridge net can differ from the device for good reasons: side waste on the same truck, combined loads
  split 50/50, stored tares.
* `weight_reconciliation_status` / `invoice_match_status` in `collection_events` are computed at extraction
  time. The `as_of` view masks them as `UNKNOWN_AS_OF`.
* Decision cases: use only data known before `decision_at` (`open_dataset(root, as_of="YYYY-MM-DD")`).
  Some actions look cheap and are not.
* Most devices are **on call**. Unnecessary lifts on on-call devices hide behind `CUSTOMER_REQUEST` (precautionary
  orders before weekends) and behind a fill sensor that reads "full" while the mass stays low (bridging): compare
  fill with mass.
* Paper is a **chargeable** stream (no material credit). Only cardboard and plastics are credit-eligible.
* Quality grades are the operator's own assessment at its facility; the device does not measure quality.
* Weighbridge tickets and quality grades exist only when the operator shares them; some never do.
* Operators are fictional. A difference is not automatically the operator's fault: sensor drift, side waste on
  the same truck and combined loads also create differences.
* Every recommendation is a **proposal** for a human to approve.
