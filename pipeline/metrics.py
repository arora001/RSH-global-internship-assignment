"""Turn daily rows into one row per (platform, city, warehouse, product, week).

In this data every platform has exactly one warehouse per city, so a
warehouse × SKU line is the same thing as a city × SKU line on that app.
That lets supply problems (warehouse) and sales problems (city) share one key.
"""

import pandas as pd

from .clean import CleanData

KEY = ["platform", "city", "warehouse_id", "sku_code"]


def weekly_fact(cd: CleanData) -> pd.DataFrame:
    s = cd.sales
    sales_w = (s.groupby(KEY + ["week"])
                .agg(sales_inr=("sales_inr", "sum"),
                     units=("units_sold", "sum"),
                     store_days=("sales_inr", "size"),
                     stores=("dark_store_id", "nunique"),
                     availability=("availability_pct", "mean"),
                     rank=("search_rank", "mean"),
                     price=("selling_price_inr", "mean"))
                .reset_index())

    wh = (cd.stores.groupby("warehouse_id")
          .agg(platform=("platform", "first"), city=("city", lambda c: c.mode().iat[0]))
          .reset_index())
    po_w = (cd.po.groupby(["warehouse_id", "sku_code", "week"])
            .agg(ordered=("qty_ordered", "sum"), delivered=("qty_delivered", "sum"))
            .reset_index()
            .merge(wh, on="warehouse_id", how="inner"))

    # Full grid: every key that appears anywhere x every week, so a missing PO
    # or a product that vanished from the export shows up as a gap, not as nothing.
    keys = pd.concat([sales_w[KEY], po_w[KEY]]).drop_duplicates()
    weeks = pd.DataFrame({"week": sorted(set(sales_w["week"]) | set(po_w["week"]))})
    grid = keys.merge(weeks, how="cross")

    f = (grid.merge(sales_w, on=KEY + ["week"], how="left")
             .merge(po_w, on=KEY + ["week"], how="left"))
    for c in ["sales_inr", "units", "store_days", "stores", "ordered", "delivered"]:
        f[c] = f[c].fillna(0)
    f["has_po"] = f["ordered"] > 0
    f["fill_rate"] = (f["delivered"] / f["ordered"]).where(f["has_po"])
    f["short_units"] = (f["ordered"] - f["delivered"]).clip(lower=0)

    names = cd.products.drop_duplicates("sku_code").set_index("sku_code")[["product_name", "category"]]
    f = f.join(names, on="sku_code")
    return f.sort_values(KEY + ["week"]).reset_index(drop=True)
