# Joy quick commerce: Monday brief 2026-11-16

## Summary (Quick Commerce Manager)

```
*Joy quick commerce: Monday 16 Nov*
Last week sales ₹19.4L (-11% vs previous week; -12% per dark store-day)
Note: selling prices moved +8% across all apps this week (a platform-wide discount started or ended), so some of the sales change is price, not a problem.
4 issues need action, worth ~₹50,325/week in sales.

1. [Supply] Blinkit Delhi NCR warehouse (BLK-WH-03): we delivered only 48% of the order for 2 products (~₹24,114/wk, new)
2. [Zepto KAM] Zepto Mumbai warehouse (ZEP-WH-08) has stopped ordering Joy Almond Milk Lotion 200ml (~₹13,468/wk, week 2)
3. [Marketing] Zepto Bengaluru: Joy Neem Face Wash 100ml fell to #13 in search (normally #3) (~₹9,857/wk, week 5)
4. [Zepto KAM] Zepto Kolkata: Joy Vitamin C Serum 30ml sales down 91% while stock and search rank look normal (~₹2,886/wk, new)
```

## Supply

```
*Supply: 1 thing to act on* (Joy QC brief for Mon 16 Nov, sales week 9 Nov–15 Nov)

*1. Blinkit Delhi NCR warehouse (BLK-WH-03): we delivered only 48% of the order for 2 products* [NEW, ~₹24,114/week]
Joy Almond Milk Lotion 400ml: ordered 120, delivered 60 (60 short); Joy Night Repair Cream 50ml: ordered 72, delivered 33 (39 short). Dark-store availability for these is 64% (normally ~91%). New this week.
👉 Ship the missing 99 units to BLK-WH-03 this week. If we are short of stock ourselves, tell the QC manager today so other cities can be prioritised.
```

## Zepto KAM

```
*Zepto KAM: 2 things to act on* (Joy QC brief for Mon 16 Nov, sales week 9 Nov–15 Nov)

*1. Zepto Mumbai warehouse (ZEP-WH-08) has stopped ordering Joy Almond Milk Lotion 200ml* [WEEK 2, ~₹13,468/week]
No purchase order for 2 weeks; last order was the week of 26 Oct. Availability in Mumbai dark stores is 16% (normally ~91%) and will keep falling.
👉 Please check why ZEP-WH-08 stopped ordering and raise a PO this week; confirm the item hasn't been blocked or delisted in your system.

*2. Zepto Kolkata: Joy Vitamin C Serum 30ml sales down 91% while stock and search rank look normal* [NEW, ~₹2,886/week]
Sold 1 unit this week vs ~12 normally. Availability 89%, search rank #4 (normal #4), so it is not a stock or visibility problem. New this week.
👉 Please check the listing in Kolkata is live and buyable (product page, price, add-to-cart) and tell us if anything changed on your side.
```

## Marketing

```
*Marketing: 1 thing to act on* (Joy QC brief for Mon 16 Nov, sales week 9 Nov–15 Nov)

*1. Zepto Bengaluru: Joy Neem Face Wash 100ml fell to #13 in search (normally #3)* [WEEK 5, ~₹9,857/week]
Stock is fine (89% availability) but sales are 58% below normal: about ₹9,857 lost this week, ₹42,894 since it started. This is week 5 in a row.
👉 Look at sponsored search / ads for 'face wash' on Zepto in Bengaluru, and check if a competitor launched or ran a promotion there.
```

## Would this have caught the last two months' problems?

| incident                                                                  | owner         | problem started (data week)   | flagged in brief of   |   weeks to flag | actually noticed after   |
|:--------------------------------------------------------------------------|:--------------|:------------------------------|:----------------------|----------------:|:-------------------------|
| Blinkit Bengaluru: we delivered ~half of 6 products' orders               | Supply        | 21 Sep                        | 28 Sep                |               1 | ~5 weeks                 |
| Instamart Hyderabad: warehouse stopped ordering sunscreen                 | Instamart KAM | 14 Sep                        | 21 Sep                |               1 | ~3 weeks                 |
| Zepto Bengaluru: best-selling face wash fell from ~3rd to ~13th in search | Marketing     | 12 Oct                        | 19 Oct                |               1 | ~4 weeks                 |

## Data quality: what was fixed before analysis

| file        | issue                                                                                                                                    |   rows | action                                       |
|:------------|:-----------------------------------------------------------------------------------------------------------------------------------------|-------:|:---------------------------------------------|
| daily_sales | Rows read: 186,285; rows used after cleaning: 185,520                                                                                    | 185520 | —                                            |
| dark_stores | City written in different ways: 'Bangalore'→Bengaluru, 'Delhi'→Delhi NCR, 'HYDERABAD'→Hyderabad, 'New Delhi'→Delhi NCR, 'mumbai '→Mumbai |     64 | Mapped every spelling to one city name       |
| products    | Product IDs differ by app (Blinkit: numeric, Instamart: text, Zepto: text), so a numeric read breaks the join                            |     45 | Read all IDs as text before joining          |
| daily_sales | Exact duplicate rows (same store, product, day, numbers)                                                                                 |    765 | Dropped duplicates                           |
| dark_stores | 51 dark stores opened during the data window, so raw weekly totals grow on their own                                                     |     51 | Compared sales per store-day, not raw totals |
