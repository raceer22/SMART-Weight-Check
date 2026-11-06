# Gap analysis of the v0 starter pack

Input inspected: `Europress_Since_AI_2026_Synthetic_Data_Pack_For_Approval.zip` (7 files, 320 KB):
`devices.csv` (50 rows), `daily_sensor_readings.csv` (4,500), `pickup_events.csv` (441),
`illustrative_contracts.csv` (10), `metadata.json`, `README.txt`, `EVENT_HANDOVER.txt`.
The original ZIP is not modified; it is kept only as reference input.

## What is worth keeping

- Explicit synthetic labelling, "not actual savings" language and the human-approval principle.
- The challenge flow: join → show data origin/quality → €/t with explicit zero/missing handling →
  approvable action → compare with a rules baseline → optional API mock.
- Material classes (cardboard, paper, plastics, mixed waste). (The v0 seed `20261023` remains the demo seed of the generator; the official v1.0.x packages use organiser-held seeds.)
- The quickstart scale (50 devices × 90 days) and a daily summary table shaped like
  `daily_sensor_readings.csv` (kept as a backwards-compatible view in the quickstart pack).

## Problems found (measured on the files, not assumed)

| # | Finding | Evidence | Consequence |
|---|---------|----------|-------------|
| 1 | Weight is a deterministic function of fill: `kg = fill × capacity × density(material) × (1 ± ~4 %)` | kg/m³ per material has std 1.5–5 around a fixed mean | Weight adds no information beyond fill level, which defeats the challenge premise ("what can weight data add?") |
| 2 | Densities are loose-material values (35–121 kg/m³) | e.g. cardboard 60.5 kg/m³ at 16 m³ | Compacted containers hold several times more; tonnages and €/t are off by ~3× |
| 3 | Pickup cost ignores mass and is driven by a per-event random distance | OLS fit `cost ≈ 121 + 2.14 × km`, mass coefficient ≈ 0; same device ranges 10–60 km | No tariff logic; route distance should be a site property |
| 4 | Benchmark is uninformative | 84 % of pickups exceed `target_pickup_eur_per_t` | A threshold rule flags almost everything; no false-positive structure |
| 5 | "Net material value" subtracts all transport from material value; mixed waste uses a negative "material value" instead of a gate fee | 95 % of pickups negative | Conflates customer cost, processing fee and recyclable credit |
| 6 | Contracts have no tariff structure or validity dates | 5 columns: benchmark + subscription hypothesis | Invoice reconstruction and contract-review tasks are impossible |
| 7 | No customers, sites, operators, weighbridge, invoices, maintenance, calendars, timestamps | date-only, 7 days/week identical behaviour | No reconciliation, no operator-data-access problem, no explanatory context |
| 8 | Labels are public features | `contamination_flag`, `value_discount_pct ∈ {0, 35}` | Leakage: the "anomaly" is given; discount is binary |
| 9 | No collection-policy variety | fill before pickup 45–100 %, no cancellations, delays, partial or wasted trips | Premature/delayed collection scenarios cannot be studied |
| 10 | Pickup-day semantics ambiguous | 440 fill drops occur on a day with no pickup id (drop shows the day after) | Easy to mis-join sensor and pickup data |
| 11 | Perfect regularity | exactly 10 devices per material, exactly 90 rows per device | Unrealistic and trivially separable |

## Architecture decision

Replace independent column sampling with a stateful, event-driven simulator, then derive all
public tables by observation models from the simulated physical/financial truth:

```
Organisation → Site (sector, calendar, region) → Device (capacity, compaction, sensor)
  → hourly material inflow (seasonality, weekday, holidays, campaigns, moisture, density)
  → container state (mass, compacted volume, overflow)  ← collection policy (fixed / on-call / hybrid)
  → collection events (delays, cancellations, partial, wasted trips)
  → weighbridge tickets (gross/tare/net, combined loads, sharing lag, unshared operators)
  → quality grading (contamination → grade → credit adjustment / rejection)
  → contract versions + monthly price index → expected charges (integer-cent reference model)
  → operator invoices (with injected, labelled discrepancies)
  → observed telemetry (noise, drift, calibration, offline, outages, latency, duplicates, out-of-order)
  → decision cases evaluated by counterfactual re-simulation with common random numbers
```

Private truth (simulator state, scenario labels, expected charges for the test period,
counterfactual outcomes, hold-out customers) is written to a separate directory that is never
packed into the public release.
