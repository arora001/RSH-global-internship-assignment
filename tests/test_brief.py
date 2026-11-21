"""Checks that the tool would have caught the three incidents from the brief in
their first week, and that Monday 16 Nov's brief is short and contains the live issues."""

import pandas as pd
import pytest

from pipeline import DATA_DIR, load_config
from pipeline.brief import analyse_dir, backtest, issues_for_week


@pytest.fixture(scope="module")
def res():
    return analyse_dir(DATA_DIR, load_config())


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_cleaning_fixed_known_mess(res):
    cities = set(res.data.stores["city"])
    assert cities == {"Bengaluru", "Mumbai", "Delhi NCR", "Hyderabad", "Pune", "Kolkata"}
    assert not res.data.sales.duplicated(["date", "dark_store_id", "platform_product_id"]).any()
    assert res.data.sales["sku_code"].notna().all()


def test_known_incidents_flagged_in_first_week(res, cfg):
    bt = backtest(res.flags, cfg)
    assert (bt["weeks to flag"] == 1).all(), bt.to_string()


def test_monday_16_nov_brief(res, cfg):
    shown, _ = issues_for_week(res.flags, "2026-11-09", cfg, res.fact)
    assert len(shown) <= cfg["brief"]["max_issues"]
    got = {(r.detector, r.warehouse_id) for r in shown.itertuples()}
    assert ("under_delivery", "BLK-WH-03") in got      # Blinkit Delhi short delivery
    assert ("po_stopped", "ZEP-WH-08") in got          # Zepto Mumbai stopped ordering lotion
    assert ("listing_issue", "ZEP-WH-12") in got       # Zepto Kolkata serum sales collapse
    assert ("rank_drop", "ZEP-WH-07") in got           # Zepto Bengaluru face wash still at #13
    assert shown["impact_inr"].is_monotonic_decreasing


def test_no_week_is_noisy(res, cfg):
    for w in res.fact["week"].unique():
        shown, _ = issues_for_week(res.flags, pd.Timestamp(w), cfg)
        assert len(shown) <= cfg["brief"]["max_issues"]
