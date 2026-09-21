"""Transfer-fee arithmetic, kept separate so the constants are easy to point at."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# R11 - the rate and its two bounds.
FEE_RATE = Decimal("0.01")
MIN_FEE = Decimal("0.10")
MAX_FEE = Decimal("5.00")


def transfer_fee(amount: Decimal) -> Decimal:
    """R11 - 1% of the amount, floored at 0.10, capped at 5.00, rounded to 2 dp."""
    raw = amount * FEE_RATE
    # R11 - the floor and the cap both apply before rounding.
    bounded = max(MIN_FEE, min(raw, MAX_FEE))
    return bounded.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
