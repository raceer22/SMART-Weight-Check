# Data generation methodology

The generator simulates a synthetic world first and only then derives the published tables through
explicit observation models. No published column is sampled on its own.

## 1. Determinism and scale

* Every entity has its own random stream: `SeedSequence([seed, hash(stream), hash(entity)])` in `rng.py`.
  Results therefore do not depend on chunk size, worker count or processing order. A test proves that
  `chunk_devices = 7` and `= 60` produce the same logical tables.
* Devices are simulated per organisation chunk (`chunk_devices`). Telemetry and truth are written straight
  to month partitions, and the other tables are staged and then routed with DuckDB. No profile holds the whole
  dataset in memory.
* Fixed seed, configuration and generator version give identical data, which a test checks with a content
  hash. The manifest records `config_hash`, `generator_version` and a SHA-256 checksum for every file.
* **Official packages use organiser-held seeds** (`--seed-file`). Their public manifest shows the seed as
  `UNDISCLOSED`, a SHA-256 commitment of it, and a configuration hash without the seed; only the private
  manifest holds the seed. This was added after the Europress review found that the public generator plus a
  public seed would have reproduced the private evaluation data. A test checks the protection.

## 2. World (`world.py`)

| Entity | Generation |
|---|---|
| Customers | Heavy-tailed fleet sizes (46 % single-site, up to 20 sites). 85 % are single-sector. All names are generated (`Fictional <Sector> Customer nnnn`) |
| Sites | Sector, region (real Finnish regions, weighted), municipality, billable round-trip km (lognormal around the regional median), outdoor staging (35 %) |
| Streams | Each sector has a probability per material stream (e.g. a grocery store has cardboard 100 %, biowaste 65 %) and a lognormal median daily kg |
| Devices | One compactor per site stream. Container volume is chosen so that the time to fill is about 9 days (lognormal), 12 % are oversized, and the volume options depend on material. Equipment class is a Europress machine type: COMBI (compactor and container joined, emptied as one unit; all biowaste) or DUO (stationary compactor, detachable container; all mixed plastic); no model-specific data |
| Sensors | Future scenario: 8 % of devices have no weight measurement, the rest a simulated integrated sensor (normal state about 1.5 % total error: reading noise max(15 kg, 1.4 %) plus installation calibration gain sd 0.4 %, offset sd 6 kg). Install dates are synthetic |
| Policies | ON_CALL 78 %, FIXED_SCHEDULE 12 %, HYBRID 10 % (Europress review: mostly on call). Fixed frequencies come from the customer's mis-estimate of demand (lognormal σ = 0.32) planned for 70 % fill, with a minimum frequency from the material's maximum interval |
| Operators | Five fictional haulers with overlapping regions, weighbridge sharing probability (0–97 %), sharing lag (minutes to 45 days), invoice error propensity, punctuality (`on_time_factor`) and missed-visit propensity (`missed_factor`). 22 % of vehicles have an outdated stored tare (S20); 45 % of weighings use the stored tare. Treatment facilities are operator-side data and are not published |
| Contracts | One per device, between the customer and the operator (Europress is not a party). Pricing model is FIXED_PER_LIFT, PER_TONNE, HYBRID or HYBRID_MIN. Only cardboard and plastics are credit-eligible; 80 % of their contracts have a credit share. Paper, mixed waste and biowaste are chargeable (processing fee per tonne). Annual indexation on 1 January, and 18 % get a mid-period amendment |
| Price index | Credit-eligible streams only. Mean-reverting monthly log random walk per material, with a cardboard value collapse (S05) and a film price spike (S06). Mixed plastics can go negative |
| Calendars | Finnish public holidays (Easter computed), sector opening days and hours, holiday modes (closed, reduced or peak), manufacturing summer shutdowns, and planned closures (S11) |

## 3. Physical state machine (`simulate.py`)

For each device-hour *h*:

1. **Generation**: `daily_kg = base × season[month] × weekday[dow] × site activity × AR(1) lognormal noise
   × campaign multipliers × holiday peaks`. Generation is zero on closed days. Daily mass is spread over
   opening hours with a sector profile, then turned into input events: `n ~ Poisson(mu / event_kg)`, and the
   mass is a sum of Gamma-distributed loads.
2. **Moisture (S28)**: rain-intensity proxy per region and day × outdoor staging → extra water mass (up to +35 %)
   for cardboard and paper. Water raises mass and density and raises the downgrade risk.
3. **Density**: device mean density × daily lognormal noise × (1 + 0.6 × moisture) × mix effects. Recyclables
   mis-sorted into mixed waste lower its density (S30). A material mix change or a compaction-setting change
   shifts density (S29).
4. **Compaction**: the compacted loose volume `W = Σ kg/ρ` maps to container volume through
   `V = C/c·(√(1+2cW/C) − 1)`, so the container compresses more as it fills (compressibility *c* by material).
   Fill = V / C.
5. **Capacity**: once `V = C`, further input becomes **side waste** (overflow). Inflow during downtime
   (breakdowns, maintenance) also becomes side waste.
6. **Collections** (event loop):
   * FIXED_SCHEDULE has booked weekday slots. Public holidays move to the next business day. Some customers
     cancel lifts during planned closures and others forget, which produces empty lifts.
   * ON_CALL orders when the *observed* fill estimate crosses the threshold (only while telemetry is online;
     isolated message drops and value rounding are not modelled in the policy's view). The order
     is served after a Poisson business-day lead time. The maximum-interval rule forces an order.
   * HYBRID books more often and skips a slot when the observed fill 26 h before is below the skip threshold.
   * In every policy, the customer calls an ad-hoc emergency lift once the container has been full for 6–30 h.
     Customers also request pre-closure and occasional ad-hoc lifts.
   * On-call devices: some customers order "to be safe" before weekends and holidays although the trigger has
     not fired (S39, published as CUSTOMER_REQUEST), and fill sensors can read falsely high for 1–4 days because
     of bridging or an obstruction (S40), which triggers orders while the true fill and mass are low.
   * Each candidate event can be cancelled, missed by the operator (and rescheduled), become a wasted trip
     (blocked access, or nothing to collect below 3 % fill), be delayed (mixture distribution, with worse delays
     during operator delay episodes, S02) or be partial (residual 10–40 %; frozen biowaste in winter, S22).
   * A completed lift removes `(1 − r)` of the container mass. The driver also loads side waste with
     probability 0.85, so it goes on the same truck and onto the same weighbridge ticket.
7. **Conservation**: `Σ inflow = Σ collected + Σ side collected + end container mass + end side stock` holds per
   device to machine precision. The validator checks it, as a release blocker.

## 4. Observation models (`telemetry.py`, `operator_records.py`)

The model keeps five layers of information separate:

| Layer | Where | Example |
|---|---|---|
| 1. Simulator ground truth | `private_evaluation/truth/*` | `true_container_mass_kg`, `true_contamination` |
| 2. Assumed sensor measurement | `telemetry_hourly.mass_kg`, `fill_pct` | gain/offset drift, noise, 5 kg resolution |
| 3. Estimates / inferences | `device_estimated_collected_kg`, daily summary, naive reconciliation status | before − after |
| 4. Operator weighbridge data | `weighbridge_tickets` (shared and published subset only) | gross/tare/net, 20 kg resolution |
| 5. Missing / unavailable | NULLs with flags, unpublished tickets, unshared operators | `quality_flag = SENSOR_FAULT` |

* **Weight**: `obs = true × gain(t) + offset(t) + σ(m) × z`, with σ = max(18 kg, 2.5 % × m) and ×3 when
  DEGRADED. The reading is rounded to 5 kg. Drift (S13) is a gain trend the device does not report.
  Calibration errors (S15) start at a maintenance visit. A replacement (S14) brings a new sensor id and new
  calibration. Faults (S12) set mass to NULL. Spikes are flagged 60 % of the time. Values can be slightly
  negative near empty (flagged).
* **Fill**: `obs = true × gain_dev + bias_dev + AR(1) noise (σ 3.5 pp)`. The device-level gain has σ 7 %, and
  5 % of devices are miscalibrated by ±20 %. Bias depends on material spring-back. Policies act on this
  observed value, so fill-sensor error changes when collections happen.
* **Delivery**: per-device connectivity outages (Poisson, lognormal duration). Messages are buffered and
  flushed out of order after an outage (S18). Data older than 72 h is lost. There are also isolated drops,
  lognormal latency with a 1 % tail and latency episodes (S16), and duplicates with an identical payload
  (0.3 %, or 6 % in bursts, S17).
* **Weighbridge**: vehicle tare is WEIGHED or STORED, and stored tares can be outdated by 180–420 kg (S20).
  About 4 % of tickets (competition profile) are combined loads split 50/50. Sharing is operator-specific, with extra-late publication
  (S19). Tickets published after the extraction time are not public. 0.6 % of jobs have no ticket, so the
  contract default weight is billed.
* **Quality**: operator contamination estimate = truth + N(0, 2 pp). Thresholds A ≤ 4 %, B ≤ 9 %, C ≤ 18 %,
  else R. Wet cardboard is downgraded one grade with probability 0.5.
* **Invoices**: expected lines (section 3 of the economic model), then labelled perturbations per operator
  error rate: outdated tariff after a version change, duplicate lines, missing credit or lift lines, wrong fuel
  rate / doubled km / non-applicable remote surcharge, weight-basis mismatch (+8–25 %), uninvoiced jobs,
  phantom jobs, and job-reference typos. Typos are a matching challenge, not a monetary error. Invoice totals
  always equal the sum of their lines. Customer disputes are recorded, and some disputes are unfounded.

## 5. Labels and ground truth (`labels.py`, `decisions.py`)

* Labels are derived from simulator truth and the operator's own records (e.g. the grade the operator applied),
  not from customer-side features. Several families are therefore close to one public column (REJECTED_LOAD and
  CONTAMINATION_VALUE_LOSS for published grades, WRONG_SURCHARGE, MISSING_LINE). They test reconstruction and
  explanation rather than detection, and they are reported separately in the benchmark. Each label has a
  severity (borderline or clear) and `is_actionable`. Explained cases carry `is_actionable = False` with an explanation code, for example
  EARLY_JUSTIFIED (hygiene minimum frequency, maximum-interval rule, pre-closure, decommissioning) or
  COST_PER_T_HIGH explained by a contractual minimum or a partial lift. These are false-positive traps.
* Decision cases are evaluated by **counterfactual re-simulation with paired common random numbers**:
  * Operational randomness (delays, cancellations, misses, partial lifts, lead times, slot jitter) comes from a
    counter-based generator keyed by *(purpose, event time)*. The same physical event gets the same draw under
    every action, whatever else happens in the simulation.
  * Every action is simulated over `decision_replications` paired replications (quickstart 8, competition 6,
    enterprise 2). Replication 0 reuses the realised history's stream. All replications share the same inflow,
    density, contamination, sensor and connectivity arrays.
  * Simulations start from the actual physical state at `decision_at`: container mass, compacted volume, side
    stock and last lift. **Orders in flight, pending reschedules and ad-hoc state are not carried over**, so
    NO_ACTION can differ from the realised history.
  * Leftover mass at the horizon is valued at a **contract-based marginal cost per kg**: fixed lift fees spread
    over a typical 80 % load, plus per-tonne fees, minus the credit at the decision month's index.
  * An action is permissible only if it adds no maximum-interval violations and at most 24 extra overflow hours
    while the site is open (both as replication means).
  * An action is *acceptable* if it is within max(25 €, 3 %) of the best permissible action, or within two paired
    standard errors of it.
  * In a stability check on the quickstart, the best action under one set of replications was acceptable under an
    independent set in 89.5 % of cases, and the acceptable sets overlapped in 94 %. Treat `best_action` as a noisy
    target and score on acceptability and regret.
  * Counterfactual costs use true collected mass and a grade from true contamination. They omit weighbridge
    noise, the combined-load split and the wet downgrade. They are an internal yardstick, not a billing replica.

## 6. Splits and leakage control

* **Customer hold-out**: about 10 % of devices, chosen as whole customers (no customer larger than 8 % of the
  fleet). All their data lives only in `private_evaluation/holdout_full`. A time-truncated copy
  (`holdout_asof_<cutoff>`) supports leak-free Task C scoring.
* **Time**: labels are split into train / validation / test periods (see the manifest). Public packages
  contain only train and validation labels. Test-period labels and all truth are private.
* Public feature tables contain no `true_*` or scenario columns. The weighbridge public table has no
  `collection_id`, so matching must go through `operator_job_ref` as it would in reality.

## 7. Limitations

See `ASSUMPTIONS_AND_LIMITATIONS.md`. In short, the distributions are plausible by construction but are **not
calibrated to measured Europress or operator data**. The world is a teaching and benchmarking instrument, not
a forecast.
