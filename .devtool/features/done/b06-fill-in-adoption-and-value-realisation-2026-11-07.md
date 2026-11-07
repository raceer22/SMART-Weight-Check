---
id: "b06-fill-in-adoption-and-value-realisation-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "3 · Europress business model"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T12:40:00.000Z"
completedAt: "2026-11-07T12:40:00.000Z"
labels: ["task-d"]
order: "b0g"
---
# B06 · Fill in adoption and value realisation

**Time:** ~20 min  ·  **Do first:** B03

**Why:** Not every customer will buy, and not every saving found is actually realised.

## Steps
1. Under `adoption:` set `adoption_share_of_eligible_pct` to e.g. `[10, 25, 40]`.
2. Set `purchase_condition_value_multiple` (e.g. `3` = customer buys only if they gain 3× the fee).
3. Under `value_realisation:` give each a number between 0 and 1 (e.g. `billing_review: 0.6`).

## Done when
- [x] All `null`s that we use are replaced with numbers + comments.

## Result
- Adoption 10/25/40 % of eligible, purchase rule value ≥ 3× fee. Realisation shares grounded in the dataset's published rules and simulated counterfactuals (over-servicing 0.35 from 30–39 % realised in `decision_outcomes`). Future models off in the main case.
