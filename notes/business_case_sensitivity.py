"""B08 · Sensitivity of the SMART Weight Check business case, plus hardware payback and future hypotheses.

Run from the repo root AFTER the calculator (B07):
    python baselines/business_case.py competition --params configs/our_params.yaml --out our_business_case
    python notes/business_case_sensitivity.py

Reuses the calculator's own `scenarios()` on its per-customer value table, so every number here follows the
same formulas as baselines/business_case.py. Writes our_business_case/sensitivity.md.

Evidence tags: customer value = ESTIMATED from synthetic records; prices, costs, adoption, realisation and
hardware costs = HYPOTHETICAL (our parameters). Nothing here is market evidence or a demonstrated saving.
"""
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "baselines"))
sys.path.insert(0, str(ROOT / "src"))
from business_case import LEVERS, scenarios  # noqa: E402

PARAMS = ROOT / "configs" / "our_params.yaml"
OUT = ROOT / "our_business_case"
BASE_PRICE, BASE_ADOPTION = 15, 25
YEARS = 3                       # horizon for the cumulative view; no churn assumed (stated as a limitation)
# Weighing hardware (HYPOTHETICAL engineering estimates, submission/1_WEIGHING_CONCEPT.md): installed cost per device
HARDWARE = {"factory option (new compactor)": 1200, "retrofit weigh frame": 3400}

P0 = yaml.safe_load(open(PARAMS))
cv0 = pd.read_csv(OUT / "business_case_customers.csv")
md: list[str] = []


def show(title: str, df: pd.DataFrame, note: str = "") -> None:
    md.extend([f"## {title}", "", df.to_markdown(index=False), ""])
    if note:
        md.extend([note, ""])
    print(f"\n{title}\n{df.to_string(index=False)}")


def run(P: dict, price=BASE_PRICE, adoption=BASE_ADOPTION) -> dict:
    """One scenario row from the calculator, plus steady-state profit and payback."""
    P = copy.deepcopy(P)
    P["pricing"]["price_per_device_month_eur"] = [price]
    P["adoption"]["adoption_share_of_eligible_pct"] = [adoption]
    _, sc = scenarios(cv0, P)
    r = sc.iloc[0].to_dict()
    r["annual_profit_eur"] = r["annual_revenue_eur"] - r["annual_operating_cost_eur"]     # steady state, after onboarding
    r[f"{YEARS}y_cumulative_eur"] = YEARS * r["annual_profit_eur"] - r["one_off_onboarding_eur"]
    r["payback_years"] = round(r["one_off_onboarding_eur"] / r["annual_profit_eur"], 1) if r["annual_profit_eur"] > 0 else np.inf
    return r


# ---------------------------------------------------------------- 1. value per device-month (justifies prices)
cv, _ = scenarios(cv0, copy.deepcopy(P0))
cv["value_per_device_month"] = cv.realisable_value_eur / cv.n_devices / 12
cv["spend_per_device_month"] = cv.annual_spend_eur / cv.n_devices / 12
q = cv.value_per_device_month.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
show("1. Realisable customer value per device-month (estimated, our realisation shares)",
     pd.DataFrame({"percentile over 52 customers": ["10th", "25th", "median", "75th", "90th"],
                   "EUR per device-month": q.round(1).values}),
     f"Portfolio: {len(cv)} customers, {int(cv.n_devices.sum())} devices, annual waste spend EUR {cv.annual_spend_eur.sum():,.0f}; "
     f"identified value EUR {cv.identified_value_eur.sum():,.0f} ({cv.identified_value_eur.sum() / cv.annual_spend_eur.sum():.1%} of spend), "
     f"realisable EUR {cv.realisable_value_eur.sum():,.0f} ({cv.realisable_value_eur.sum() / cv.annual_spend_eur.sum():.1%} of spend). "
     f"Median spend per device-month EUR {cv.spend_per_device_month.median():,.0f}.")

lev = pd.DataFrame({"lever": LEVERS,
                    "identified_eur_per_year": [round(cv[f"{k}_eur"].sum()) for k in LEVERS],
                    "realisation_share": [P0["value_realisation"][k] for k in LEVERS],
                    "realisable_eur_per_year": [round(cv[f"{k}_eur"].sum() * P0["value_realisation"][k]) for k in LEVERS]})
show("2. Where the customer value comes from (estimated, all 52 customers, annualised)", lev)

# ---------------------------------------------------------------- 3. price sweep: which price maximises fee revenue?
rows = []
for mult in (2, 3):
    for p in (5, 10, 15, 20, 25, 30, 40, 50, 60):
        fee = cv.n_devices * p * 12
        el = cv.realisable_value_eur >= mult * fee
        rows.append({"purchase rule (value >= x fee)": mult, "price EUR/device-month": p, "eligible customers": int(el.sum()),
                     "eligible devices": int(cv.n_devices[el].sum()), "fee revenue at 100 % adoption EUR": int(fee[el].sum())})
sweep = pd.DataFrame(rows)
best = sweep[sweep["purchase rule (value >= x fee)"] == 3].sort_values("fee revenue at 100 % adoption EUR").iloc[-1]
show("3. Price sweep (estimated eligibility, hypothetical prices)", sweep,
     f"With the 3x purchase rule fee revenue peaks at EUR {best['price EUR/device-month']} per device-month: "
     "cheaper prices add customers who are too small to matter, dearer prices lose them.")

# ---------------------------------------------------------------- 4. B08 table: price x adoption -> yearly profit
grid = []
for p in P0["pricing"]["price_per_device_month_eur"]:
    for a in P0["adoption"]["adoption_share_of_eligible_pct"]:
        grid.append({"price": p, "adoption": a, **run(P0, p, a)})
g = pd.DataFrame(grid)
tab = g.pivot(index="price", columns="adoption", values="annual_profit_eur").astype(int)
tab.columns = [f"adoption {c} %" for c in tab.columns]
show("4. B08 · Yearly profit after onboarding (steady state, EUR, hypothetical)", tab.reset_index().rename(columns={"price": "price EUR/device-month"}),
     "Yearly profit = fee revenue - operating cost - support (onboarding excluded). Year 1 is lower by the one-off onboarding below.")
detail = g[["price", "adoption", "adopting_customers_expected", "devices_expected", "annual_revenue_eur", "annual_operating_cost_eur",
            "one_off_onboarding_eur", "year1_contribution_eur", "annual_profit_eur", f"{YEARS}y_cumulative_eur", "payback_years"]]
show("5. Scenario detail (hypothetical)", detail)

# ---------------------------------------------------------------- 6. which assumption matters most? (one at a time)
base = run(P0)
KEY = f"{YEARS}y_cumulative_eur"


def variant(label, low, high, apply):
    out = {"assumption": label, "low setting": low, "high setting": high}
    for side, v in (("low", low), ("high", high)):
        P, price, adoption = apply(copy.deepcopy(P0), v)
        out[f"{YEARS}-year result at low" if side == "low" else f"{YEARS}-year result at high"] = int(run(P, price, adoption)[KEY])
    out["swing EUR"] = abs(out[f"{YEARS}-year result at high"] - out[f"{YEARS}-year result at low"])
    return out


def scale_realisation(P, f):
    for k in LEVERS:
        P["value_realisation"][k] = min(1.0, P["value_realisation"][k] * f)
    return P, BASE_PRICE, BASE_ADOPTION


def set_cost(name):
    def f(P, v):
        P["costs"][name] = v
        return P, BASE_PRICE, BASE_ADOPTION
    return f


def set_mult(P, v):
    P["adoption"]["purchase_condition_value_multiple"] = v
    return P, BASE_PRICE, BASE_ADOPTION


tornado = pd.DataFrame([
    variant("price EUR/device-month", 10, 25, lambda P, v: (P, v, BASE_ADOPTION)),
    variant("adoption % of eligible", 10, 40, lambda P, v: (P, BASE_PRICE, v)),
    variant("value realisation (x base shares)", 0.5, 1.5, scale_realisation),
    variant("purchase rule (value >= x fee)", 4, 2, set_mult),
    variant("support EUR/customer-month", 80, 20, set_cost("customer_support_per_customer_month_eur")),
    variant("onboarding EUR/customer", 1600, 400, set_cost("onboarding_per_customer_eur")),
    variant("operating cost EUR/device-month", 6, 1, set_cost("operating_cost_per_device_month_eur")),
]).sort_values("swing EUR", ascending=False)
show(f"6. Which assumption matters most? ({YEARS}-year cumulative profit, base EUR {int(base[KEY]):,}; hypothetical)", tornado,
     f"Base case: EUR {BASE_PRICE}/device-month, {BASE_ADOPTION} % adoption, our_params.yaml. One assumption moves at a time.")

# ---------------------------------------------------------------- 7. which customers are worth serving? (segment view at base)
P = copy.deepcopy(P0)
fee = cv.n_devices * BASE_PRICE * 12
el = cv.realisable_value_eur >= P["adoption"]["purchase_condition_value_multiple"] * fee
c = P["costs"]
seg = cv[el].assign(rev=fee[el], opex=lambda x: x.n_devices * c["operating_cost_per_device_month_eur"] * 12 + c["customer_support_per_customer_month_eur"] * 12,
                    onb=lambda x: c["onboarding_per_customer_eur"] + x.n_devices * c["onboarding_per_device_eur"])
seg = seg.groupby("segment").agg(eligible_customers=("customer_id", "count"), devices=("n_devices", "sum"), revenue_per_customer=("rev", "mean"),
                                 profit_per_customer=("rev", "mean")).reset_index()
seg_profit = cv[el].assign(p=fee[el] - (cv.n_devices * c["operating_cost_per_device_month_eur"] * 12 + c["customer_support_per_customer_month_eur"] * 12)).groupby("segment").p.mean()
seg["profit_per_customer"] = seg.segment.map(seg_profit)
show(f"7. Yearly profit per adopting customer by fleet size at EUR {BASE_PRICE} (hypothetical)", seg.round(0),
     "Small fleets barely cover the analyst support; the service pays from about 6 devices per customer.")

# ---------------------------------------------------------------- 8. does the weighing hardware pay back for the customer?
dev = cv.loc[cv.index.repeat(cv.n_devices)]           # one row per device, customer-average value
net = dev.value_per_device_month * 12 - BASE_PRICE * 12     # customer's yearly gain after the subscription
rows = []
for name, capex in HARDWARE.items():
    pb = np.where(net > 0, capex / net, np.inf)
    rows.append({"hardware": name, "installed cost EUR": capex,
                 "payback years at median device": round(float(np.median(pb)), 1),
                 "payback years at 75th pct device": round(float(np.quantile(pb, 0.25)), 1),
                 "share of devices paying back within 3 years": f"{(pb <= 3).mean():.0%}",
                 "within 5 years": f"{(pb <= 5).mean():.0%}"})
show("8. Customer payback of the weighing hardware (estimated value, hypothetical hardware cost)", pd.DataFrame(rows),
     f"Customer gain = realisable value - EUR {BASE_PRICE}/month subscription. Device value = its customer's average per device. "
     "Conclusion: a retrofit frame only pays where the value is high, so weigh where it pays: factory option on new "
     "compactors, retrofit for the top-value devices found by the free value scan.")

# ---------------------------------------------------------------- 9. future hypotheses (Europress in the middle) - labelled HYPOTHESIS
fm = P0["future_models"]
tp, ts, mm = fm["transport_procurement"], fm["tonne_based_full_service"], fm["materials_marketplace"]
hyp = pd.DataFrame([
    {"HYPOTHESIS (not today's role)": "transport procurement (Europress buys transport for pooled customers)",
     "parameter": f"{tp['discount_on_logistics_pct']} % cheaper logistics x {tp['realisation']} realised",
     "value EUR/year (all 52 customers)": f"{cv.logistics_spend_eur.sum() * tp['discount_on_logistics_pct'] / 100 * tp['realisation']:,.0f} for customers"},
    {"HYPOTHESIS (not today's role)": "tonne-based full service (one EUR/t price, Europress in the middle)",
     "parameter": f"{ts['margin_on_customer_spend_pct']} % margin on customer spend",
     "value EUR/year (all 52 customers)": f"{cv.annual_spend_eur.sum() * ts['margin_on_customer_spend_pct'] / 100:,.0f} gross margin for Europress"},
    {"HYPOTHESIS (not today's role)": "materials marketplace (better price for cardboard and plastics)",
     "parameter": f"+EUR {mm['credit_uplift_eur_per_t']}/t x {mm['realisation']} realised",
     "value EUR/year (all 52 customers)": f"{cv.credit_eligible_tonnes.sum() * mm['credit_uplift_eur_per_t'] * mm['realisation']:,.0f} for customers"},
])
show("9. Future models, clearly labelled hypotheses (all 52 customers, annual)", hyp,
     "Each one needs a role Europress does not have today and verified weight to price per tonne. Not part of the main case.")

md.insert(0, "# SMART Weight Check · sensitivity and payback (B08)\n\n"
             "Generated by `python notes/business_case_sensitivity.py` from `our_business_case/business_case_customers.csv` and "
             "`configs/our_params.yaml`. **Synthetic data. Customer value = estimated; prices, costs, adoption, realisation and "
             "hardware costs = hypothetical.** Not market evidence, not a Europress price, not a demonstrated saving.\n")
(OUT / "sensitivity.md").write_text("\n".join(md))
print(f"\nwrote {OUT / 'sensitivity.md'}")
