"""SMART Weight View: the customer demo of "SMART Weight Check" (Epic 2, tasks C09–C14, plus the weight check).

Run from the repo root:
    python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv   # C01
    python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv         # C04
    streamlit run app/app.py

Sections: device picker · fill and weight charts · cost per tonne and weight source · weight check (invoiced
tonnes vs device weight vs weighbridge ticket) · proposals (Task B baseline flags + weight-based rules from
app/weight_rules.py), each one approved or rejected by a human.

Every number on the page carries an evidence tag (docs/BENCHMARK.md, rubric for D and E):
    observed      read straight from a record (collection event, weighbridge ticket, invoice line)
    simulated     from the SMART device (fill %, container mass); device weighing is a future scenario
    estimated     our calculation from records (cost per tonne, medians)
    hypothetical  an assumption; all tariffs in the dataset are hypothetical
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))
from europress_data.sdk import open_dataset  # noqa: E402
from weight_rules import premature_extra, scale_check, weight_check  # noqa: E402

DATA = ROOT / "data" / "quickstart" / "public"
TASK_A = ROOT / "my_task_a.csv"
TASK_B = ROOT / "my_task_b.csv"
STORY_DEVICE = "CMP-00046"  # the C03 storyline device
LIFT = ("COMPLETED", "PARTIAL")
SERIES = "#2a78d6"

MASS_SOURCE = {  # mass_basis -> (plain name, evidence tag)
    "WEIGHBRIDGE": ("weighbridge ticket", "observed"),
    "INVOICE_QUANTITY": ("invoice tonnage", "observed"),
    "DEVICE_ESTIMATE": ("device estimate", "simulated"),
}

# Plain-language proposal per anomaly family: (title, what a human should check). Neutral towards operators.
FAMILY = {
    "PREMATURE_UNJUSTIFIED": ("Lift may have been too early", "Check whether a schedule or on-call threshold change would avoid lifts at low fill."),
    "COST_PER_T_HIGH": ("Cost per tonne well above the contract benchmark", "Check lift frequency and container size against how much material this site produces."),
    "DELAYED_COLLECTION": ("Lift happened later than planned", "Check with the operator what caused the delay before changing anything."),
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

st.set_page_config(page_title="SMART Weight View", layout="wide")


# ---------- data ----------
@st.cache_resource
def dataset():
    return open_dataset(DATA)


@st.cache_data
def query(sql: str) -> pd.DataFrame:
    cur = dataset().cursor()  # a cursor shares the views but not the session settings
    cur.execute("SET TimeZone='UTC'")
    return cur.sql(sql).df()


@st.cache_data
def task_csv(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


@st.cache_data
def weight_table(device_id: str) -> pd.DataFrame:
    cur = dataset().cursor()
    cur.execute("SET TimeZone='UTC'")
    return weight_check(cur, device_id)


@st.cache_data
def early_lifts() -> pd.DataFrame:
    return premature_extra(DATA)


def eur(x: float) -> str:
    return f"€{x:,.0f}"


def local(ts) -> str:
    return pd.Timestamp(ts).tz_convert("Europe/Helsinki").strftime("%a %d %b %H:%M")


def tag(text: str) -> None:
    st.caption(text)


def line_chart(df: pd.DataFrame, field: str, title: str, unit: str, lifts: pd.DataFrame, y_max=None) -> alt.LayerChart:
    """One measure, one axis. Grey rules = lifts (dashed = trip without a lift). Hover shows the value."""
    base = alt.Chart(df).encode(x=alt.X("date:T", title=None))
    y = alt.Y(f"{field}:Q", title=title, scale=alt.Scale(domain=[0, y_max]) if y_max else alt.Undefined)
    line = base.mark_line(color=SERIES, strokeWidth=2, interpolate="monotone").encode(y=y)
    hover = alt.selection_point(nearest=True, on="pointerover", fields=["date"], empty=False, clear="pointerout")
    points = base.mark_point(size=60, filled=True, color=SERIES, stroke="white", strokeWidth=2).encode(
        y=y, opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="date"), alt.Tooltip(f"{field}:Q", title=f"{title} ({unit})", format=",.0f")],
    ).add_params(hover)
    crosshair = base.mark_rule(color="#9a9893", strokeWidth=1).encode(opacity=alt.condition(hover, alt.value(0.6), alt.value(0)))
    rules = alt.Chart(lifts).mark_rule(color="#8f8d86", strokeWidth=1).encode(
        x="actual_at:T", opacity=alt.value(0.55),
        strokeDash=alt.condition("datum.is_lift", alt.value([1, 0]), alt.value([4, 3])),
        tooltip=[alt.Tooltip("collection_id:N", title="collection"), alt.Tooltip("trigger_type:N", title="why"),
                 alt.Tooltip("status:N", title="status"), alt.Tooltip("actual_at:T", title="when", format="%d %b %H:%M")],
    )
    return alt.layer(rules, line, crosshair, points).properties(height=200)


# ---------- C09 · page ----------
st.title("SMART Weight View (synthetic data)")
st.write("One compactor, seen by the customer: how full it was, what it weighed, what each lift cost, "
         "and what might be worth a closer look.")

# ---------- C10 · device picker ----------
devices = query("""SELECT d.device_id, d.material_stream, d.collection_policy, d.on_call_threshold_pct, d.fixed_schedule_per_week,
                          d.container_volume_m3, d.has_weight_measurement, d.operator_id, s.site_name
                   FROM devices d JOIN sites s USING (site_id) ORDER BY 1""")
ids = devices.device_id
info = devices.set_index("device_id")
start = st.query_params.get("device", STORY_DEVICE)  # e.g. ?device=CMP-00042 opens that device directly
start = start if (ids == start).any() else STORY_DEVICE
device = st.selectbox("Device", ids, index=int((ids == start).idxmax()) if (ids == start).any() else 0,
                      format_func=lambda d: f"{d} · {info.loc[d, 'material_stream'].replace('_', ' ')}")
d = info.loc[device]
if d.collection_policy == "ON_CALL":
    policy = f"emptied on call at {d.on_call_threshold_pct:.0f} % fill"
elif pd.notna(d.fixed_schedule_per_week):
    policy = f"{d.collection_policy.replace('_', ' ').lower()}, {d.fixed_schedule_per_week:g} lifts a week"
else:
    policy = d.collection_policy.replace("_", " ").lower()
st.markdown(f"**{d.material_stream.replace('_', ' ').capitalize()}**, {d.container_volume_m3:g} m³ · {policy} · "
            f"operator {d.operator_id} · {d.site_name}")
tag("observed – devices and sites tables")

events = query(f"""SELECT collection_id, trigger_type, status, actual_at, scheduled_at, device_fill_pct_before,
                          device_estimated_collected_kg, operator_job_ref
                   FROM collection_events WHERE device_id = '{device}' ORDER BY actual_at""")

# ---------- C11 · fill and weight ----------
st.subheader("How full it was and what it weighed")
daily = query(f"""SELECT date, fill_pct_max, mass_kg_max_valid FROM telemetry_daily_summary
                  WHERE device_id = '{device}' ORDER BY date""").assign(date=lambda x: pd.to_datetime(x.date))
lifts = events.dropna(subset=["actual_at"])[["collection_id", "trigger_type", "status", "actual_at"]].assign(is_lift=lambda e: e.status.isin(LIFT))
st.altair_chart(line_chart(daily, "fill_pct_max", "fill %", "%", lifts, y_max=100), width="stretch")
if daily.mass_kg_max_valid.notna().any():
    st.altair_chart(line_chart(daily, "mass_kg_max_valid", "weight kg", "kg", lifts), width="stretch")
else:
    st.info("This device has no weight sensor, so there is no weight line. Cost per tonne below uses tickets or invoices only.")
tag("Device data – simulated (SMART device telemetry; device weighing is a future scenario in this dataset). "
    "Highest valid reading of each day. Grey lines = lifts, dashed = trip without a lift (hover for details).")

# ---------- C12 · cost per tonne and where the weight came from ----------
st.subheader("What it cost, and where the weight came from")
a = task_csv(TASK_A)
if a is None:
    st.warning("Cost data not found. Run this first, then reload:")
    st.code("python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv")
else:
    a = a[a.device_id == device]
    done = a[a.status.isin(LIFT)]
    known = done[done.mass_known.astype(bool) & (done.mass_kg > 0)]
    tonnes = known.mass_kg.sum() / 1000
    eur_t = known.collection_cost_eur.sum() / tonnes if tonnes else None
    bench = done.benchmark_eur_per_t.median()
    no_lift_fees = a[~a.status.isin(LIFT)].penalties_eur.sum()
    sources = done.mass_basis.map(lambda b: MASS_SOURCE.get(b, ("unknown", ""))[0]).value_counts()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Collection cost per tonne", f"{eur(eur_t)} /t" if eur_t else "unknown", border=True)
        tag("estimated – contract calculation, hypothetical tariffs" if eur_t else "no lift with a known weight: not filled in")
    with c2:
        if eur_t and pd.notna(bench):
            st.metric("vs contract benchmark", f"{eur_t / bench:.1f}×", help=f"benchmark {eur(bench)} per tonne", border=True)
            tag(f"estimated – benchmark {eur(bench)} /t")
        else:
            st.metric("vs contract benchmark", "unknown", border=True)
            tag("estimated – needs a known weight")
    with c3:
        st.metric("Lifts · tonnes moved", f"{len(done)} · {tonnes:.2f} t", border=True)
        tag("observed lifts; tonnes from the weight sources →")
    with c4:
        st.metric("Fees for trips without a lift", eur(no_lift_fees), border=True)
        tag("estimated – wasted trips and cancellations, contract calculation")

    st.markdown("**Weight source of the lifts:** " + " · ".join(f"{name} {n}" for name, n in sources.items()))
    tag("observed – weighbridge ticket and invoice tonnage; simulated – device estimate. "
        "A lift without any weight source shows “unknown” and gets no € per tonne.")

    table = a.merge(events[["collection_id", "trigger_type", "device_fill_pct_before"]], on="collection_id", how="left")
    table = table.sort_values("service_date")
    src = table.mass_basis.map(lambda b: MASS_SOURCE.get(b, ("unknown" if b != "NOT_A_LIFT" else "no lift", "")))
    lift_rows = table.status.isin(LIFT)
    per_t = table.collection_cost_eur_per_t.where(lift_rows & table.mass_known.astype(bool))
    shown = pd.DataFrame({
        "date": pd.to_datetime(table.service_date).dt.strftime("%d %b"),
        "why": table.trigger_type.str.replace("_", " ").str.lower(),
        "status": table.status.str.replace("_", " ").str.lower(),
        "fill before %": table.device_fill_pct_before.map(lambda x: f"{x:.0f} %" if pd.notna(x) else "–"),
        "kg": table.mass_kg.where(lift_rows).map(lambda x: f"{x:,.0f}" if pd.notna(x) else "–"),
        "weight source": [f"{n} ({t})" if t else n for n, t in src],
        "lift cost €": table.collection_cost_eur.where(lift_rows).map(lambda x: f"€{x:,.2f}" if pd.notna(x) else "–"),
        "other fees €": table.penalties_eur.round(2),
        "€ per tonne": [f"{x:,.0f}" if pd.notna(x) else ("unknown" if lift else "–") for x, lift in zip(per_t, lift_rows)],
    })
    st.dataframe(shown, hide_index=True, column_config={
        "fill before %": st.column_config.TextColumn(help="simulated – device fill the hour before the lift"),
        "kg": st.column_config.TextColumn(help="from the weight source in the next column"),
        "lift cost €": st.column_config.TextColumn(help="estimated – contract calculation (Task A baseline)"),
        "other fees €": st.column_config.NumberColumn(help="estimated – wasted-trip and cancellation fees", format="€%.2f"),
        "€ per tonne": st.column_config.TextColumn(help="estimated – lift cost ÷ tonnes; unknown weight is never filled in"),
    })
    tag("Every lift: fill before = simulated · kg = observed or simulated (see weight source) · € = estimated, hypothetical tariffs")

# ---------- Weight check: invoiced tonnes vs device weight vs weighbridge ticket ----------
st.subheader("Weight check: does the invoiced tonnage match what the container weighed?")
st.markdown("The operator's weighbridge stays the billing basis. The device weight is the customer's own, independent check.")
wc = weight_table(device)
scale_note = scale_check(wc)
if wc.empty:
    st.info("This device's invoices have no per-tonne lines: its contract bills per lift and per km. "
            "The weight still shows the real € per tonne above, but there is no tonnage on the invoice to check.")
else:
    review = wc.result.str.startswith("review")
    explained = wc.result.str.startswith("explained")
    checked = wc.device_kg.notna()
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Lifts with per-tonne lines", f"{len(wc)}", border=True)
        tag(f"observed – invoice lines; {int(checked.sum())} with a device weight (simulated)")
    with k2:
        st.metric("Agree within tolerance", f"{int((wc.result == 'agrees').sum())}", border=True)
        tag("tolerance max(100 kg, 3.3 %) – hypothetical, the dataset's accuracy target")
    with k3:
        st.metric("Explained differences", f"{int(explained.sum())}", border=True)
        tag("combined loads split equally, side waste – observed from the ticket and driver report")
    with k4:
        st.metric("To review", f"{int(review.sum())}", border=True)
        stake = wc.eur_at_stake.where(review & (wc.eur_at_stake > 0)).sum()
        tag(f"estimated – {eur(stake)} of per-tonne charges at stake" if review.any() else "nothing to review")
    shown = pd.DataFrame({
        "date": wc.actual_at.dt.tz_convert("Europe/Helsinki").dt.strftime("%d %b"),
        "lift": wc.collection_id,
        "device kg": wc.device_kg.map(lambda x: f"{x:,.0f}" if pd.notna(x) else "–"),
        "ticket kg": wc.ticket_kg.map(lambda x: f"{x:,.0f}" if pd.notna(x) else "not shared"),
        "invoiced kg": wc.invoiced_kg.map(lambda x: f"{x:,.0f}"),
        "invoice − device kg": wc.diff_kg.map(lambda x: f"{x:+,.0f}" if pd.notna(x) else "–"),
        "€ at stake": wc.eur_at_stake.map(lambda x: f"{x:+,.2f}" if pd.notna(x) else "–"),
        "result": wc.result,
        "why": wc.explanation,
    })
    st.dataframe(shown, hide_index=True, height=min(36 * (len(shown) + 1) + 4, 640), column_config={
        "why": st.column_config.TextColumn(width="large"),
        "device kg": st.column_config.TextColumn(help="simulated – container mass before minus after the lift"),
        "ticket kg": st.column_config.TextColumn(help="observed – operator weighbridge ticket, when shared"),
        "invoiced kg": st.column_config.TextColumn(help="observed – tonnage on the per-tonne invoice lines"),
        "€ at stake": st.column_config.TextColumn(help="estimated – difference × the invoice's own € per kg; "
                                                  "positive = the invoice works against the customer"),
    })
    tag("A difference is a question, not a verdict: combined loads, side waste, tares and the device's own calibration "
        "all cause differences that are nobody's fault.")
if scale_note:
    st.warning(f"**Device scale check suggested.** {scale_note}")

# ---------- C13 · flagged issues as proposals ----------
st.subheader("Proposals")
st.markdown("**Proposals. A human must approve each one.**")
when = events.set_index("collection_id").actual_at.fillna(events.set_index("collection_id").scheduled_at)
ev = events.set_index("collection_id")
props = []  # one dict per proposal: key, lift, what, why, check, source

b = task_csv(TASK_B)
if b is None:
    st.warning("Baseline flags not found, so only the weight-based proposals are shown. Run this first, then reload:")
    st.code("python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv")
else:
    lines = query(f"""SELECT l.invoice_line_id, l.line_type, l.amount_eur, c.collection_id FROM invoice_lines l
                      JOIN collection_events c USING (operator_job_ref) WHERE c.device_id = '{device}'""")
    col_flags = b[(b.entity_type == "collection") & b.entity_id.isin(events.collection_id)].assign(collection_id=lambda x: x.entity_id)
    line_flags = b[b.entity_type == "invoice_line"].merge(lines, left_on="entity_id", right_on="invoice_line_id")
    flags = pd.concat([col_flags, line_flags], ignore_index=True)
    flags["family"] = flags.label_family.str.split(":").str[0]
    wb = query(f"""SELECT c.collection_id, w.allocated_net_kg FROM collection_events c
                   JOIN weighbridge_tickets w USING (operator_job_ref) WHERE c.device_id = '{device}'""").drop_duplicates("collection_id").set_index("collection_id")
    cost = a.set_index("collection_id") if a is not None else pd.DataFrame()

    def why(r) -> str:
        e = ev.loc[r.collection_id] if r.collection_id in ev.index else None
        if r.family == "WEIGHT_DISCREPANCY" and e is not None and r.collection_id in wb.index:
            return (f"Device {e.device_estimated_collected_kg:,.0f} kg (simulated) vs weighbridge "
                    f"{wb.loc[r.collection_id, 'allocated_net_kg']:,.0f} kg (observed).")
        if r.family == "DELAYED_COLLECTION" and e is not None and pd.notna(e.actual_at):
            late = (e.actual_at - e.scheduled_at).total_seconds() / 3600
            if late > 24:
                return (f"Planned {local(e.scheduled_at)}, lifted {local(e.actual_at)} Finnish time, "
                        f"{late:,.0f} h later (observed).")
            return "The container reported FULL for 12 or more of the 72 hours before the lift (simulated)."
        if r.family == "PREMATURE_UNJUSTIFIED" and e is not None:
            return f"Lifted at {e.device_fill_pct_before:.0f} % fill (simulated)."
        if r.family == "COST_PER_T_HIGH" and r.collection_id in cost.index:
            c = cost.loc[r.collection_id]
            return f"{eur(c.collection_cost_eur_per_t)} per tonne vs benchmark {eur(c.benchmark_eur_per_t)} (estimated)."
        if pd.notna(r.get("line_type")):
            return f"Invoice line {r.line_type.replace('_', ' ').lower()}, {eur(r.amount_eur)} (observed)."
        return "Flagged by the rule-based check."

    for _, r in flags.iterrows():
        title, check = FAMILY.get(r.family, (r.family, ""))
        props.append({"key": f"{r.entity_id}|{r.family}", "lift": r.collection_id, "what": title, "why": why(r),
                      "check": check, "source": "baseline rule (Task B)"})

# weight-based rules (app/weight_rules.py): early lifts the fill reading cannot see, and the weight check
flagged_early = {p["lift"] for p in props if p["what"] == FAMILY["PREMATURE_UNJUSTIFIED"][0]}
for _, r in early_lifts()[lambda x: x.collection_id.isin(events.collection_id)].iterrows():
    if r.collection_id in flagged_early:
        continue
    e = ev.loc[r.collection_id]
    if r.rule == "precautionary":
        why_text = (f"Customer-requested lift at {r.fill_pct:.0f} % fill on {local(e.actual_at)}, just before a weekend or a closed day "
                    f"(simulated fill, observed calendar); it moved {r.kg:,.0f} kg.")
    else:
        why_text = (f"The fill reading said full, but the lift moved only {r.kg:,.0f} kg, {r.share_of_full:.0%} of this device's "
                    "typical full load (simulated). Only the weight shows this.")
    props.append({"key": f"{r.collection_id}|EARLY|{r.rule}", "lift": r.collection_id, "what": FAMILY["PREMATURE_UNJUSTIFIED"][0],
                  "why": why_text, "check": "Check the reason for the order with the site before changing the on-call rule.",
                  "source": f"weight rule: {r.rule}"})
for _, r in wc[wc.proposal.notna()].iterrows() if not wc.empty else []:
    props.append({"key": f"{r.collection_id}|WEIGHT|{r.result}", "lift": r.collection_id,
                  "what": "Re-split a combined load" if r.result.startswith("explained") else "Invoiced tonnage needs a look",
                  "why": r.explanation, "check": r.proposal, "source": "weight check"})
if scale_note:
    props.append({"key": f"{device}|SCALE", "lift": "whole device", "what": "Check the device scale", "why": scale_note,
                  "check": "Maintenance visit or remote zero/span check before the next billing period.", "source": "weight check"})

P = pd.DataFrame(props, columns=["key", "lift", "what", "why", "check", "source"])
if P.empty:
    st.info("No proposals for this device.")
else:
    P["when"] = P.lift.map(when)
    P = P.sort_values("when", na_position="last").reset_index(drop=True)
    st.dataframe(P[["lift", "what", "why", "check", "source"]].rename(columns={"check": "check before acting"}), hide_index=True)
    tag("estimated – rule-based flags (Task B baseline) and weight-based rules (app/weight_rules.py). "
        "A flag is a question, not a verdict.")

    decisions = st.session_state.setdefault("decisions", {})
    FIRST = 8

    def card(r) -> None:
        key = f"{device}|{r.key}"
        with st.container(border=True):
            left, right = st.columns([5, 2], vertical_alignment="center")
            with left:
                st.markdown(f"**{r.what}** · {r.lift}")
                st.caption(f"{r.why} {r.check}")
            with right:
                state = decisions.get(key)
                if state is None:
                    ok_col, no_col = st.columns(2)
                    if ok_col.button("Approve", key=f"ok-{key}", icon=":material/check:"):
                        decisions[key] = "approved"; st.rerun()
                    if no_col.button("Reject", key=f"no-{key}"):
                        decisions[key] = "rejected"; st.rerun()
                else:
                    (st.success if state == "approved" else st.info)(f"{state.capitalize()} (demo)")
                    if st.button("Undo", key=f"undo-{key}", type="tertiary"):
                        decisions.pop(key); st.rerun()

    for _, r in P.head(FIRST).iterrows():
        card(r)
    if len(P) > FIRST:
        with st.expander(f"Show {len(P) - FIRST} more proposals"):
            for _, r in P.iloc[FIRST:].iterrows():
                card(r)
    st.caption("Approve sends the proposal to the account manager (demo only, nothing is executed). Every decision can be undone.")

# ---------- C14 · footer ----------
st.divider()
st.caption("**All data is synthetic. Not Europress data.** Evidence tags: *observed* = read from a record · "
           "*simulated* = SMART device data · *estimated* = our calculation · *hypothetical* = an assumption "
           "(all tariffs are hypothetical customer–operator prices).")
