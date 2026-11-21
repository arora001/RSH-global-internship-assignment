"""Load the four CSV exports and clean them.

Every fix is written to a data-quality log so the manager (and we) can see
what was changed instead of it happening silently.
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

FILES = {
    "sales": "daily_sales.csv",
    "stores": "dark_stores.csv",
    "products": "products.csv",
    "po": "purchase_orders.csv",
}

# Spellings seen in the exports (plus a few obvious ones) mapped to one name per city.
CITY_ALIASES = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "delhi": "Delhi NCR",
    "new delhi": "Delhi NCR",
    "delhi ncr": "Delhi NCR",
    "gurgaon": "Delhi NCR",
    "gurugram": "Delhi NCR",
    "noida": "Delhi NCR",
    "bombay": "Mumbai",
    "mumbai": "Mumbai",
    "calcutta": "Kolkata",
    "kolkata": "Kolkata",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
}

PLATFORM_ALIASES = {
    "blinkit": "Blinkit",
    "zepto": "Zepto",
    "instamart": "Instamart",
    "swiggy instamart": "Instamart",
}


@dataclass
class CleanData:
    sales: pd.DataFrame
    stores: pd.DataFrame
    products: pd.DataFrame
    po: pd.DataFrame
    dq: list = field(default_factory=list)  # one dict per issue found

    @property
    def dq_table(self) -> pd.DataFrame:
        return pd.DataFrame(self.dq, columns=["file", "issue", "rows", "action"])


def read_raw(sources: dict) -> dict:
    """sources maps 'sales'/'stores'/'products'/'po' to a path or an uploaded file object.

    Everything is read as text first: product IDs are numbers on Blinkit but
    strings on Zepto/Instamart, and we want to decide types ourselves.
    """
    return {k: pd.read_csv(v, dtype=str) for k, v in sources.items()}


def read_dir(data_dir: Path) -> dict:
    return read_raw({k: Path(data_dir) / f for k, f in FILES.items()})


def _strip(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df


def _norm_platform(s: pd.Series) -> pd.Series:
    return s.str.lower().map(PLATFORM_ALIASES).fillna(s)


def _monday(d: pd.Series) -> pd.Series:
    return (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.normalize()


def clean(raw: dict) -> CleanData:
    dq = []

    def log(file, issue, rows, action):
        if rows:
            dq.append({"file": file, "issue": issue, "rows": int(rows), "action": action})

    # ---------- dark_stores ----------
    stores = _strip(raw["stores"])
    raw_city = raw["stores"]["city"]
    stores["platform"] = _norm_platform(stores["platform"])
    stores["city"] = stores["city"].str.lower().map(CITY_ALIASES).fillna(stores["city"].str.title())
    changed = raw_city != stores["city"]
    if changed.any():
        examples = sorted({f"'{a}'→{b}" for a, b in zip(raw_city[changed], stores["city"][changed])})
        log("dark_stores", "City written in different ways: " + ", ".join(examples), changed.sum(),
            "Mapped every spelling to one city name")
    dup = stores.duplicated("dark_store_id", keep="last")
    log("dark_stores", "Same dark_store_id listed twice", dup.sum(), "Kept the last row")
    stores = stores[~dup]
    stores["opened_date"] = pd.to_datetime(stores["opened_date"], errors="coerce")

    # ---------- products ----------
    products = _strip(raw["products"])
    products["platform"] = _norm_platform(products["platform"])
    products["mrp_inr"] = pd.to_numeric(products["mrp_inr"], errors="coerce")
    dup = products.duplicated(["platform", "platform_product_id"], keep="last")
    log("products", "Same platform product ID listed twice", dup.sum(), "Kept the last row")
    products = products[~dup]
    id_styles = products.groupby("platform")["platform_product_id"].apply(
        lambda s: "numeric" if s.str.fullmatch(r"\d+").all() else "text")
    if id_styles.nunique() > 1:
        log("products", "Product IDs differ by app (" + ", ".join(f"{p}: {t}" for p, t in id_styles.items())
            + "), so a numeric read breaks the join", len(products), "Read all IDs as text before joining")

    # ---------- daily_sales ----------
    sales = _strip(raw["sales"])
    n0 = len(sales)
    sales["platform"] = _norm_platform(sales["platform"])
    dup = sales.duplicated()
    log("daily_sales", "Exact duplicate rows (same store, product, day, numbers)", dup.sum(), "Dropped duplicates")
    sales = sales[~dup]

    sales["date"] = pd.to_datetime(sales["date"], errors="coerce")
    num_cols = ["availability_pct", "units_sold", "selling_price_inr", "sales_inr", "search_rank"]
    for c in num_cols:
        sales[c] = pd.to_numeric(sales[c], errors="coerce")
    bad = sales["date"].isna() | sales[num_cols].isna().any(axis=1)
    log("daily_sales", "Unreadable date or number", bad.sum(), "Dropped those rows")
    sales = sales[~bad]

    keycols = ["date", "platform", "dark_store_id", "platform_product_id"]
    dup = sales.duplicated(keycols, keep="last")
    log("daily_sales", "Same store/product/day reported twice with different numbers", dup.sum(), "Kept the last row")
    sales = sales[~dup]

    out = ~sales["availability_pct"].between(0, 100)
    log("daily_sales", "Availability outside 0-100%", out.sum(), "Clipped to 0-100")
    sales["availability_pct"] = sales["availability_pct"].clip(0, 100)

    mismatch = (sales["units_sold"] * sales["selling_price_inr"] - sales["sales_inr"]).abs() > 1
    log("daily_sales", "sales_inr ≠ units × price", mismatch.sum(), "Recomputed sales_inr")
    sales.loc[mismatch, "sales_inr"] = sales["units_sold"] * sales["selling_price_inr"]

    sales = sales.merge(products[["platform", "platform_product_id", "sku_code", "product_name", "category", "mrp_inr"]],
                        on=["platform", "platform_product_id"], how="left")
    unmapped = sales["sku_code"].isna()
    log("daily_sales", "Product ID not found in products.csv", unmapped.sum(), "Dropped those rows")
    sales = sales[~unmapped]

    sales = sales.merge(stores[["dark_store_id", "city", "warehouse_id", "opened_date"]], on="dark_store_id", how="left")
    unmapped = sales["warehouse_id"].isna()
    log("daily_sales", "Dark store not found in dark_stores.csv", unmapped.sum(), "Dropped those rows")
    sales = sales[~unmapped]

    sales["week"] = _monday(sales["date"])
    start = sales["date"].min()
    new_stores = stores[stores["opened_date"] > start]
    log("dark_stores", f"{len(new_stores)} dark stores opened during the data window, so raw weekly totals grow "
        "on their own", len(new_stores), "Compared sales per store-day, not raw totals")

    # ---------- purchase_orders ----------
    po = _strip(raw["po"])
    po["platform"] = _norm_platform(po["platform"])
    dup = po.duplicated("po_id", keep="last")
    log("purchase_orders", "Same po_id listed twice", dup.sum(), "Kept the last row")
    po = po[~dup]
    po["po_date"] = pd.to_datetime(po["po_date"], errors="coerce")
    po["delivery_date"] = pd.to_datetime(po["delivery_date"], errors="coerce")
    for c in ["qty_ordered", "qty_delivered"]:
        po[c] = pd.to_numeric(po[c], errors="coerce")
    bad = po["po_date"].isna() | po["qty_ordered"].isna() | po["qty_delivered"].isna()
    log("purchase_orders", "Unreadable date or quantity", bad.sum(), "Dropped those rows")
    po = po[~bad]
    over = po["qty_delivered"] > po["qty_ordered"]
    log("purchase_orders", "Delivered more than ordered", over.sum(), "Capped delivered at ordered")
    po["qty_delivered"] = po[["qty_delivered", "qty_ordered"]].min(axis=1)
    po["week"] = _monday(po["po_date"])

    dq.insert(0, {"file": "daily_sales", "issue": f"Rows read: {n0:,}; rows used after cleaning: {len(sales):,}",
                  "rows": len(sales), "action": "—"})
    return CleanData(sales=sales.reset_index(drop=True), stores=stores.reset_index(drop=True),
                     products=products.reset_index(drop=True), po=po.reset_index(drop=True), dq=dq)
