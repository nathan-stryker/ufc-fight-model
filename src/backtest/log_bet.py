"""
Log a single prop/moneyline bet you're considering, against the model's own
probability for that exact market -- the live, forward-looking counterpart to
the historical moneyline backtest (src/backtest/run_backtest.py), for markets
(method of victory, round totals) where no free historical odds dataset
exists. Run this once per bet you're weighing; settle it later with
settle_bet.py once the fight has happened, then use paper_trade_report.py to
see running calibration/ROI once enough bets have accumulated.

Run: python -m src.backtest.log_bet
"""
import csv
from datetime import datetime
from pathlib import Path

from src.backtest.odds_utils import KELLY_FRACTION, american_to_prob, devig_two_way, kelly_stake
from src.models.predict import predict_full

PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data" / "processed"
LOG_PATH = PROCESSED_DIR / "paper_trades.csv"

FIELDS = [
    "bet_id", "logged_at", "event", "fighter_a", "fighter_b", "scheduled_rounds",
    "market", "selection", "sportsbook", "odds_american", "other_side_odds_american",
    "model_prob", "implied_prob", "vig_free", "edge", "kelly_fraction", "suggested_stake_units",
    "status", "settled_at", "profit_units_flat", "profit_units_kelly", "notes",
]


def next_bet_id():
    if not LOG_PATH.exists():
        return 1
    with open(LOG_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    return (max((int(r["bet_id"]) for r in rows), default=0)) + 1


def prompt(text, cast=str, default=None, optional=False):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{text}{suffix}: ").strip()
        if not raw and optional:
            return None
        if not raw and default is not None:
            return default
        if not raw:
            continue
        try:
            return cast(raw)
        except ValueError:
            print(f"  couldn't parse as {cast.__name__}, try again")


def choose_method_prob(result, fighter_label, method_label):
    dist = result["method_given_a"] if fighter_label == "a" else result["method_given_b"]
    return dist[method_label]


def round_total_prob(result, over_line):
    """P(fight goes OVER over_line rounds), e.g. over_line=2.5 -> P(fight lasts into round 3+)."""
    n = int(over_line)  # 2.5 -> 2
    p_finish_by_n = result["p_finish"] * sum(
        p for r, p in result["round_given_finish"].items() if r <= n
    )
    return 1.0 - p_finish_by_n


def main():
    print("=== Log a paper-trade prop bet ===\n")
    event = prompt("Event name")
    fighter_a = prompt("Fighter A name (as in fighters.csv)")
    fighter_b = prompt("Fighter B name")
    scheduled_rounds = prompt("Scheduled rounds", int, default=3)

    result = predict_full(fighter_a, fighter_b, scheduled_rounds=scheduled_rounds)
    print(f"\n{result['name_a']}: {result['prob_a_wins']:.1%}  |  {result['name_b']}: {result['prob_b_wins']:.1%}")
    print(f"Method (overall): dec={result['method']['dec']:.1%}  ko={result['method']['ko']:.1%}  sub={result['method']['sub']:.1%}")
    print(f"Finish probability: {result['p_finish']:.1%}\n")

    print("Market: 1) winner  2) method of victory  3) round total (over/under)")
    market_choice = prompt("Choose 1/2/3", int)

    if market_choice == 1:
        market = "winner"
        side = prompt(f"Betting on which fighter, 'a' ({result['name_a']}) or 'b' ({result['name_b']})")
        model_prob = result["prob_a_wins"] if side == "a" else result["prob_b_wins"]
        selection = result["name_a"] if side == "a" else result["name_b"]

    elif market_choice == 2:
        market = "method"
        side = prompt(f"Which fighter, 'a' ({result['name_a']}) or 'b' ({result['name_b']})")
        method_label = prompt("Method: dec / ko / sub")
        model_prob = choose_method_prob(result, side, method_label)
        name = result["name_a"] if side == "a" else result["name_b"]
        selection = f"{name} by {method_label}"

        if method_label != "dec":
            round_pick = prompt("Pin an exact round too? (blank for any round)", int, optional=True)
            if round_pick:
                round_dist = result["round_given_win_method"][side][method_label]
                round_prob = round_dist[round_pick - 1] if 0 < round_pick <= len(round_dist) else 0.0
                model_prob *= round_prob  # joint P(fighter wins by method AND round), not just P(method)
                selection += f", Round {round_pick}"

    elif market_choice == 3:
        market = "round_total"
        line = prompt("Line, e.g. 2.5 for 'over/under 2.5 rounds'", float)
        direction = prompt("over or under")
        p_over = round_total_prob(result, line)
        model_prob = p_over if direction == "over" else 1.0 - p_over
        selection = f"{direction} {line}"

    else:
        raise SystemExit("invalid market choice")

    sportsbook = prompt("Sportsbook")
    odds_american = prompt("Odds you're getting (American, e.g. -150 or +130)", float)
    other_side_odds = prompt("Other side's odds, if known (for de-vig; blank to skip)", float, optional=True)

    implied_prob = american_to_prob(odds_american)
    if other_side_odds is not None:
        other_implied = american_to_prob(other_side_odds)
        vig_free_prob, _ = devig_two_way(implied_prob, other_implied)
        vig_free = True
    else:
        vig_free_prob = implied_prob
        vig_free = False

    edge = model_prob - vig_free_prob
    stake = kelly_stake(model_prob, odds_american)

    print(f"\n--- {selection} @ {odds_american:+.0f} ({sportsbook}) ---")
    print(f"Model probability:        {model_prob:.1%}")
    print(f"Market implied ({'vig-free' if vig_free else 'raw, has vig'}): {vig_free_prob:.1%}")
    print(f"Edge:                      {edge:+.1%}")
    print(f"Suggested stake ({KELLY_FRACTION:.0%} Kelly): {stake:.3f} units")

    if prompt("\nLog this bet? y/n", default="y").lower() != "y":
        print("Not logged.")
        return

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "bet_id": next_bet_id(), "logged_at": datetime.now().isoformat(timespec="seconds"),
            "event": event, "fighter_a": result["name_a"], "fighter_b": result["name_b"],
            "scheduled_rounds": scheduled_rounds, "market": market, "selection": selection,
            "sportsbook": sportsbook, "odds_american": odds_american,
            "other_side_odds_american": other_side_odds if other_side_odds is not None else "",
            "model_prob": round(model_prob, 4), "implied_prob": round(implied_prob, 4),
            "vig_free": vig_free, "edge": round(edge, 4), "kelly_fraction": KELLY_FRACTION,
            "suggested_stake_units": round(stake, 4), "status": "pending", "settled_at": "",
            "profit_units_flat": "", "profit_units_kelly": "", "notes": "",
        })
    print(f"Logged -> {LOG_PATH}")


if __name__ == "__main__":
    main()
