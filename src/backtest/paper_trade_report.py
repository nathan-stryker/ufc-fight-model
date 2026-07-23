"""
Summarize data/paper_trades.csv: open bets awaiting settlement, and once
enough are settled, running ROI/profit and calibration (model probability vs.
actual outcome) by market -- the forward-looking counterpart to
run_backtest.py's historical report, for markets with no historical odds
data to backtest against.

Run: python -m src.backtest.paper_trade_report
"""
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
LOG_PATH = PROCESSED_DIR / "paper_trades.csv"


def main():
    if not LOG_PATH.exists():
        print(f"No paper trades logged yet -- run `python -m src.backtest.log_bet` first.")
        return

    df = pd.read_csv(LOG_PATH)
    pending = df[df["status"] == "pending"]
    settled = df[df["status"] != "pending"]

    print(f"{len(df)} bets logged total: {len(pending)} pending, {len(settled)} settled\n")

    if len(pending):
        print("=== Pending ===")
        print(pending[["bet_id", "event", "selection", "sportsbook", "odds_american", "model_prob", "edge"]].to_string(index=False))

    if len(settled) == 0:
        print("\nNo settled bets yet -- nothing to report on ROI/calibration until some fights happen.")
        return

    print("\n=== Settled: overall ===")
    decided = settled[settled["status"] != "push"]
    n = len(decided)
    win_rate = (decided["status"] == "won").mean() if n else float("nan")
    flat_total = decided["profit_units_flat"].sum()
    kelly_staked = decided["suggested_stake_units"].sum()
    kelly_total = decided["profit_units_kelly"].sum()
    print(f"n={n} (excl. pushes)  win_rate={win_rate:.1%}")
    print(f"flat:  total profit {flat_total:+.3f} units  (ROI {flat_total / n:+.1%} per bet)" if n else "")
    print(f"kelly: total profit {kelly_total:+.3f} units on {kelly_staked:.3f} staked  (ROI {kelly_total / kelly_staked:+.1%})" if kelly_staked else "")

    print("\n=== Settled: by market ===")
    by_market = decided.groupby("market").agg(
        n=("bet_id", "count"),
        win_rate=("status", lambda s: (s == "won").mean()),
        mean_edge=("edge", "mean"),
        flat_profit=("profit_units_flat", "sum"),
        kelly_profit=("profit_units_kelly", "sum"),
    )
    print(by_market.to_string())

    print("\n=== Calibration: model_prob vs actual outcome ===")
    decided = decided.copy()
    decided["won_flag"] = (decided["status"] == "won").astype(int)
    print(f"mean model_prob: {decided['model_prob'].mean():.3f}   actual win rate: {decided['won_flag'].mean():.3f}")
    print("(needs a few dozen+ settled bets before this is meaningful -- small samples are pure noise)")


if __name__ == "__main__":
    main()
