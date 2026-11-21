"""Four checks, each owned by one team, run week by week for every
(platform, city/warehouse, product) line.

Baseline = the last N weeks where that line was NOT flagged. Without this, a
problem that runs for 5 weeks becomes "normal" after 4 and stops being flagged,
which is exactly how the Zepto search-rank drop would have been missed.

Money:
  lost_inr    = (baseline sales per store-day x this week's store-days) - actual sales
  at_risk_inr = sales we expect to lose soon even if it has not shown yet
                (supply: value of units not delivered; PO stopped: a full normal week)
  impact_inr  = max(lost, at_risk) -> used to sort the brief
"""

import numpy as np
import pandas as pd

from .metrics import KEY

DETECTORS = {
    "under_delivery": ("Supply", "We under-delivered a purchase order"),
    "po_stopped": ("KAM", "Platform warehouse stopped ordering"),
    "rank_drop": ("Marketing", "Dropped in search results"),
    "listing_issue": ("KAM", "Sales collapsed with stock and rank fine (likely listing problem)"),
}


def team_for(detector: str, platform: str) -> str:
    team = DETECTORS[detector][0]
    return f"{platform} KAM" if team == "KAM" else team


def run_all(fact: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Return every flag for every week (history + latest)."""
    rows = []
    for key, g in fact.groupby(KEY, sort=False):
        rows.extend(_scan_line(dict(zip(KEY, key)), g.reset_index(drop=True), cfg))
    flags = pd.DataFrame(rows)
    if flags.empty:
        return flags
    return _dedupe(flags)


def _scan_line(key: dict, g: pd.DataFrame, cfg: dict) -> list:
    bw, bmin = cfg["baseline"]["weeks"], cfg["baseline"]["min_weeks"]
    ud, ps, rd, li = cfg["under_delivery"], cfg["po_stopped"], cfg["rank_drop"], cfg["listing_issue"]

    flagged_any = np.zeros(len(g), dtype=bool)
    run_len = {d: 0 for d in DETECTORS}     # consecutive weeks each check has fired
    run_lost = {d: 0.0 for d in DETECTORS}  # cumulative lost sales over that run
    out = []

    for i, r in g.iterrows():
        healthy = [j for j in range(i) if not flagged_any[j]][-bw:]
        # One healthy week is enough to put a rupee figure on a loss; judging rank or
        # sales "unusual" needs at least `min_weeks` of history.
        base = g.loc[healthy] if healthy else None
        enough_history = len(healthy) >= bmin
        prior = g.loc[max(0, i - 4):i - 1]
        prior_orders = int(prior["has_po"].sum())
        # "Ordered in >= 3 of the last 4 weeks", or in every week we have if the data is shorter than that.
        needed = min(ps["min_prior_orders"], len(prior))

        b = {}
        if base is not None and base["store_days"].sum() > 0:
            b_spsd = base["sales_inr"].sum() / base["store_days"].sum()
            store_days = r["store_days"] if r["store_days"] > 0 else base["store_days"].mean()
            expected = b_spsd * store_days
            b = dict(expected=expected,
                     lost=max(0.0, expected - r["sales_inr"]),
                     ratio=(r["sales_inr"] / expected) if expected > 0 else np.nan,
                     rank=base["rank"].mean(),
                     avail=base["availability"].mean(),
                     price=base["price"].mean())

        fired = {}
        # 1. Supply: we delivered too little against a PO.
        if r["has_po"] and r["fill_rate"] < ud["max_fill_rate"] and r["short_units"] >= ud["min_units_short"]:
            price = r["price"] if r["price"] > 0 else b.get("price", 0)
            fired["under_delivery"] = dict(at_risk=r["short_units"] * price)

        # 2. KAM: the warehouse stopped ordering something it normally orders.
        if not r["has_po"] and i > 0 and (prior_orders >= needed or run_len["po_stopped"] > 0):
            # At risk: a normal week of sales; if there is no sales baseline yet, the
            # value of a normal order (avg units ordered x price).
            usual_order = g.loc[:i - 1].query("has_po")["ordered"].tail(4).mean()
            fallback = (usual_order if usual_order == usual_order else 0) * (r["price"] or 0)
            fired["po_stopped"] = dict(at_risk=b.get("expected", fallback))

        if b and enough_history:
            rank_worse = r["rank"] - b["rank"] if r["store_days"] else 0
            stock_ok = r["availability"] >= rd["min_availability"] if r["store_days"] else False
            # 3. Marketing: lost visibility while stock was fine.
            if stock_ok and rank_worse >= rd["min_positions"]:
                fired["rank_drop"] = dict(at_risk=0)
            # 4. KAM: sales collapsed but stock and rank don't explain it
            #    (or the product vanished from the export altogether).
            vanished = r["store_days"] == 0
            if vanished or (r["availability"] >= li["min_availability"]
                            and abs(rank_worse) < li["max_rank_change"]
                            and b["ratio"] <= li["max_sales_ratio"]):
                fired["listing_issue"] = dict(at_risk=0, vanished=bool(vanished))

        for d in DETECTORS:
            if d not in fired:
                run_len[d], run_lost[d] = 0, 0.0
                continue
            run_len[d] += 1
            lost = b.get("lost", 0.0)
            run_lost[d] += lost
            flagged_any[i] = True
            out.append({
                **key,
                "week": r["week"],
                "detector": d,
                "team": team_for(d, key["platform"]),
                "product_name": r["product_name"],
                "category": r["category"],
                "lost_inr": round(lost),
                "at_risk_inr": round(fired[d]["at_risk"]),
                "impact_inr": round(max(lost, fired[d]["at_risk"])),
                "weeks_running": run_len[d],
                "lost_so_far_inr": round(run_lost[d]),
                "sales_inr": r["sales_inr"],
                "units": r["units"],
                "stores": r["stores"],
                "expected_inr": round(b.get("expected", np.nan)) if b else np.nan,
                "sales_ratio": b.get("ratio", np.nan),
                "availability": r["availability"],
                "availability_before": b.get("avail", np.nan),
                "rank": r["rank"],
                "rank_before": b.get("rank", np.nan),
                "price": r["price"],
                "price_before": b.get("price", np.nan),
                "ordered": r["ordered"],
                "delivered": r["delivered"],
                "short_units": r["short_units"],
                "fill_rate": r["fill_rate"],
                "last_po_week": g.loc[:i][g.loc[:i, "has_po"]]["week"].max(),
                "vanished": fired[d].get("vanished", False),
            })
    return out


def _dedupe(flags: pd.DataFrame) -> pd.DataFrame:
    """If a line has a supply or PO problem, its sales drop is explained: don't
    also send the KAM a 'listing problem' for the same line."""
    supply_side = flags[flags["detector"].isin(["under_delivery", "po_stopped"])][KEY + ["week"]].drop_duplicates()
    supply_side["_explained"] = True
    flags = flags.merge(supply_side, on=KEY + ["week"], how="left")
    drop = (flags["detector"] == "listing_issue") & flags["_explained"].eq(True)
    return flags[~drop].drop(columns="_explained").reset_index(drop=True)
