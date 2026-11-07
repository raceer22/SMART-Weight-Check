"""Weight-based checks used by the demo app (app/app.py) and by notes/premature_rule.py.

Two checks that need the container's own weight, which a fill-level sensor cannot provide:

premature_extra(root)
    C05 rule on top of the Task B baseline. Flags on-call lifts that were probably too early:
      * precautionary: CUSTOMER_REQUEST at < 45 % fill just before a weekend or a closed day (scenario S39)
      * false-high fill: ON_CALL_ORDER whose collected weight is < 40 % of the device's own typical full load
        (median kg on its lifts that started >= 70 % full). The fill reading said "full", the weight says not (S40).

weight_check(con, device_id)
    "SMART Weight Check": per lift, compares the tonnage on the invoice with the device weight and the shared
    weighbridge ticket, explains known causes of differences neutrally (combined loads, side waste, missing
    tickets) and turns the rest into proposals. Tolerance = max(100 kg, 3.3 %), the dataset's accuracy target
    (docs/ASSUMPTIONS_AND_LIMITATIONS.md). The weighbridge stays the billing basis; the device is a check.

Synthetic data. Every output is a proposal that needs human approval.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "baselines"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PER_TONNE_LINES = ("PROCESSING", "HAUL_PER_TONNE", "MATERIAL_CREDIT", "REJECTION_REPROCESSING")
TOLERANCE_KG, TOLERANCE_REL = 100, 0.033       # dataset accuracy target: about +-100 kg on a 3 t load
TICKET_GAP_KG = 20                             # weighbridge resolution: invoice vs ticket must match to this


def premature_extra(root: Path) -> pd.DataFrame:
    """Extra PREMATURE_UNJUSTIFIED flags (C05). Columns: collection_id, rule, fill_pct, kg, share_of_full."""
    from b2_rules_anomaly import collection_features
    from europress_data.sdk import open_dataset

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        f = collection_features(Path(root))
    con = open_dataset(root)
    cal = con.sql("SELECT site_id, date, is_open FROM site_calendar").df()
    con.close()

    f["local_date"] = f.actual_at.dt.tz_convert("Europe/Helsinki").dt.date
    nxt = cal.assign(local_date=(pd.to_datetime(cal.date) - pd.Timedelta(days=1)).dt.date)  # row = the NEXT day
    f = f.merge(nxt[["site_id", "local_date", "is_open"]].rename(columns={"is_open": "next_day_open"}),
                on=["site_id", "local_date"], how="left")
    dow = pd.to_datetime(f.local_date).dt.dayofweek
    typical = (f[(f.status == "COMPLETED") & (f.device_fill_pct_before >= 70)]
               .groupby("device_id").device_estimated_collected_kg.median().rename("typical_full_kg"))
    f = f.merge(typical, on="device_id", how="left")
    kg = f.device_estimated_collected_kg.fillna(f.mass_kg)
    share = kg / f.typical_full_kg
    done = f.status.isin(["COMPLETED", "PARTIAL"])

    before_closed_day = (dow >= 4) | (f.next_day_open == False)  # noqa: E712  (NULL = unknown = not closed)
    precautionary = done & (f.collection_policy == "ON_CALL") & (f.trigger_type == "CUSTOMER_REQUEST") \
        & (f.device_fill_pct_before < 45) & before_closed_day
    false_high = done & (f.trigger_type == "ON_CALL_ORDER") & (share < 0.4)
    out = f.loc[precautionary | false_high, ["collection_id", "device_fill_pct_before"]].copy()
    out["rule"] = ["false-high fill" if fh else "precautionary" for fh in false_high[precautionary | false_high]]
    out["kg"] = kg[precautionary | false_high]
    out["share_of_full"] = share[precautionary | false_high]
    return out.rename(columns={"device_fill_pct_before": "fill_pct"}).reset_index(drop=True)


def weight_check(con, device_id: str) -> pd.DataFrame:
    """One row per completed lift of the device that has per-tonne invoice lines."""
    df = con.sql(f"""
        WITH t AS (
          SELECT operator_job_ref,
                 max(quantity) AS invoiced_t,
                 sum(amount_eur) AS per_t_amount_eur
          FROM invoice_lines WHERE line_type IN {PER_TONNE_LINES} GROUP BY 1),
        w AS (SELECT DISTINCT ON (operator_job_ref) operator_job_ref, allocated_net_kg, loads_on_vehicle, allocation_method
              FROM weighbridge_tickets ORDER BY operator_job_ref, published_at)
        SELECT c.collection_id, c.actual_at, c.driver_reported_side_waste AS side_waste,
               c.device_estimated_collected_kg AS device_kg, w.allocated_net_kg AS ticket_kg, w.loads_on_vehicle,
               t.invoiced_t * 1000 AS invoiced_kg, t.per_t_amount_eur
        FROM collection_events c JOIN t USING (operator_job_ref) LEFT JOIN w USING (operator_job_ref)
        WHERE c.device_id = '{device_id}' AND c.status IN ('COMPLETED', 'PARTIAL')
        ORDER BY c.actual_at""").df()
    if df.empty:
        return df
    df["diff_kg"] = df.invoiced_kg - df.device_kg
    df["tolerance_kg"] = (df.device_kg.abs() * TOLERANCE_REL).clip(lower=TOLERANCE_KG)
    eur_per_kg = df.per_t_amount_eur / df.invoiced_kg.where(df.invoiced_kg > 0)
    df["eur_at_stake"] = (df.diff_kg * eur_per_kg).round(2)      # > 0: invoice implies more than the device weighed

    def judge(r) -> tuple[str, str, str | None]:
        """(result, plain explanation, proposal or None). Neutral: a difference is not a fault.
        EUR at stake > 0 means the invoice works against the customer (more charge, or less credit)."""
        rate = r.per_t_amount_eur / r.invoiced_kg if r.invoiced_kg else float("nan")
        if pd.notna(r.ticket_kg) and abs(r.invoiced_kg - r.ticket_kg) > TICKET_GAP_KG:
            if (r.invoiced_kg - r.ticket_kg) * rate > 0:
                return ("review: invoice vs ticket",
                        f"The invoice says {r.invoiced_kg:,.0f} kg but the operator's own ticket says {r.ticket_kg:,.0f} kg.",
                        "Compare the invoiced tonnage with the weighbridge ticket; ask for a credit note if the ticket is right.")
            return ("in the customer's favour", f"The invoice uses {r.invoiced_kg:,.0f} kg, the ticket {r.ticket_kg:,.0f} kg.", None)
        if pd.isna(r.device_kg):
            return ("no device weight", "No valid device weight for this lift (no sensor, or a sensor fault).", None)
        if abs(r.diff_kg) <= r.tolerance_kg:
            return ("agrees", "The invoiced tonnage and the device weight agree within the tolerance.", None)
        if pd.notna(r.loads_on_vehicle) and r.loads_on_vehicle >= 2:
            return ("explained: combined load",
                    f"Two jobs were weighed together and the net was split equally. The device weighed {r.device_kg:,.0f} kg in "
                    "this container, so the customer's total is right but this site's € per tonne is not.",
                    "Re-split the combined load by device weight when allocating cost between sites.")
        if bool(r.side_waste) and r.diff_kg > 0:
            return ("explained: side waste",
                    "The driver also loaded loose waste next to the container, which the container scale cannot see.", None)
        if pd.isna(r.ticket_kg):
            if r.eur_at_stake > 0:
                return ("review: no ticket",
                        f"No weighbridge ticket was shared, and the invoice implies {abs(r.diff_kg):,.0f} kg "
                        f"{'more' if r.diff_kg > 0 else 'less'} than the device weighed.",
                        "Ask the operator for the weighbridge ticket before accepting the per-tonne lines.")
            return ("in the customer's favour", "No ticket shared; the invoice is in the customer's favour versus the device weight.", None)
        return ("device differs from ticket",
                f"The invoice matches the operator's ticket; the device weighed {r.diff_kg:+,.0f} kg differently.", None)

    df[["result", "explanation", "proposal"]] = df.apply(lambda r: pd.Series(judge(r)), axis=1)
    return df


def scale_check(df: pd.DataFrame) -> str | None:
    """One device-level proposal when the device repeatedly disagrees with matching invoice + ticket pairs.
    That points at the device scale (tare, drift, calibration), not at the operator."""
    if df.empty:
        return None
    off = df[df.result == "device differs from ticket"]
    single = df[df.ticket_kg.notna() & df.device_kg.notna() & ~(df.loads_on_vehicle >= 2) & ~df.side_waste.astype(bool)]
    if len(off) < 2 or len(off) < 0.25 * len(single):
        return None
    return (f"{len(off)} of {len(single)} single-load lifts differ from the operator's ticket by more than the tolerance "
            f"(median {off.diff_kg.median():+,.0f} kg). Check this device's scale: zero, tare and span against recent tickets.")
