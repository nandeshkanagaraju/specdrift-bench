"""Late-fee arithmetic, kept separate so the constants are easy to point at."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# R13 - the daily rate and the cap.
DAILY_LATE_FEE = Decimal("0.50")
LATE_FEE_CAP = Decimal("20.00")


def late_fee(days_late: int) -> Decimal:
    """R13 - 0.50 per day late, capped at 20.00, rounded to 2 decimal places."""
    if days_late <= 0:
        return Decimal("0.00")

    raw = DAILY_LATE_FEE * days_late
    # R13 - the cap applies before rounding.
    capped = min(raw, LATE_FEE_CAP)
    return capped.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
