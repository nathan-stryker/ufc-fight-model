"""Shared odds math for the paper-trading tools (log_bet.py / settle_bet.py / paper_trade_report.py)."""

KELLY_FRACTION = 0.25


def american_to_decimal(american: float) -> float:
    return 1 + american / 100 if american > 0 else 1 - 100 / american


def american_to_prob(american: float) -> float:
    """Raw implied probability from one side's American odds -- includes the vig."""
    dec = american_to_decimal(american)
    return 1.0 / dec


def devig_two_way(prob_a: float, prob_b: float) -> tuple[float, float]:
    """Remove the bookmaker's overround, given both sides' raw implied probabilities."""
    overround = prob_a + prob_b
    return prob_a / overround, prob_b / overround


def kelly_stake(model_prob: float, american: float, fraction: float = KELLY_FRACTION) -> float:
    """Fractional-Kelly stake as a fraction of bankroll, for a bet at these American odds."""
    dec = american_to_decimal(american)
    b = dec - 1.0
    full_kelly = (model_prob * (b + 1) - 1) / b
    return max(0.0, fraction * full_kelly)


def profit_units(won: bool, american: float, stake: float = 1.0) -> float:
    if won:
        return stake * (american_to_decimal(american) - 1.0)
    return -stake
