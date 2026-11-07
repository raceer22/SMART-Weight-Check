---
id: "b07-run-the-business-case-calculator-with-our-numb-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "3 · Europress business model"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T12:40:00.000Z"
completedAt: "2026-11-07T12:40:00.000Z"
labels: ["task-d", "python", "beginner"]
order: "b0h"
---
# B07 · Run the business-case calculator with our numbers

**Time:** ~10 min  ·  **Do first:** B04, B05, B06

**Why:** This turns our assumptions into revenue and profit numbers.

## Steps
1. Run `python baselines/business_case.py competition --params configs/our_params.yaml --out our_business_case`.
2. Open the files in `our_business_case/`.
3. Copy the key result (revenue, profit, payback) into FINDINGS.md.

## Done when
- [x] The output folder exists and key numbers are in FINDINGS.md.

## Help
- If it errors on a missing value, the message tells you which field to fill.

## Result
- `our_business_case/` written. Base case (€15, 25 %): revenue €11.0 k/year, year 1 −€5.4 k, then +€5.4 k/year, payback 2.0 years. Customer value: €332 k/year realisable on €5.19 M spend. FINDINGS.md → B07.
