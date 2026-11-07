---
id: "b04-fill-in-pricing-in-our-params-yaml-2026-11-07"
status: "done"
priority: "medium"
assignee: null
epic: "3 · Europress business model"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-07T12:40:00.000Z"
completedAt: "2026-11-07T12:40:00.000Z"
labels: ["task-d"]
order: "b0e"
---
# B04 · Fill in pricing in our_params.yaml

**Time:** ~20 min  ·  **Do first:** B03

**Why:** Prices are part of our answer, and we must justify them.

## Steps
1. Under `pricing:` set `price_per_device_month_eur` to 3 values, e.g. `[15, 30, 50]`.
2. Next to it write a `#` comment: why these numbers? (e.g. “≈10 % of the overspend found in C02”).

## Done when
- [x] Pricing filled in with a justification comment.

## Result
- Prices 10 / 15 / 25 € per device-month, from the realisable value per device-month (25th/50th/75th percentile €20/€36/€72) and a price sweep (€15 maximises fee revenue under the 3× purchase rule). Outcome-based alternative: 20 % of verified savings.
