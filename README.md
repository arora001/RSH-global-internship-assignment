# Joy quick commerce: Monday brief

The Quick Commerce Manager's Monday brief: the problems from last week's Blinkit, Zepto and Instamart exports,
ranked by rupees, with a message for each team (Supply, each platform's account manager, Marketing).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

streamlit run app.py              # the web app (uses joy_qcom_data/ or upload your own 4 CSVs)
python scripts/make_brief.py      # same brief as files in output/brief_<monday>/
pytest -q                         # checks the 3 past incidents get flagged in week 1
```

## What's where

| Path | What it does |
|---|---|
| `pipeline/clean.py` | Reads the 4 CSVs, fixes the mess, logs every fix |
| `pipeline/metrics.py` | One row per app × city/warehouse × product × week |
| `pipeline/detect.py` | The 4 checks + ₹ estimate |
| `pipeline/brief.py` | Groups, ranks and caps issues; writes the team messages; backtest |
| `config.yaml` | All thresholds (also adjustable in the app sidebar) |
| `app.py` | Streamlit front end |
| `output/brief_2026-11-16/` | Monday 16 Nov output |
| `NOTE.md` | Short note: what I flagged, data mess, AI use |

## The four checks

| Check | Fires when | Sent to |
|---|---|---|
| Under-delivery | fill rate < 80% and ≥ 20 units short | Supply |
| Warehouse stopped ordering | no PO for a product ordered in ≥ 3 of the last 4 weeks | Platform account manager |
| Search rank drop | rank ≥ 3 places worse while availability ≥ 80% | Marketing |
| Listing problem | sales < 40% of normal while stock and rank are fine | Platform account manager |

"Normal" means that product line's last 4 weeks that were *not* flagged, so a long-running problem doesn't become the baseline.
