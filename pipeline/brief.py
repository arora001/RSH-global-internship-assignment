"""Turn raw flags into the Monday brief: grouped issues, sorted by rupees,
capped, with a plain-language action per team and WhatsApp-ready text."""

from dataclasses import dataclass

import pandas as pd

from .clean import CleanData, read_dir, clean
from .detect import run_all
from .metrics import weekly_fact

# The three incidents from the assignment. "started" is the first week the
# problem is visible in the data (checked by hand with pivots).
KNOWN_INCIDENTS = [
    dict(name="Blinkit Bengaluru: we delivered ~half of 6 products' orders", detector="under_delivery",
         match=dict(platform="Blinkit", city="Bengaluru"), started="2026-09-21", noticed_after_weeks=5, owner="Supply"),
    dict(name="Instamart Hyderabad: warehouse stopped ordering sunscreen", detector="po_stopped",
         match=dict(platform="Instamart", city="Hyderabad", category="Sunscreen"), started="2026-09-14",
         noticed_after_weeks=3, owner="Instamart KAM"),
    dict(name="Zepto Bengaluru: best-selling face wash fell from ~3rd to ~13th in search", detector="rank_drop",
         match=dict(platform="Zepto", city="Bengaluru", sku_code="JY-FW-NEEM-100"), started="2026-10-12",
         noticed_after_weeks=4, owner="Marketing"),
]


def inr(x: float) -> str:
    """₹ in the way an Indian manager reads it: ₹8,400 / ₹1.3L."""
    x = float(x)
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.1f}L"
    s = f"{round(x):,}"
    return f"₹{s}"


def _n(x, word: str) -> str:
    x = round(float(x))
    return f"{x} {word}" if x == 1 else f"{x} {word}s"


def day(d) -> str:
    return pd.Timestamp(d).strftime("%-d %b")


@dataclass
class Result:
    data: CleanData
    fact: pd.DataFrame
    flags: pd.DataFrame


def analyse(raw: dict, cfg: dict) -> Result:
    data = clean(raw)
    fact = weekly_fact(data)
    return Result(data=data, fact=fact, flags=run_all(fact, cfg))


def analyse_dir(data_dir, cfg) -> Result:
    return analyse(read_dir(data_dir), cfg)


# ---------------------------------------------------------------- issues

def price_moves(fact: pd.DataFrame, week) -> pd.DataFrame:
    """Price change of each line vs the previous week, and the typical change on that app.
    Used so a listing alert only mentions price when this product moved differently from
    everything else (e.g. not when a festive discount ends across the board)."""
    week = pd.Timestamp(week)
    prev = fact.loc[fact["week"] < week, "week"].max()
    if pd.isna(prev):
        return pd.DataFrame(columns=["platform", "city", "warehouse_id", "sku_code", "price_move", "app_move"])
    a = fact[fact["week"] == week].set_index(["platform", "city", "warehouse_id", "sku_code"])["price"]
    b = fact[fact["week"] == prev].set_index(["platform", "city", "warehouse_id", "sku_code"])["price"]
    m = (a / b - 1).rename("price_move").reset_index()
    m["app_move"] = m.groupby("platform")["price_move"].transform("median")
    return m


def issues_for_week(flags: pd.DataFrame, week, cfg: dict, fact: pd.DataFrame | None = None
                    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Group a week's flags into issues. Returns (shown, watchlist)."""
    week = pd.Timestamp(week)
    f = flags[flags["week"] == week].copy() if not flags.empty else flags
    if f.empty:
        empty = pd.DataFrame(columns=["issue_id", "impact_inr"])
        return empty, empty

    # Supply and PO problems are about a warehouse: one issue per warehouse, SKUs listed inside.
    # Search and listing problems are about one product in one city.
    if fact is not None:
        f = f.merge(price_moves(fact, week), on=["platform", "city", "warehouse_id", "sku_code"], how="left")
    else:
        f["price_move"], f["app_move"] = float("nan"), float("nan")
    by_wh = f["detector"].isin(["under_delivery", "po_stopped"])
    f["issue_id"] = f["detector"] + "|" + f["warehouse_id"]
    f.loc[~by_wh, "issue_id"] = f["detector"] + "|" + f["warehouse_id"] + "|" + f["sku_code"]

    rows = []
    for iid, g in f.groupby("issue_id", sort=False):
        g = g.sort_values("impact_inr", ascending=False)
        top = g.iloc[0]
        rows.append(dict(
            issue_id=iid, week=week, detector=top["detector"], team=top["team"],
            platform=top["platform"], city=top["city"], warehouse_id=top["warehouse_id"],
            impact_inr=int(g["impact_inr"].sum()), lost_inr=int(g["lost_inr"].sum()),
            lost_so_far_inr=int(g["lost_so_far_inr"].sum()), weeks_running=int(g["weeks_running"].max()),
            n_products=len(g), products=", ".join(g["product_name"]), lines=g,
            title=_title(g), detail=_detail(g), action=_action(g),
        ))
    issues = pd.DataFrame(rows)
    issues["status"] = issues["weeks_running"].map(lambda w: "New" if w == 1 else f"Week {w}")
    issues = issues.sort_values("impact_inr", ascending=False).reset_index(drop=True)

    b = cfg["brief"]
    big = issues["impact_inr"] >= b["min_impact_inr"]
    shown = issues[big].head(b["max_issues"])
    watch = issues[~issues.index.isin(shown.index)]
    return shown.reset_index(drop=True), watch.reset_index(drop=True)


def _title(g: pd.DataFrame) -> str:
    t = g.iloc[0]
    where = f"{t.platform} {t.city}"
    if t.detector == "under_delivery":
        fill = g["delivered"].sum() / g["ordered"].sum()
        return f"{where} warehouse ({t.warehouse_id}): we delivered only {fill:.0%} of the order for {_n(len(g), 'product')}"
    if t.detector == "po_stopped":
        names = ", ".join(g["product_name"])
        return f"{where} warehouse ({t.warehouse_id}) has stopped ordering {names}"
    if t.detector == "rank_drop":
        return f"{where}: {t.product_name} fell to #{t['rank']:.0f} in search (normally #{t.rank_before:.0f})"
    if t.vanished:
        return f"{where}: {t.product_name} has disappeared from the sales data"
    return f"{where}: {t.product_name} sales down {1 - t.sales_ratio:.0%} while stock and search rank look normal"


def _detail(g: pd.DataFrame) -> str:
    t = g.iloc[0]
    run = f" This is week {t.weeks_running} in a row." if t.weeks_running > 1 else " New this week."
    if t.detector == "under_delivery":
        lines = "; ".join(f"{r.product_name}: ordered {r.ordered:.0f}, delivered {r.delivered:.0f} "
                          f"({r.short_units:.0f} short)" for r in g.itertuples())
        avail = (g["availability"].mean(), g["availability_before"].mean())
        return (f"{lines}. Dark-store availability for these is {avail[0]:.0f}% (normally ~{avail[1]:.0f}%)." + run)
    if t.detector == "po_stopped":
        last = day(t.last_po_week) if pd.notna(t.last_po_week) else "before the data starts"
        return (f"No purchase order for {_n(t.weeks_running, 'week')}; last order was the week of {last}. "
                f"Availability in {t.city} dark stores is {g['availability'].mean():.0f}% "
                f"(normally ~{g['availability_before'].mean():.0f}%) and will keep falling.")
    if t.detector == "rank_drop":
        return (f"Stock is fine ({t.availability:.0f}% availability) but sales are {1 - t.sales_ratio:.0%} below normal: "
                f"about {inr(t.lost_inr)} lost this week, {inr(t.lost_so_far_inr)} since it started." + run)
    price = ""
    if pd.notna(t.price_move) and abs(t.price_move - t.app_move) >= 0.05:
        price = (f" Its price moved {t.price_move:+.0%} this week while the rest of {t.platform} moved "
                 f"{t.app_move:+.0%}: check the price.")
    exp_units = t.expected_inr / t.price if t.price else float("nan")
    return (f"Sold {_n(t.units, 'unit')} this week vs ~{exp_units:.0f} normally. Availability {t.availability:.0f}%, "
            f"search rank #{t['rank']:.0f} (normal #{t.rank_before:.0f}), so it is not a stock or visibility problem."
            + price + run)


def _action(g: pd.DataFrame) -> str:
    t = g.iloc[0]
    if t.detector == "under_delivery":
        return (f"Ship the missing {g['short_units'].sum():.0f} units to {t.warehouse_id} this week. "
                "If we are short of stock ourselves, tell the QC manager today so other cities can be prioritised.")
    if t.detector == "po_stopped":
        return (f"Please check why {t.warehouse_id} stopped ordering and raise a PO this week; "
                "confirm the item hasn't been blocked or delisted in your system.")
    if t.detector == "rank_drop":
        return (f"Look at sponsored search / ads for '{t.category.lower()}' on {t.platform} in {t.city}, "
                "and check if a competitor launched or ran a promotion there.")
    return (f"Please check the listing in {t.city} is live and buyable (product page, price, add-to-cart) "
            "and tell us if anything changed on your side.")


# ---------------------------------------------------------------- summaries

def week_summary(fact: pd.DataFrame, week) -> dict:
    week = pd.Timestamp(week)
    w = fact.groupby("week").agg(sales=("sales_inr", "sum"), sd=("store_days", "sum")).sort_index()
    this = w.loc[week]
    prev = w.loc[:week].iloc[-2] if len(w.loc[:week]) > 1 else None
    out = dict(sales=this.sales, per_store_day=this.sales / this.sd if this.sd else 0)
    if prev is not None and prev.sd:
        out["change"] = this.sales / prev.sales - 1
        out["change_per_store_day"] = (this.sales / this.sd) / (prev.sales / prev.sd) - 1
        moves = price_moves(fact, week)["price_move"]
        out["price_move"] = moves.median() if len(moves) else 0.0
    return out


def team_messages(shown: pd.DataFrame, week) -> dict:
    """WhatsApp-style text, one message per team."""
    week = pd.Timestamp(week)
    monday = day(week + pd.Timedelta(7, 'D'))
    header = f"(Joy QC brief for Mon {monday}, sales week {day(week)}–{day(week + pd.Timedelta(6, 'D'))})"
    msgs = {}
    for team, g in shown.groupby("team", sort=False):
        lines = [f"*{team}: {_n(len(g), 'thing')} to act on* {header}", ""]
        for n, r in enumerate(g.itertuples(), 1):
            tag = "NEW" if r.status == "New" else r.status.upper()
            lines += [f"*{n}. {r.title}* [{tag}, ~{inr(r.impact_inr)}/week]", r.detail, f"👉 {r.action}", ""]
        msgs[team] = "\n".join(lines).strip()
    return msgs


def manager_text(shown: pd.DataFrame, watch: pd.DataFrame, summary: dict, week) -> str:
    week = pd.Timestamp(week)
    total = shown["impact_inr"].sum() if len(shown) else 0
    head = (f"*Joy quick commerce: Monday {day(week + pd.Timedelta(7, 'D'))}*\n"
            f"Last week sales {inr(summary['sales'])}")
    if "change" in summary:
        head += (f" ({summary['change']:+.0%} vs previous week; "
                 f"{summary['change_per_store_day']:+.0%} per dark store-day)")
    if abs(summary.get("price_move", 0)) >= 0.03:
        head += (f"\nNote: selling prices moved {summary['price_move']:+.0%} across all apps this week "
                 "(a platform-wide discount started or ended), so some of the sales change is price, not a problem.")
    head += f"\n{_n(len(shown), 'issue')} need action, worth ~{inr(total)}/week in sales.\n"
    body = [f"{n}. [{r.team}] {r.title} (~{inr(r.impact_inr)}/wk, {r.status.lower()})"
            for n, r in enumerate(shown.itertuples(), 1)]
    tail = f"\n{_n(len(watch), 'smaller item')} on the watchlist, not sent to teams." if len(watch) else ""
    return head + "\n" + "\n".join(body) + tail


def backtest(flags: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """For each known incident: in which Monday brief would it first have appeared (in the shown list)?"""
    rows = []
    weeks = sorted(pd.to_datetime(flags["week"].unique())) if not flags.empty else []
    for inc in KNOWN_INCIDENTS:
        first = None
        for w in weeks:
            shown, _ = issues_for_week(flags, w, cfg)
            for r in shown.itertuples():
                lines = r.lines
                if r.detector != inc["detector"]:
                    continue
                if all((lines[k] == v).any() for k, v in inc["match"].items()):
                    first = pd.Timestamp(w)
                    break
            if first is not None:
                break
        started = pd.Timestamp(inc["started"])
        rows.append({
            "incident": inc["name"],
            "owner": inc["owner"],
            "problem started (data week)": day(started),
            "flagged in brief of": day(first + pd.Timedelta(7, 'D')) if first is not None else "not flagged",
            "weeks to flag": (int((first - started).days / 7) + 1) if first is not None else None,
            "actually noticed after": f"~{inc['noticed_after_weeks']} weeks",
        })
    return pd.DataFrame(rows)
