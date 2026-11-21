# Note

## What I flagged, and why

Each of the three past incidents is a different failure, and each belongs to a different team, so I built one check per failure instead of a general "something dropped" alert:

- **Under-delivery → Supply.** We delivered < 80% of a PO line and were ≥ 20 units short. The message names the warehouse, products and units, because that's how Supply thinks.
- **Warehouse stopped ordering → the platform's account manager.** There was no PO for a product the warehouse had ordered in ≥ 3 of the last 4 weeks.
- **Search rank drop → Marketing.** Average rank was ≥ 3 places worse *while availability was ≥ 80%*. If stock was low, the drop isn't a visibility problem.
- **Listing problem → the platform's account manager.** Sales were below 40% of normal while stock and rank were both fine. I added this after finding Zepto Kolkata's Vitamin C serum selling 1 unit in the last week with ~89% availability and its usual rank.

"Normal" is that product line's last 4 weeks that were *not* flagged. Without this, the Zepto rank drop would have become the baseline after a month and stopped being flagged. Every issue gets a rough ₹/week: the bigger of the sales already lost and the sales at risk (the value of units we didn't deliver, or a normal week of sales when a warehouse stops ordering). Issues are sorted by that figure. Anything under ₹2,000/week goes to a watchlist, and at most 10 are sent.

Replaying the data week by week, all three past incidents are flagged in their first week. The tool would have caught them on 28 Sep, 21 Sep and 19 Oct, instead of 3–5 weeks later. Across the ten Mondays it sends 0–4 issues a week. **For 16 Nov it sends 4:**
1. Blinkit Delhi under-delivered 2 products (Supply).
2. Zepto Mumbai stopped ordering Almond Lotion 200ml (Zepto account manager).
3. The Zepto Bengaluru face wash is still at #13 in search, now in its 5th week (Marketing).
4. The Zepto Kolkata serum listing problem (Zepto account manager).

## What was messy, and what I did

- **765 exact duplicate rows** in daily_sales: dropped.
- **City names written 5 different ways** (Bangalore/Bengaluru, "mumbai " with a trailing space, HYDERABAD, Delhi/New Delhi/Delhi NCR): mapped to one name per city.
- **Product IDs** are numbers on Blinkit but text on Zepto/Instamart, so everything is read as text before joining.
- **51 dark stores opened during the 10 weeks**, so raw weekly totals rise on their own: I compare sales per store-day.
- **Prices changed for everything at once.** The selling price was ~8% below MRP, then ~15% below during the festive period (19 Oct – 8 Nov), and back to ~8% on 9 Nov. That makes last week look −12% overall. The brief shows this as context instead of flagging every product, and a price change only appears in an alert if the product moved differently from the rest of the app.
- **Sunscreen sales dipped seasonally** in November (to ~50% of normal in a few cities). These are small and stay below the thresholds on purpose.
- **Checked and found clean:** sales_inr = units × price on every row, every product and store joins, delivered ≤ ordered.

**Assumptions:**
- Each app has one warehouse per city (true in this data), so a warehouse problem maps to that city's dark stores.
- "Platform account manager" means the person at Blinkit/Zepto/Instamart.
- Lost sales are a rough estimate (normal ₹ per store-day × store-days − actual), not a forecast.

## How I used AI tools

- **ChatGPT:** I gave it the brief and the data at the start and asked for different ways to approach the problem.
- **Claude Code:** profiling the data (duplicates, city names, finding where each incident shows up), writing most of the pandas and Streamlit code, and drafting this note.

**What I checked myself:**
- Each of the three incidents in a pivot, to confirm the week it starts.
- The thresholds, by looking at which weeks they would flag.
- One ₹ estimate by hand: the Zepto Bengaluru face wash lost ₹9,857 last week, which matches the tool.
- That the festive price change is the same across all products and apps, before treating it as context and not a problem.

---

### Appendix: how I got here (my working notes)

So first of all I started and read it all, in the first iteration (before I know what to do I read the problem which was messy data causing delay in problem identification then I read the proposed solution to this a Quick Commerce Manager and I thought of a webpage that can just present all the numbers in a visually appealing way, predict the problem based on my assumptions like defining some thresholds and then just looking for violations and make them easy to report without using an expansive llm for that, just define tables joins indexes and defining some editable constraints,,,

Now the second step was to look for solutions via llm's and just ask chatgpt what could be done -> so I gave the data and the pdf file and asked how I should I approach this what could be different ways of approaching this kind of problem and look through solutions
