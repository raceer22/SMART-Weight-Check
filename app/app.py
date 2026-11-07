"""SMART Weight Check: the customer's decision inbox (Epic 2, tasks C09–C14, the weight check, and the fleet inbox).

Run from the repo root:
    streamlit run app/app.py
    (deep link to one compactor: http://localhost:8501/?device=CMP-00042)

One customer (ORG-0004: 25 compactors at 8 sites, the customer of the story compactors CMP-00046, -42 and -47)
sees every finding of the quarter as a decision, ranked by the euros it is about (app/inbox.py). Approve sends a
question to the account manager, Reject dismisses it, and both can be undone. "Why?" opens the evidence: that
compactor's fill and weight, its cost per tonne, and the lifts the decision is about.

Every number carries an evidence dot (docs/BENCHMARK.md, rubric for D and E):
    observed      read straight from a record (collection event, weighbridge ticket, invoice line)
    simulated     from the SMART device (fill %, container mass); device weighing is a future scenario
    estimated     our calculation from records (cost per tonne, € at stake)
    hypothetical  an assumption; all tariffs in the dataset are hypothetical
Look: Europress brand cyan and Poppins (.streamlit/config.toml), no Europress logo. Synthetic data.
"""
import html
import re
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))
from europress_data.sdk import open_dataset  # noqa: E402
from inbox import baselines, decisions, eur  # noqa: E402
from weight_rules import premature_extra, weight_check  # noqa: E402

DATA = ROOT / "data" / "quickstart" / "public"
CUSTOMER = "ORG-0004"
LIFT = ("COMPLETED", "PARTIAL")
TOP = 5
BRAND, LINE, ACTION, AMBER, GREY = "#03b4e0", "#0099c7", "#0077a6", "#e09b00", "#9aa7b0"
TAGS = {"observed": "read from a record", "simulated": "SMART device data", "estimated": "our calculation",
        "hypothetical": "an assumption"}
ICON = {"wasted": "local_shipping", "resplit": "call_split", "tonnage": "scale", "invoice": "receipt_long",
        "early": "hourglass_bottom", "cost": "trending_up", "note": "info"}
MASS_SOURCE = {"WEIGHBRIDGE": ("weighbridge ticket", "observed"), "INVOICE_QUANTITY": ("invoice tonnage", "observed"),
               "DEVICE_ESTIMATE": ("device estimate", "simulated")}

st.set_page_config(page_title="SMART Weight Check", page_icon=":material/scale:", layout="wide")

st.markdown(f"""<style>
[data-testid="stMainBlockContainer"], .block-container {{ max-width: 1160px; padding-top: 2.2rem; padding-bottom: 4rem; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.hero {{ position: relative; overflow: hidden; border-radius: 24px; padding: 30px 34px 26px; margin-bottom: 18px;
        background: radial-gradient(circle at 92% 8%, rgba(3,180,224,.30), transparent 42%),
                    linear-gradient(135deg, #ffffff 0%, #e6f6fc 100%);
        border: 1px solid #d3e6ee; box-shadow: 0 10px 30px rgba(0,119,166,.08); }}
.eyebrow {{ font-size: .78rem; font-weight: 600; letter-spacing: .16em; text-transform: uppercase; color: {ACTION}; }}
.eyebrow b {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: {BRAND}; margin-right: 8px; }}
.concept {{ position: absolute; top: 26px; right: 30px; font-size: .74rem; color: #5b6670; background: rgba(255,255,255,.8);
           border: 1px solid #d3e6ee; border-radius: 999px; padding: 4px 12px; }}
.hero h1 {{ font-size: 2.35rem; line-height: 1.15; margin: 10px 0 6px; padding: 0; color: #141618; font-weight: 700; }}
.hero p {{ margin: 0; color: #5b6670; font-size: .95rem; }}
.tiles {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 22px; }}
.tile {{ background: #fff; border: 1px solid #d3e6ee; border-radius: 16px; padding: 14px 18px; }}
.tile .label {{ font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: #5b6670; font-weight: 600; }}
.tile .value {{ font-size: 2rem; font-weight: 700; color: #141618; line-height: 1.25; }}
.tile.sent {{ background: linear-gradient(135deg, {ACTION}, {LINE}); border: none; }}
.tile.sent .label, .tile.sent .value, .tile.sent .note {{ color: #fff; }}
.tile .note {{ font-size: .78rem; color: #5b6670; }}
.chip {{ display: inline-block; margin-left: 8px; font-size: .8rem; font-weight: 600; padding: 2px 9px; border-radius: 999px;
        background: rgba(255,255,255,.25); vertical-align: middle; }}
.section {{ font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; color: #5b6670; font-weight: 600;
           margin: 22px 0 6px; }}
[class*="st-key-card_"] {{ background: #fff; border: 1px solid #d3e6ee; border-radius: 18px; padding: 18px 22px 14px;
                         box-shadow: 0 4px 16px rgba(20,22,24,.04); }}
/* Streamlit pulls every markdown block up by 1rem to hide the last paragraph's margin; our HTML blocks have none */
[data-testid="stMarkdownContainer"]:has(> :is(.hero, .ctitle, .stake, .action, .lines, .legend, .evidence-head, .section)) {{ margin-bottom: 0 !important; }}
[class*="st-key-card_"][class*="_approved"] {{ background: #e9f7fc; border-color: #9fd9ee; padding: 12px 22px; box-shadow: none; }}
[class*="st-key-card_"][class*="_rejected"] {{ background: #f5f7f8; border-color: #e3e8eb; padding: 12px 22px; box-shadow: none; opacity: .75; }}
.ctitle {{ font-size: 1.12rem; font-weight: 600; color: #141618; line-height: 1.3; }}
.where {{ font-size: .82rem; color: #5b6670; }}
.stake {{ font-size: 1.7rem; font-weight: 700; color: {ACTION}; line-height: 1.1; text-align: right; }}
.stake-label {{ font-size: .74rem; color: #5b6670; text-align: right; line-height: 1.25; }}
.lines {{ margin: 2px 0 0; padding-left: 1.1rem; color: #303133; font-size: .92rem; }}
.lines li {{ margin: 2px 0; }}
.action {{ font-size: .86rem; color: #303133; }}
.action b {{ color: {ACTION}; font-weight: 600; }}
.ev {{ display: inline-block; width: .55em; height: .55em; border-radius: 50%; margin: 0 .15em .12em .3em; vertical-align: middle; }}
.tile .ev {{ width: .3em; height: .3em; margin-left: .25em; }}
.stake-label .ev {{ width: .45em; height: .45em; }}
.ev-observed {{ background: #303133; }}
.ev-simulated {{ background: {BRAND}; }}
.ev-estimated {{ background: {AMBER}; }}
.ev-hypothetical {{ background: transparent; border: 1.5px solid #5b6670; }}
.legend {{ font-size: .8rem; color: #5b6670; }}
.legend span.item {{ margin-right: 14px; white-space: nowrap; }}
.evidence-head {{ font-size: .95rem; font-weight: 600; color: #141618; margin-top: 10px; padding-top: 12px; border-top: 1px solid #e3eef3; }}
div[data-testid="stMetric"] {{ background: #f7fbfd; }}
@media (max-width: 760px) {{ .tiles {{ grid-template-columns: 1fr; }} .concept {{ position: static; display: inline-block; margin-bottom: 8px; }}
  .hero h1 {{ font-size: 1.7rem; }} }}
</style>""", unsafe_allow_html=True)


# ---------- data ----------
@st.cache_resource
def dataset():
    return open_dataset(DATA)


def cursor():
    cur = dataset().cursor()  # a cursor shares the views but not the session settings
    cur.execute("SET TimeZone='UTC'")
    return cur


@st.cache_data
def query(sql: str) -> pd.DataFrame:
    return cursor().sql(sql).df()


@st.cache_data(show_spinner="Weighing and checking every lift…")
def fleet() -> tuple[pd.DataFrame, pd.DataFrame]:
    task_a, pred = baselines(DATA)
    return decisions(cursor(), DATA, CUSTOMER, task_a, pred, premature_extra(DATA)), task_a


@st.cache_data
def weight_table(device_id: str) -> pd.DataFrame:
    return weight_check(cursor(), device_id)


def dots(text: str) -> str:
    """Escape text and turn [[tag]] markers into evidence dots with a tooltip."""
    return re.sub(r"\s*\[\[(\w+)\]\]", lambda m: f'<span class="ev ev-{m[1]}" title="{m[1]}: {TAGS[m[1]]}"></span>',
                  html.escape(text))


def dot(tag: str) -> str:
    return dots(f"[[{tag}]]")


def line_chart(df, field, title, unit, lifts, y_max=None) -> alt.LayerChart:
    """One measure, one axis. Grey rules = lifts (dashed = trip without a lift); amber = the lifts this decision is about."""
    base = alt.Chart(df).encode(x=alt.X("date:T", title=None, axis=alt.Axis(format="%-d %b", grid=False)))
    y = alt.Y(f"{field}:Q", title=title, scale=alt.Scale(domain=[0, y_max]) if y_max else alt.Undefined,
              axis=alt.Axis(gridColor="#e6eef2", tickCount=4))
    area = base.mark_area(color=BRAND, opacity=0.10, interpolate="monotone").encode(y=y)
    line = base.mark_line(color=LINE, strokeWidth=2.5, interpolate="monotone").encode(y=y)
    hover = alt.selection_point(nearest=True, on="pointerover", fields=["date"], empty=False, clear="pointerout")
    points = base.mark_point(size=70, filled=True, color=LINE, stroke="white", strokeWidth=2).encode(
        y=y, opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="date"), alt.Tooltip(f"{field}:Q", title=f"{title} ({unit})", format=",.0f")],
    ).add_params(hover)
    rules = alt.Chart(lifts).mark_rule(strokeWidth=1.5).encode(
        x="actual_at:T",
        color=alt.condition("datum.hl", alt.value(AMBER), alt.value(GREY)),
        opacity=alt.condition("datum.hl", alt.value(0.95), alt.value(0.45)),
        strokeDash=alt.condition("datum.is_lift", alt.value([1, 0]), alt.value([4, 3])),
        tooltip=[alt.Tooltip("collection_id:N", title="collection"), alt.Tooltip("trigger_type:N", title="why"),
                 alt.Tooltip("status:N", title="status"), alt.Tooltip("actual_at:T", title="when", format="%d %b %H:%M")],
    )
    return (alt.layer(rules, area, line, points).properties(height=170)
            .configure(background="transparent").configure_view(stroke=None).configure_axis(labelFont="Poppins", titleFont="Poppins", labelColor="#5b6670",
                                                        titleColor="#5b6670", domainColor="#d3e6ee", tickColor="#d3e6ee"))


# ---------- the fleet and its decisions ----------
D, TASK_A = fleet()
devices = query(f"""SELECT d.device_id, d.material_stream, d.collection_policy, d.on_call_threshold_pct, d.fixed_schedule_per_week,
                           d.container_volume_m3, d.operator_id, s.site_name, s.site_id
                    FROM devices d JOIN sites s USING (site_id) WHERE d.customer_id = '{CUSTOMER}' ORDER BY 1""")
info = devices.set_index("device_id")
customer = query(f"SELECT customer_name FROM customers WHERE customer_id = '{CUSTOMER}'").customer_name.iloc[0]
lifts_done = int(query(f"""SELECT count(*) AS n FROM collection_events c JOIN devices d USING (device_id)
                           WHERE d.customer_id = '{CUSTOMER}' AND c.status IN {LIFT}""").n.iloc[0])
period = query("SELECT min(date) AS a, max(date) AS b FROM telemetry_daily_summary")
period = f"{pd.Timestamp(period.a.iloc[0]):%B}–{pd.Timestamp(period.b.iloc[0]):%B %Y}"

state = st.session_state
state.setdefault("decided", {})
state.setdefault("why", None)
decided: dict = state.decided


def decide(key: str, verdict: str, stake: float) -> None:
    decided[key] = verdict
    if state.why == key:
        state.why = None
    if verdict == "approved":
        state.flash = f"Sent to your account manager · {eur(stake)}" if stake else "Sent to your account manager"


def undo(key: str) -> None:
    decided.pop(key, None)


def toggle_why(key: str) -> None:
    state.why = None if state.why == key else key


# filter: the whole fleet, or one compactor (?device=CMP-00042)
choices = ["all"] + list(devices.device_id)
start = st.query_params.get("device", "all")
pick_label = {"all": f"All {len(devices)} compactors"} | {
    d: f"{d} · {info.loc[d, 'material_stream'].replace('_', ' ')} · {info.loc[d, 'site_name'].split(' (')[0]}" for d in devices.device_id}
view = D if start == "all" or start not in info.index else D[D.device_id == start]

open_ = view[~view.key.isin(decided)]
money = open_[open_.has_stake]
approved = view[view.key.map(decided.get) == "approved"]
sent = approved.stake_eur.sum()
last = state.pop("flash", None)

# ---------- hero ----------
waiting = len(money)
headline = (f"{waiting} decision{'s are' if waiting != 1 else ' is'} waiting for you." if waiting
            else "All done. Nothing is waiting for you.")
chip = f'<span class="chip">+{html.escape(last.split("· ")[-1])}</span>' if last and "€" in last else ""
st.markdown(f"""
<section class="hero">
  <div class="concept">A concept for Europress SMART compactors · synthetic data</div>
  <div class="eyebrow"><b></b>SMART Weight Check</div>
  <h1>{headline}</h1>
  <p>{html.escape(customer)} · {len(devices)} compactors at {devices.site_id.nunique()} sites · {period}.
     The biggest come first. Approving sends a question to your account manager; nothing changes until a person acts.</p>
  <div class="tiles">
    <div class="tile"><div class="label">€ in question</div><div class="value">{eur(money.stake_eur.sum())}{dot('estimated')}</div>
      <div class="note">on open decisions</div></div>
    <div class="tile sent"><div class="label">€ sent for review</div><div class="value">{eur(sent)}{chip}</div>
      <div class="note">{len(approved)} approved · every decision can be undone</div></div>
    <div class="tile"><div class="label">Lifts weighed and checked</div><div class="value">{lifts_done}{dot('simulated')}</div>
      <div class="note">against the invoice, the ticket and the contract</div></div>
  </div>
</section>""", unsafe_allow_html=True)
if last:
    st.toast(last, icon=":material/send:")

pick = st.selectbox("Show", choices, index=choices.index(start) if start in choices else 0,
                    format_func=pick_label.get, label_visibility="collapsed")
if pick != start:
    st.query_params["device"] = pick
    st.rerun()


# ---------- evidence ----------
def evidence(r) -> None:
    device = r.device_id
    d = info.loc[device]
    if d.collection_policy == "ON_CALL":
        policy = f"emptied on call at {d.on_call_threshold_pct:.0f} % fill"
    elif pd.notna(d.fixed_schedule_per_week):
        policy = f"{d.collection_policy.replace('_', ' ').lower()}, {d.fixed_schedule_per_week:g} lifts a week"
    else:
        policy = d.collection_policy.replace("_", " ").lower()
    st.markdown(f'<div class="evidence-head">Evidence · {device}</div><div class="where">{d.material_stream.replace("_", " ").capitalize()}, '
                f'{d.container_volume_m3:g} m³ · {policy} · operator {d.operator_id} · {html.escape(d.site_name)}{dot("observed")}</div>',
                unsafe_allow_html=True)

    events = query(f"""SELECT collection_id, trigger_type, status, actual_at, scheduled_at, device_fill_pct_before
                       FROM collection_events WHERE device_id = '{device}' ORDER BY actual_at""")
    daily = query(f"""SELECT date, fill_pct_max, mass_kg_max_valid FROM telemetry_daily_summary
                      WHERE device_id = '{device}' ORDER BY date""").assign(date=lambda x: pd.to_datetime(x.date))
    lifts = (events.dropna(subset=["actual_at"])[["collection_id", "trigger_type", "status", "actual_at"]]
             .assign(is_lift=lambda e: e.status.isin(LIFT), hl=lambda e: e.collection_id.isin(r["items"])))
    c1, c2 = st.columns(2)
    with c1:
        st.altair_chart(line_chart(daily, "fill_pct_max", "fill %", "%", lifts, y_max=100), width="stretch")
    with c2:
        if daily.mass_kg_max_valid.notna().any():
            st.altair_chart(line_chart(daily, "mass_kg_max_valid", "weight kg", "kg", lifts), width="stretch")
        else:
            st.info("No weight sensor on this compactor yet, so there is no weight line.")
    st.markdown(f'<div class="legend">Fill and weight{dot("simulated")}: highest valid reading of each day. '
                f'Amber lines = the lifts this decision is about, grey = other lifts, dashed = a trip without a lift.</div>',
                unsafe_allow_html=True)

    a = TASK_A[TASK_A.device_id == device]
    done = a[a.status.isin(LIFT)]
    known = done[done.mass_known.astype(bool) & (done.mass_kg > 0)]
    tonnes = known.mass_kg.sum() / 1000
    eur_t = known.collection_cost_eur.sum() / tonnes if tonnes else None
    bench = done.benchmark_eur_per_t.median()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cost per tonne", f"{eur(eur_t)} /t" if eur_t else "unknown", border=True,
              help="estimated – contract calculation, hypothetical tariffs")
    m2.metric("vs contract benchmark", f"{eur_t / bench:.1f}×" if eur_t and pd.notna(bench) else "unknown", border=True,
              help=f"estimated – benchmark {eur(bench)} per tonne" if pd.notna(bench) else "estimated")
    m3.metric("Lifts · tonnes", f"{len(done)} · {tonnes:.2f} t", border=True, help="observed lifts; tonnes from tickets, invoices or the device")
    m4.metric("Wasted-trip fees", eur(a[~a.status.isin(LIFT)].penalties_eur.sum()), border=True,
              help="estimated – contract calculation")

    if r.kind in ("resplit", "tonnage"):
        wc = weight_table(device)
        wc = wc[wc.collection_id.isin(r["items"])]
        st.dataframe(pd.DataFrame({
            "date": wc.actual_at.dt.tz_convert("Europe/Helsinki").dt.strftime("%d %b"),
            "container kg (device)": wc.device_kg.map(lambda x: f"{x:,.0f}" if pd.notna(x) else "–"),
            "ticket kg": wc.ticket_kg.map(lambda x: f"{x:,.0f}" if pd.notna(x) else "not shared"),
            "invoiced kg": wc.invoiced_kg.map(lambda x: f"{x:,.0f}"),
            "€ at stake": wc.eur_at_stake.map(lambda x: f"{x:+,.2f}" if pd.notna(x) else "–"),
            "why": wc.explanation,
        }), hide_index=True, column_config={"why": st.column_config.TextColumn(width="large"),
                                            "container kg (device)": st.column_config.TextColumn(help="simulated – container mass before minus after the lift"),
                                            "€ at stake": st.column_config.TextColumn(help="estimated – difference × the invoice's own € per kg")})

    with st.expander("Every lift of this compactor"):
        table = a.merge(events[["collection_id", "trigger_type", "device_fill_pct_before"]], on="collection_id", how="left")
        table = table.sort_values("service_date")
        lift_rows = table.status.isin(LIFT)
        src = table.mass_basis.map(lambda b: MASS_SOURCE.get(b, ("unknown" if b != "NOT_A_LIFT" else "no lift", "")))
        per_t = table.collection_cost_eur_per_t.where(lift_rows & table.mass_known.astype(bool))
        st.dataframe(pd.DataFrame({
            "date": pd.to_datetime(table.service_date).dt.strftime("%d %b"),
            "why": table.trigger_type.str.replace("_", " ").str.lower(),
            "status": table.status.str.replace("_", " ").str.lower(),
            "fill before": table.device_fill_pct_before.map(lambda x: f"{x:.0f} %" if pd.notna(x) else "–"),
            "kg": table.mass_kg.where(lift_rows).map(lambda x: f"{x:,.0f}" if pd.notna(x) else "–"),
            "weight source": [f"{n} ({t})" if t else n for n, t in src],
            "lift cost": table.collection_cost_eur.where(lift_rows).map(lambda x: f"€{x:,.2f}" if pd.notna(x) else "–"),
            "other fees": table.penalties_eur.map(lambda x: f"€{x:,.2f}"),
            "€ per tonne": [f"{x:,.0f}" if pd.notna(x) else ("unknown" if lift else "–") for x, lift in zip(per_t, lift_rows)],
        }), hide_index=True, column_config={
            "fill before": st.column_config.TextColumn(help="simulated – device fill the hour before the lift"),
            "lift cost": st.column_config.TextColumn(help="estimated – contract calculation (Task A baseline)"),
            "other fees": st.column_config.TextColumn(help="estimated – wasted-trip and cancellation fees"),
            "€ per tonne": st.column_config.TextColumn(help="estimated – lift cost ÷ tonnes; unknown weight is never filled in"),
        })


# ---------- decision cards ----------
def card(r, slot: str) -> None:
    verdict = decided.get(r.key)
    where = f'{r.device_id} · {html.escape(r.site.split(" (")[0])}'
    stake = (f'<div class="stake">{eur(r.stake_eur)}</div><div class="stake-label">{html.escape(r.stake_label)}{dot("estimated")}</div>'
             if r.stake_eur > 0 else "")
    with st.container(key=f"card_{slot}_{verdict or 'open'}"):
        if verdict:
            left, mid, right = st.columns([0.66, 0.18, 0.16], vertical_alignment="center")
            done_text = "Sent to your account manager" if verdict == "approved" else "Dismissed"
            left.markdown(f":material/{'check_circle' if verdict == 'approved' else 'do_not_disturb_on'}: **{done_text}** · "
                          f"{r.title} · {r.device_id}")
            mid.markdown(stake, unsafe_allow_html=True)
            right.button("Undo", key=f"undo_{slot}", type="tertiary", icon=":material/undo:", on_click=undo, args=(r.key,),
                         width="stretch")
            return
        left, mid, right = st.columns([0.5, 0.2, 0.3], vertical_alignment="center")
        left.markdown(f'<div class="ctitle">{html.escape(r.title)}</div><div class="where">{where}</div>', unsafe_allow_html=True)
        mid.markdown(stake, unsafe_allow_html=True)
        with right:
            ok, no = st.columns(2)
            ok.button("Approve", key=f"ok_{slot}", type="primary", icon=":material/check:", on_click=decide,
                      args=(r.key, "approved", r.stake_eur), width="stretch")
            no.button("Reject", key=f"no_{slot}", on_click=decide, args=(r.key, "rejected", r.stake_eur), width="stretch")
        st.markdown('<ul class="lines">' + "".join(f"<li>{dots(x)}</li>" for x in r.lines) + "</ul>", unsafe_allow_html=True)
        act, why = st.columns([0.8, 0.2], vertical_alignment="center")
        act.markdown(f'<div class="action"><b>Approve sends:</b> {html.escape(r.action)}</div>', unsafe_allow_html=True)
        opened = state.why == r.key
        why.button("Hide evidence" if opened else "Why?", key=f"why_{slot}", type="tertiary",
                   icon=":material/expand_less:" if opened else ":material/insights:", on_click=toggle_why, args=(r.key,),
                   width="stretch")
        if opened:
            evidence(r)


ranked = view[view.has_stake]
notes = view[~view.has_stake]
if ranked.empty and notes.empty:
    st.info("No findings for this compactor this quarter.")
top = ranked.head(TOP if start == "all" else len(ranked))
more = ranked.iloc[len(top):]
if not top.empty:
    st.markdown(f'<div class="section">Start here · the {len(top)} biggest</div>', unsafe_allow_html=True)
    for i, r in top.iterrows():
        card(r, str(i))
if not more.empty:
    with st.expander(f"{len(more)} more decisions · {eur(more[~more.key.isin(decided)].stake_eur.sum())} in question"):
        for i, r in more.iterrows():
            card(r, str(i))
if not notes.empty:
    with st.expander(f"{len(notes)} notes without € at stake (delays, sorting, sensor checks)"):
        for i, r in notes.iterrows():
            card(r, str(i))

# ---------- C14 · footer ----------
st.divider()
st.markdown(
    '<div class="legend"><b>All data is synthetic. Not Europress data.</b> Every number has an evidence dot: '
    + "".join(f'<span class="item">{dot(t)} {t} = {d}</span>' for t, d in TAGS.items())
    + "All tariffs are hypothetical customer–operator prices. A decision is a question, not a verdict: combined loads, side "
      "waste, tares and the device's own calibration all cause differences that are nobody's fault.</div>",
    unsafe_allow_html=True)
