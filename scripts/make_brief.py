"""Write Monday's brief to files (no browser needed).

    python scripts/make_brief.py                 # latest week in the data
    python scripts/make_brief.py --week 2026-10-12 --data path/to/csvs

Creates output/brief_<monday>/ with:
    brief.md            manager summary + every team message + backtest + data-quality log
    <team>.txt          one WhatsApp-ready message per team
    issues.csv          the issues behind the brief (for anyone who wants the numbers)
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import DATA_DIR, ROOT, load_config  # noqa: E402
from pipeline.brief import (analyse_dir, backtest, issues_for_week, manager_text,  # noqa: E402
                            team_messages, week_summary)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DATA_DIR), help="folder with the four CSVs")
    ap.add_argument("--week", help="Monday of the sales week (default: latest in data)")
    ap.add_argument("--out", default=str(ROOT / "output"))
    args = ap.parse_args()

    cfg = load_config()
    res = analyse_dir(Path(args.data), cfg)
    week = pd.Timestamp(args.week) if args.week else res.fact["week"].max()
    monday = (week + pd.Timedelta(7, "D")).strftime("%Y-%m-%d")

    shown, watch = issues_for_week(res.flags, week, cfg, res.fact)
    summary = week_summary(res.fact, week)
    msgs = team_messages(shown, week)

    out = Path(args.out) / f"brief_{monday}"
    out.mkdir(parents=True, exist_ok=True)
    for team, text in msgs.items():
        (out / (re.sub(r"\W+", "_", team).strip("_").lower() + ".txt")).write_text(text + "\n")
    cols = ["team", "status", "impact_inr", "lost_inr", "lost_so_far_inr", "title", "detail", "action"]
    shown[cols].to_csv(out / "issues.csv", index=False)

    md = [f"# Joy quick commerce: Monday brief {monday}", "",
          "## Summary (Quick Commerce Manager)", "", "```", manager_text(shown, watch, summary, week), "```", ""]
    for team, text in msgs.items():
        md += [f"## {team}", "", "```", text, "```", ""]
    md += ["## Would this have caught the last two months' problems?", "",
           backtest(res.flags, cfg).to_markdown(index=False), "",
           "## Data quality: what was fixed before analysis", "",
           res.data.dq_table.to_markdown(index=False), ""]
    (out / "brief.md").write_text("\n".join(md))

    print(manager_text(shown, watch, summary, week))
    print(f"\nWrote {out}/ ({len(msgs)} team messages, {len(shown)} issues)")


if __name__ == "__main__":
    main()
