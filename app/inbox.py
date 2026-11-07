"""Fleet decision inbox for SMART Weight Check (app/app.py).

decisions(con, root, customer_id) returns one row per decision: the findings of one kind on one compactor,
with the euros they are about. The customer sees them ranked by € at stake and approves or rejects each one.
Approving only sends a question to the account manager: nothing is executed, so the € is "in question",
never "recovered".

Kinds (€ at stake, and where it comes from):
    wasted    trucks that came for nothing: stuck fill sensor, ordered when empty, access blocked
              € = wasted-trip fees (Task A contract calculation)
    resplit   two containers shared a truck and the net was split equally
              € = per-tonne charges on the wrong site (the customer's total is right)
    tonnage   invoiced tonnage differs from the device weight and no matching ticket backs it
              € = per-tonne charges in question (weight_rules.weight_check)
    invoice   invoice-line flags of the Task B baseline (duplicate, surcharge, old tariff, unmatched)
              € = amount of the lines in question
    early     lifts at low fill (Task B baseline + weight rules)          € = lift cost of those lifts
    cost      cost per tonne above the contract benchmark                  € = cost above benchmark × tonnes
    note      no € at stake: delays, contamination, device vs weighbridge, scale check

Evidence tags are written inline as [[observed]], [[simulated]], [[estimated]] or [[hypothetical]] right after
the number they belong to; app.py turns them into coloured dots. Synthetic data.
"""
from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "baselines", ROOT / "app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from weight_rules import premature_extra, scale_check, weight_check  # noqa: E402

LIFT = ("COMPLETED", "PARTIAL")
OBS, SIM, EST = "[[observed]]", "[[simulated]]", "[[estimated]]"
STUCK_FILL_PCT, STUCK_MAX_KG = 70, 100     # fill reading says "full" while the scale reads almost nothing
DEFAULT_FULL_PCT = 75                      # "full enough to lift" for devices without an on-call threshold (assumption)
COLUMNS = ["key", "device_id", "site", "kind", "title", "stake_eur", "stake_label", "lines", "action", "items", "first_at"]

# Plain-language finding per Task B family: (title, what a human should check). Neutral towards operators.
FAMILY = {
    "PREMATURE_UNJUSTIFIED": ("Lift may have been too early", "Check whether a schedule or on-call threshold change would avoid lifts at low fill."),
    "COST_PER_T_HIGH": ("Cost per tonne above the contract benchmark", "Check lift frequency and container size against how much material this site produces."),
    "DELAYED_COLLECTION": ("Lifts happened later than planned", "Check with the operator what caused the delay before changing anything."),
    "WEIGHT_DISCREPANCY": ("Device weight differs from the weighbridge", "Check the ticket first: side waste, combined loads, tare or sensor drift can all cause gaps."),
    "CONTAMINATION_VALUE_LOSS": ("Load graded as contaminated", "Check sorting at the site with the customer; the material credit drops with the grade."),
    "REJECTED_LOAD": ("Load rejected as too contaminated", "Check sorting at the site; a rejected load earns no credit and costs reprocessing."),
    "OUTDATED_TARIFF": ("Invoice may use an old tariff", "Compare the invoiced unit price with the contract version valid on the service date."),
    "DUPLICATE_LINE": ("Invoice line may be billed twice", "Compare with the job: the same job and line type appear twice."),
    "WRONG_SURCHARGE": ("Surcharge may not match the contract", "Compare fuel, km and remote surcharges with the contract."),
    "WEIGHT_BASIS_MISMATCH": ("Invoiced tonnage may not match the ticket", "Compare the invoiced quantity with the weighbridge ticket."),
    "UNMATCHED_LINE": ("Invoice line without a matching lift", "Check the job reference; it may be a typo rather than an error."),
    "MISSING_LINE": ("Expected invoice line is missing", "Check the invoice against the lift; this can also be an undercharge."),
    "UNINVOICED_COLLECTION": ("Lift was never invoiced", "Check with the operator; this is an undercharge, not a customer loss."),
}
INVOICE_FAMILIES = ("OUTDATED_TARIFF", "DUPLICATE_LINE", "WRONG_SURCHARGE", "WEIGHT_BASIS_MISMATCH", "UNMATCHED_LINE")


def plain(text: str) -> str:
    """Text without evidence markers (for tests and plain output)."""
    return re.sub(r"\s*\[\[\w+\]\]", "", text)


def eur(x: float) -> str:
    return f"−€{-x:,.0f}" if x < 0 else f"€{x:,.0f}"


def day(ts) -> str:
    return pd.Timestamp(ts).tz_convert("Europe/Helsinki").strftime("%-d %b")


def days(stamps) -> str:
    """'13, 14 and 15 Jul' for a list of timestamps (same month), else '13 Jul, 2 Aug'."""
    ts = sorted(pd.Timestamp(t).tz_convert("Europe/Helsinki") for t in stamps)
    if len({t.month for t in ts}) == 1:
        nums = [str(t.day) for t in ts]
        joined = nums[0] if len(nums) == 1 else ", ".join(nums[:-1]) + " and " + nums[-1]
        return f"{joined} {ts[0].strftime('%b')}"
    return ", ".join(t.strftime("%-d %b") for t in ts)


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def baselines(root: Path):
    """Task A (cost per lift) and Task B (flags) for the whole dataset, in memory."""
    import b2_rules_anomaly as b2

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pred, _, task_a = b2.run(Path(root))
    pred = pred.assign(family=pred.label_family.str.split(":").str[0])
    return task_a, pred


def decisions(con, root: Path, customer_id: str, task_a=None, pred=None, early=None) -> pd.DataFrame:
    """All decisions for one customer's fleet, ranked by € at stake (notes without € last)."""
    if task_a is None or pred is None:
        task_a, pred = baselines(root)
    if early is None:
        early = premature_extra(Path(root))

    dev = con.sql(f"""SELECT d.device_id, d.on_call_threshold_pct, s.site_name FROM devices d JOIN sites s USING (site_id)
                      WHERE d.customer_id = '{customer_id}' ORDER BY 1""").df()
    ids = tuple(dev.device_id)
    site = dev.set_index("device_id").site_name
    threshold = dev.set_index("device_id").on_call_threshold_pct.dropna().to_dict()
    ev = con.sql(f"""SELECT collection_id, device_id, status, trigger_type, wasted_trip_reason, scheduled_at, actual_at,
                            device_fill_pct_before, device_estimated_collected_kg
                     FROM collection_events WHERE device_id IN {ids}""").df()
    ev["when"] = ev.actual_at.fillna(ev.scheduled_at)
    evi = ev.set_index("collection_id")
    a = task_a[task_a.device_id.isin(ids)].set_index("collection_id")
    out: list[dict] = []

    def add(device_id, kind, title, stake, stake_label, lines, action, items, suffix=""):
        items = list(items)
        out.append({"key": f"{device_id}|{kind}{suffix}", "device_id": device_id, "site": site[device_id], "kind": kind,
                    "title": title, "stake_eur": round(float(stake), 2), "stake_label": stake_label, "lines": lines,
                    "action": action, "items": items, "first_at": evi.loc[items, "when"].min() if items else pd.NaT})

    # ---- wasted: trucks that came for nothing ----
    daily = con.sql(f"""SELECT device_id, date, fill_pct_max, mass_kg_max_valid FROM telemetry_daily_summary
                        WHERE device_id IN {ids}""").df().assign(date=lambda x: pd.to_datetime(x.date).dt.date)
    tele = daily.set_index(["device_id", "date"])
    wt = ev[ev.status == "WASTED_TRIP"].copy()
    for device_id, g in wt.groupby("device_id"):
        sensor, empty, blocked = [], [], []
        for _, r in g.iterrows():
            ordered = (device_id, pd.Timestamp(r.scheduled_at).date())      # what the reading said when it was ordered
            fill, kg = tele.loc[ordered, ["fill_pct_max", "mass_kg_max_valid"]] if ordered in tele.index else (None, None)
            if r.wasted_trip_reason == "ACCESS_BLOCKED":
                blocked.append(r)
            elif fill is not None and fill >= STUCK_FILL_PCT and pd.notna(kg) and kg <= STUCK_MAX_KG:
                sensor.append((r, fill, kg))
            else:
                empty.append((r, fill))
        lines, action = [], None
        if sensor:
            fills = [f for _, f, _ in sensor]
            kgs = [k for _, _, k in sensor]
            kg_txt = f"{min(kgs):,.0f}–{max(kgs):,.0f} kg" if min(kgs) != max(kgs) else f"{kgs[0]:,.0f} kg"
            lines.append(f"{days([r.when for r, _, _ in sensor])}: the fill reading said {max(fills):.0f} % {SIM}, "
                         f"but the scale read {kg_txt} {SIM}. The fill sensor may be stuck.")
            action = "Ask for a fill-sensor check before the next on-call order."
        if empty:
            fill_txt = ", ".join(f"{f:.0f} %" for _, f in empty if f is not None)
            lines.append(f"{days([r.when for r, _ in empty])}: nothing to collect {OBS}"
                         + (f"; the container was {fill_txt} full {SIM}." if fill_txt else "."))
            action = action or "Check with the site why lifts were ordered when the container was nearly empty."
        if blocked:
            lines.append(f"{days([r.when for r in blocked])}: the truck could not reach the container {OBS}.")
            action = action or "Agree access to the container on collection days with the site."
        fees = a.reindex(g.collection_id).penalties_eur.fillna(0).sum()
        lines.append(f"The operator did what was ordered and charged the contract's wasted-trip fee {OBS}.")
        add(device_id, "wasted", f"{plural(len(g), 'truck')} came for nothing", fees, "paid in wasted-trip fees", lines,
            action, g.collection_id)

    # ---- weight check per compactor: resplit, tonnage ----
    wcs = []
    for device_id in ids:
        wc = weight_check(con, device_id)
        if not wc.empty:
            wcs.append(wc.assign(device_id=device_id))
            note = scale_check(wc)
            if note:
                add(device_id, "note", "Check the device scale", 0, "", [f"{note} {SIM}"],
                    "Ask for a remote zero and span check before the next billing period.", [], suffix="|scale")
    wc = pd.concat(wcs, ignore_index=True) if wcs else pd.DataFrame(columns=["device_id", "result", "eur_at_stake"])
    split = wc[(wc.result == "explained: combined load") & (wc.eur_at_stake > 0)]
    for device_id, g in split.groupby("device_id"):
        lines = [f"{day(r.actual_at)}: invoiced {r.invoiced_kg / 1000:.2f} t {OBS}, the container held {r.device_kg:,.0f} kg {SIM}."
                 for r in g.itertuples()]
        lines.append("Two containers shared a truck and the net was split equally. Your total is right; this site's € per tonne is not.")
        add(device_id, "resplit", "Shared truck split equally" if len(g) == 1 else f"{len(g)} shared trucks split equally",
            g.eur_at_stake.sum(), "per-tonne charges on the wrong site", lines,
            "Re-split shared loads by container weight when costs are allocated between sites.", g.collection_id)
    review = wc[wc.result.str.startswith("review", na=False) & (wc.eur_at_stake > 0)]
    for device_id, g in review.groupby("device_id"):
        lines = []
        for r in g.itertuples():
            if pd.isna(r.ticket_kg):
                lines.append(f"{day(r.actual_at)}: invoice {r.invoiced_kg:,.0f} kg {OBS}, container {r.device_kg:,.0f} kg {SIM}, "
                             f"no weighbridge ticket shared {OBS}.")
            else:
                lines.append(f"{day(r.actual_at)}: invoice {r.invoiced_kg:,.0f} kg {OBS}, the operator's ticket {r.ticket_kg:,.0f} kg {OBS}.")
        add(device_id, "tonnage", "Invoiced tonnage needs a look", g.eur_at_stake.sum(), "per-tonne charges in question", lines,
            g.proposal.iloc[0], g.collection_id)

    # ---- Task B flags ----
    col = pred[(pred.entity_type == "collection") & pred.entity_id.isin(ev.collection_id)].rename(columns={"entity_id": "collection_id"})
    col = col.merge(ev[["collection_id", "device_id"]], on="collection_id")
    lines_db = con.sql(f"""SELECT l.invoice_line_id, l.line_type, l.amount_eur, c.collection_id, c.device_id
                           FROM invoice_lines l JOIN collection_events c USING (operator_job_ref)
                           WHERE c.device_id IN {ids}""").df()
    inv = pred[(pred.entity_type == "invoice_line") & pred.family.isin(INVOICE_FAMILIES)].merge(
        lines_db, left_on="entity_id", right_on="invoice_line_id")
    for device_id, g in inv.groupby("device_id"):
        g = g.drop_duplicates("invoice_line_id")
        lines = [f"{FAMILY[r.family][0]}: {r.line_type.replace('_', ' ').lower()} {eur(r.amount_eur)} {OBS}" for r in g.itertuples()]
        top = g.loc[g.amount_eur.abs().idxmax()]
        add(device_id, "invoice", f"{plural(len(g), 'invoice line')} to check", g.amount_eur.abs().sum(),
            "on invoice lines in question", lines, FAMILY[top.family][1], g.collection_id.unique())

    # early: Task B PREMATURE flags plus the weight rules, one decision per compactor
    pre = col[col.family == "PREMATURE_UNJUSTIFIED"][["collection_id", "device_id"]].assign(rule="baseline")
    ext = early[early.collection_id.isin(ev.collection_id)].merge(ev[["collection_id", "device_id"]], on="collection_id")
    ext = ext[~ext.collection_id.isin(pre.collection_id)]
    allearly = pd.concat([pre, ext], ignore_index=True)
    for device_id, g in allearly.groupby("device_id"):
        g = g.assign(when=g.collection_id.map(evi["when"])).sort_values("when")
        lines = []
        for r in g.itertuples():
            e = evi.loc[r.collection_id]
            if r.rule == "precautionary":
                lines.append(f"{day(e.when)}: customer-requested at {r.fill_pct:.0f} % full {SIM}, before a weekend or closed day {OBS}; "
                             f"it moved {r.kg:,.0f} kg {SIM}.")
            elif r.rule == "false-high fill":
                lines.append(f"{day(e.when)}: the fill reading said full, but the lift moved only {r.kg:,.0f} kg {SIM}, "
                             f"{r.share_of_full:.0%} of a typical full load.")
            else:
                lines.append(f"{day(e.when)}: lifted at {e.device_fill_pct_before:.0f} % full {SIM}.")
        # the material still has to be collected later, so only the empty part of each lift could have been avoided:
        # cost × (1 − fill ÷ the device's on-call threshold), or × (1 − share of a typical full load) when the fill lied
        cost = a.reindex(g.collection_id).collection_cost_eur.fillna(0).to_numpy()
        full = threshold.get(device_id, DEFAULT_FULL_PCT)
        filled = [min(r.share_of_full, 1) if r.rule == "false-high fill" else
                  min((r.fill_pct if r.rule == "precautionary" else evi.loc[r.collection_id, "device_fill_pct_before"]) / full, 1)
                  for r in g.itertuples()]
        avoidable = sum(c * (1 - f) for c, f in zip(cost, filled) if pd.notna(f))
        add(device_id, "early", f"{plural(len(g), 'lift')} at low fill", avoidable, "lift cost that waiting could have avoided",
            lines, "Check with the site why these were ordered before changing the on-call rule.", g.collection_id)

    # cost per tonne above the benchmark (lifts already counted as early lifts are left out, so no € is counted twice)
    hi = col[(col.family == "COST_PER_T_HIGH") & ~col.collection_id.isin(allearly.collection_id)]
    for device_id, g in hi.groupby("device_id"):
        c = a.reindex(g.collection_id)
        excess = (c.collection_cost_eur - c.benchmark_eur_per_t * c.mass_kg / 1000).clip(lower=0).sum()
        lines = [f"{day(evi.loc[cid, 'when'])}: {eur(r.collection_cost_eur_per_t)} per tonne vs benchmark {eur(r.benchmark_eur_per_t)} {EST}."
                 for cid, r in c.iterrows()]
        add(device_id, "cost", FAMILY["COST_PER_T_HIGH"][0], excess, "above the contract benchmark", lines,
            FAMILY["COST_PER_T_HIGH"][1], g.collection_id)

    # notes: findings without € at stake, one per compactor and family
    rest = col[~col.family.isin(["PREMATURE_UNJUSTIFIED", "COST_PER_T_HIGH"])]
    for (device_id, fam), g in rest.groupby(["device_id", "family"]):
        title, check = FAMILY.get(fam, (fam, ""))
        lines = []
        for cid in g.collection_id:
            e = evi.loc[cid]
            if fam == "DELAYED_COLLECTION" and pd.notna(e.actual_at):
                late = (e.actual_at - e.scheduled_at).total_seconds() / 3600
                lines.append(f"{day(e.when)}: lifted {late:,.0f} h after the planned time {OBS}." if late > 24 else
                             f"{day(e.when)}: the container reported full for 12 or more hours before the lift {SIM}.")
            elif fam == "WEIGHT_DISCREPANCY" and pd.notna(e.device_estimated_collected_kg):
                lines.append(f"{day(e.when)}: device {e.device_estimated_collected_kg:,.0f} kg {SIM}, the weighbridge differs {OBS}.")
            else:
                lines.append(f"{day(e.when)}: {title.lower()} {OBS}.")
        add(device_id, "note", title if len(g) == 1 else f"{title} ({len(g)}×)", 0, "", lines, check, g.collection_id,
            suffix=f"|{fam}")

    df = pd.DataFrame(out, columns=COLUMNS)
    df["has_stake"] = df.stake_eur > 0
    return df.sort_values(["has_stake", "stake_eur", "first_at"], ascending=[False, False, True]).reset_index(drop=True)
