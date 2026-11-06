"""What is a given weighing accuracy worth? (supports brief part 1, "Get the weight")

    python examples/weighing_accuracy_value.py data/competition/public [--sigmas 0.5,1,1.5,2.5,5,10] [--abs-kg 15]

For a candidate weighing concept with relative accuracy sigma (1 standard deviation, % of the load) and an
absolute floor, the script uses the operator weighbridge net of shared single-load tickets as the reference
mass and re-measures every load with your concept's error model. It reports:

  * the share of 2.5-3.5 t loads within +/-100 kg (the challenge's simulation target, about 95 %),
  * the precision of collection cost per tonne computed from the device weight,
  * how reliably a tonnage overbilling of +10 % on the invoice would be detected (flag when the invoice
    tonnage exceeds the device weight by more than 2 combined standard deviations), and the false-alarm rate
    on correct invoices,
  * for comparison, how the dataset's device estimates and operator weighbridge nets actually differ (both sides carry
    error: sensor faults, material added between readings, residuals, outdated stored vehicle tares).

All data are synthetic. The target of about 100 kg on a 3 t load is a challenge simulation target, not a
specification of any Europress weighing solution. The weighbridge itself has an error (about 12 kg, 20 kg
resolution), which is included in the comparison.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

WB_SIGMA_KG = 12.0          # weighbridge noise in this synthetic world (configs/assumptions.yaml -> operations)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("public", nargs="?", default="data/competition/public")
    ap.add_argument("--sigmas", default="0.5,1,1.5,2.5,5,10", help="relative 1-sigma accuracy in %% of the load")
    ap.add_argument("--abs-kg", type=float, default=15.0, help="absolute 1-sigma floor in kg")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    pub = Path(a.public)
    ce = pd.read_parquet(pub / "operations" / "collection_events.parquet")
    wb = pd.read_parquet(pub / "operations" / "weighbridge_tickets.parquet")
    one = wb[(wb.loads_on_vehicle == 1) & (wb.allocated_net_kg > 100)][["operator_job_ref", "allocated_net_kg"]]
    d = ce[ce.status == "COMPLETED"].merge(one, on="operator_job_ref")
    d = d[~d.driver_reported_side_waste.fillna(False).astype(bool)]
    m = d.allocated_net_kg.to_numpy(dtype=float)
    rng = np.random.default_rng(a.seed)
    rows = []
    for s_pct in [float(x) for x in a.sigmas.split(",")]:
        s = s_pct / 100
        sig = np.maximum(a.abs_kg, s * m)
        dev = m + rng.normal(0, 1, len(m)) * sig
        err = dev - m
        band = (m >= 2500) & (m <= 3500)
        sig_tot = np.sqrt(sig ** 2 + WB_SIGMA_KG ** 2)
        over = 1.10 * m                                    # invoice tonnage +10 %
        detect = (over - dev) > 2 * sig_tot
        false_alarm = (m - dev) > 2 * sig_tot
        cpt_err = np.abs(m / dev - 1)                       # relative error of EUR/t from the device weight
        rows.append({"concept_sigma_pct": s_pct, "loads": len(m),
                     "within_100kg_on_2.5-3.5t_loads": round(float((np.abs(err[band]) <= 100).mean()), 3) if band.any() else None,
                     "median_eur_per_t_error_pct": round(100 * float(np.median(cpt_err)), 2),
                     "p95_eur_per_t_error_pct": round(100 * float(np.quantile(cpt_err, 0.95)), 2),
                     "detects_+10pct_tonnage_overbilling": round(float(detect.mean()), 3),
                     "false_alarm_rate_on_correct_invoices": round(float(false_alarm.mean()), 4)})
    out = pd.DataFrame(rows)
    print("# Value of weighing accuracy (synthetic data; reference = shared single-load weighbridge tickets)\n")
    print(out.to_markdown(index=False))
    e = d.dropna(subset=["device_estimated_collected_kg"])
    rel = (e.device_estimated_collected_kg - e.allocated_net_kg) / e.allocated_net_kg
    b = e[(e.allocated_net_kg >= 2500) & (e.allocated_net_kg <= 3500)]
    print("\nReconciliation reality in this dataset: the device's own collected-mass estimate (reading before minus after the lift)"
          "\nvs the operator's weighbridge net. Both sides carry error: device noise and sensor faults, material added between"
          "\nreadings, residuals, and outdated stored vehicle tares at the weighbridge. Differences are not automatically anyone's fault:")
    print(f"  loads {len(e)}, median |difference| {100 * rel.abs().median():.2f} %, p95 |difference| {100 * rel.abs().quantile(0.95):.2f} %, "
          f"within 100 kg on 2.5-3.5 t loads {(np.abs(b.device_estimated_collected_kg - b.allocated_net_kg) <= 100).mean():.3f}")
    print("\nRead it as: which accuracy does a business use case really need? Verification of operator tonnage needs a "
          "much tighter error than cost-per-tonne reporting. Device weight is never a billing basis today.")


if __name__ == "__main__":
    main()
