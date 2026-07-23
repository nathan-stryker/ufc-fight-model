"""
Mark a logged paper-trade bet (src/backtest/log_bet.py) as won/lost/push once
the actual fight has happened, and compute its realized profit both at flat
1-unit stake and at the fractional-Kelly stake that was suggested at log time.

Run: python -m src.backtest.settle_bet <bet_id> won|lost|push ["optional note"]
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

from src.backtest.odds_utils import profit_units

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
LOG_PATH = PROCESSED_DIR / "paper_trades.csv"


def main():
    if len(sys.argv) < 3:
        raise SystemExit(f"usage: python -m src.backtest.settle_bet <bet_id> won|lost|push [note]")
    bet_id, result = sys.argv[1], sys.argv[2].lower()
    note = sys.argv[3] if len(sys.argv) > 3 else ""
    if result not in ("won", "lost", "push"):
        raise SystemExit("result must be one of: won, lost, push")

    with open(LOG_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []

    found = False
    for row in rows:
        if row["bet_id"] != bet_id:
            continue
        found = True
        odds = float(row["odds_american"])
        stake = float(row["suggested_stake_units"]) if row["suggested_stake_units"] else 0.0

        if result == "push":
            flat_profit, kelly_profit = 0.0, 0.0
        else:
            won = result == "won"
            flat_profit = profit_units(won, odds, stake=1.0)
            kelly_profit = profit_units(won, odds, stake=stake)

        row["status"] = result
        row["settled_at"] = datetime.now().isoformat(timespec="seconds")
        row["profit_units_flat"] = round(flat_profit, 4)
        row["profit_units_kelly"] = round(kelly_profit, 4)
        if note:
            row["notes"] = note

        print(f"Settled bet #{bet_id} ({row['selection']}): {result}")
        print(f"  flat profit:  {flat_profit:+.3f} units")
        print(f"  kelly profit: {kelly_profit:+.3f} units (staked {stake:.3f})")

    if not found:
        raise SystemExit(f"bet_id {bet_id} not found in {LOG_PATH}")

    with open(LOG_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
