"""Joy quick commerce: Monday brief.

Run:  streamlit run app.py
"""

import copy
import json

import altair as alt
import pandas as pd
import streamlit as st

from pipeline import DATA_DIR, load_config
from pipeline.brief import (backtest, day, inr, issues_for_week, manager_text, team_messages,
                            week_summary)
from pipeline.clean import FILES, clean, read_dir, read_raw
from pipeline.detect import run_all
from pipeline.metrics import KEY, weekly_fact

st.set_page_config(page_title="Joy QC Monday Brief", page_icon="📦", layout="wide")


# ---------------------------------------------------------------- data (cached)

@st.cache_data(show_spinner="Reading and cleaning the exports…")
def prepare_bundled():
    data = clean(read_dir(DATA_DIR))
    return data, weekly_fact(data)


@st.cache_data(show_spinner="Reading and cleaning your files…")
def prepare_uploaded(blobs: tuple):
    import io
    raw = read_raw({k: io.BytesIO(b) for k, b in blobs})
    data = clean(raw)
    return data, weekly_fact(data)


@st.cache_data(show_spinner="Checking every warehouse, product and week…")
def detect(fact: pd.DataFrame, cfg_json: str):
    return run_all(fact, json.loads(cfg_json))


# ---------------------------------------------------------------- sidebar

base_cfg = load_config()
cfg = copy.deepcopy(base_cfg)

with st.sidebar:
    st.header("Data")
    source = st.radio("Source", ["Sample exports (7 Sep – 15 Nov 2026)", "Upload this week's CSVs"],
                      label_visibility="collapsed")
    if source.startswith("Upload"):
        ups = {k: st.file_uploader(f, type="csv", key=k) for k, f in FILES.items()}
        if not all(ups.values()):
            st.info("Upload all four files: " + ", ".join(FILES.values()))
            st.stop()
        try:
            data, fact = prepare_uploaded(tuple((k, u.getvalue()) for k, u in ups.items()))
        except Exception as e:  # bad column names etc.
            st.error(f"Could not read the files: {e}")
            st.stop()
    else:
        data, fact = prepare_bundled()

    weeks = sorted(fact["week"].unique())
    labels = {f"{day(pd.Timestamp(w) + pd.Timedelta(7, 'D'))} (sales {day(w)}–"
              f"{day(pd.Timestamp(w) + pd.Timedelta(6, 'D'))})": pd.Timestamp(w) for w in weeks[::-1]}
    week = labels[st.selectbox("Brief for Monday", list(labels), index=0)]

    with st.expander("Thresholds", expanded=False):
        st.caption("Change these to see how the brief reacts. Defaults live in config.yaml.")
        cfg["under_delivery"]["max_fill_rate"] = st.slider("Supply: flag fill rate below", 0.5, 0.95,
                                                           base_cfg["under_delivery"]["max_fill_rate"], 0.05)
        cfg["under_delivery"]["min_units_short"] = st.number_input("Supply: and at least N units short", 0, 500,
                                                                   base_cfg["under_delivery"]["min_units_short"])
        cfg["po_stopped"]["min_prior_orders"] = st.slider("KAM: ordered in at least N of last 4 weeks", 1, 4,
                                                          base_cfg["po_stopped"]["min_prior_orders"])
        cfg["rank_drop"]["min_positions"] = st.slider("Marketing: rank worse by at least", 1, 10,
                                                      base_cfg["rank_drop"]["min_positions"])
        cfg["listing_issue"]["max_sales_ratio"] = st.slider("KAM listing: sales below % of normal", 0.1, 0.8,
                                                            base_cfg["listing_issue"]["max_sales_ratio"], 0.05)
        cfg["brief"]["min_impact_inr"] = st.number_input("Ignore issues smaller than ₹/week", 0, 50000,
                                                         base_cfg["brief"]["min_impact_inr"], step=500)
        cfg["brief"]["max_issues"] = st.slider("Show at most N issues", 3, 25, base_cfg["brief"]["max_issues"])

flags = detect(fact, json.dumps(cfg, sort_keys=True))
shown, watch = issues_for_week(flags, week, cfg, fact)
summary = week_summary(fact, week)
monday = week + pd.Timedelta(7, "D")


# ---------------------------------------------------------------- helpers

def line_history(issue) -> pd.DataFrame:
    keys = issue.lines[KEY].drop_duplicates()
    h = fact.merge(keys, on=KEY)
    h = h[h["week"] <= week].copy()
    h["spsd"] = h["sales_inr"] / h["store_days"].where(h["store_days"] > 0)
    h["fill_pct"] = h["fill_rate"] * 100
    h["product"] = h["product_name"].str.replace("Joy ", "", regex=False)
    return h


def chart(h: pd.DataFrame, col: str, title: str, reverse: bool = False):
    base = alt.Chart(h).encode(x=alt.X("week:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0)))
    lines = base.mark_line(point=True).encode(
        y=alt.Y(f"{col}:Q", title=None, axis=alt.Axis(labels=True, tickCount=4, labelPadding=4),
                scale=alt.Scale(reverse=reverse, zero=not reverse)),
        color=alt.Color("product:N", legend=alt.Legend(orient="bottom", title=None)),
        tooltip=["product", alt.Tooltip("week:T", format="%d %b"), alt.Tooltip(f"{col}:Q", format=".1f")])
    marker = alt.Chart(pd.DataFrame({"week": [week]})).mark_rule(color="#d33", strokeDash=[4, 3]).encode(x="week:T")
    return (lines + marker).properties(
        title=alt.TitleParams(title, anchor="start", fontSize=13), height=260,
        padding={"left": 8, "top": 6, "right": 8, "bottom": 4})


CHARTS = {
    "under_delivery": [("fill_pct", "PO fill rate %", False), ("availability", "Dark-store availability %", False)],
    "po_stopped": [("ordered", "Units ordered by the warehouse", False), ("availability", "Dark-store availability %", False)],
    "rank_drop": [("rank", "Search rank (top = #1)", True), ("spsd", "Sales per store-day ₹", False)],
    "listing_issue": [("spsd", "Sales per store-day ₹", False), ("availability", "Dark-store availability %", False)],
}


def issue_card(issue, n=None, expanded=False):
    label = f"{'#' + str(n) + '  ' if n else ''}{issue.title}  ·  ~{inr(issue.impact_inr)}/week  ·  {issue.status}"
    with st.expander(label, expanded=expanded):
        st.markdown(f"**Owner:** {issue.team}")
        st.write(issue.detail)
        st.markdown(f"**What to do:** {issue.action}")
        h = line_history(issue)
        c1, c2 = st.columns(2)
        for col, (metric, title, rev) in zip((c1, c2), CHARTS[issue.detector]):
            col.altair_chart(chart(h, metric, title, rev), use_container_width=True)


def team_tab(team_filter, empty_msg):
    sub = shown[shown["team"].map(team_filter)] if len(shown) else shown
    if sub.empty:
        st.success(empty_msg)
        return
    msgs = team_messages(sub, week)
    for team, text in msgs.items():
        st.subheader(team)
        st.caption("Copy and paste into WhatsApp")
        st.code(text, language=None, wrap_lines=True)
        for r in sub[sub["team"] == team].itertuples():
            issue_card(r)


# ---------------------------------------------------------------- page

st.title(f"Monday brief · {monday.strftime('%-d %b %Y')}")
st.caption(f"Sales week {day(week)}–{day(week + pd.Timedelta(6, 'D'))} · Blinkit, Zepto, Instamart · "
           f"{data.stores['city'].nunique()} cities · {data.stores['dark_store_id'].nunique()} dark stores")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Issues to act on", len(shown), help="Sorted by rupees. Smaller ones go to the watchlist.")
k2.metric("Sales at stake", f"{inr(shown['impact_inr'].sum()) if len(shown) else '₹0'}/wk",
          help="Per issue: the bigger of (sales already lost vs a normal week) and (sales at risk: "
               "value of stock not delivered / a normal week of sales when a warehouse stops ordering).")
k3.metric("New this week", int((shown["status"] == "New").sum()) if len(shown) else 0)
k4.metric("Sales last week", inr(summary["sales"]),
          f"{summary['change_per_store_day']:+.0%} per store-day" if "change_per_store_day" in summary else None)
if abs(summary.get("price_move", 0)) >= 0.03:
    st.info(f"Selling prices moved **{summary['price_move']:+.0%}** on every app this week, so a platform-wide "
            "discount started or ended. Part of the sales change is "
            "price, not a problem, so it is not flagged.")

tabs = st.tabs(["Priority list", "Supply", "Platform KAMs", "Marketing", "Did it work?", "Data quality", "How it works"])

with tabs[0]:
    if shown.empty:
        st.success("Nothing above the thresholds this week.")
    else:
        st.code(manager_text(shown, watch, summary, week), language=None, wrap_lines=True)
        for n, r in enumerate(shown.itertuples(), 1):
            issue_card(r, n, expanded=(n == 1))
    if len(watch):
        with st.expander(f"Watchlist: {len(watch)} smaller item(s), not sent to teams"):
            st.dataframe(watch[["team", "title", "impact_inr", "status"]]
                         .rename(columns={"impact_inr": "₹/week"}), hide_index=True, width="stretch")

with tabs[1]:
    team_tab(lambda t: t == "Supply", "No delivery shortfalls worth acting on this week.")
with tabs[2]:
    team_tab(lambda t: t.endswith("KAM"), "No platform ordering or listing problems this week.")
with tabs[3]:
    team_tab(lambda t: t == "Marketing", "No search-visibility drops this week.")

with tabs[4]:
    st.subheader("Would this have caught the three problems from the last two months?")
    st.write("Replaying every past week through the same checks, with the thresholds in the sidebar:")
    st.dataframe(backtest(flags, cfg), hide_index=True, width="stretch")
    st.subheader("How many issues each Monday?")
    counts = []
    for w in weeks:
        s, wl = issues_for_week(flags, w, cfg)
        counts.append({"Monday": day(pd.Timestamp(w) + pd.Timedelta(7, "D")), "Sent to teams": len(s), "Watchlist": len(wl)})
    cdf = pd.DataFrame(counts).melt("Monday", var_name="type", value_name="issues")
    st.altair_chart(alt.Chart(cdf).mark_bar().encode(
        x=alt.X("Monday:O", sort=None, axis=alt.Axis(labelAngle=0), title=None),
        y=alt.Y("issues:Q", title=None, axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("type:N", legend=alt.Legend(orient="bottom", title=None),
                        scale=alt.Scale(domain=["Sent to teams", "Watchlist"], range=["#2f6fdf", "#9aa3ad"])),
        order=alt.Order("type:N"),
        tooltip=["type", "issues"]).properties(height=220), use_container_width=True)
    st.caption("Kept short on purpose: if it flags 200 things, nobody reads it.")

with tabs[5]:
    st.write("What was wrong with the raw exports and what the tool did about it:")
    st.dataframe(data.dq_table, hide_index=True, width="stretch")

with tabs[6]:
    st.markdown("""
Every week, for every **app × city (warehouse) × product**, the tool compares the week with that line's
own baseline: the last 4 weeks in which it was *not* flagged. Using only healthy weeks means a problem that runs for
a month never becomes the new normal.

| Check | Fires when | Goes to |
|---|---|---|
| Under-delivery | we delivered < 80% of a PO line and ≥ 20 units short | Supply (warehouse, product, units) |
| Warehouse stopped ordering | no PO for a product it ordered in ≥ 3 of the last 4 weeks | That app's account manager |
| Search rank drop | average rank ≥ 3 places worse **while availability ≥ 80%** | Marketing (₹ lost) |
| Listing problem | sales per store-day < 40% of normal **with stock and rank fine** | That app's account manager |

**Ranking:** each issue gets a rough ₹/week: the bigger of the sales already lost (normal sales per store-day ×
store-days − actual) and sales at risk (value of the units we didn't deliver, or a normal week of sales when a
warehouse stops ordering, because the stock runs out a week or two later). Issues under ₹2,000/week go to a watchlist
and at most 10 are sent.

**Not flagged on purpose:** small dips (seasonal sunscreen slowdown in November), price-driven changes that hit
every product at once, and a listing alert on a product whose drop is already explained by a supply problem.
""")
