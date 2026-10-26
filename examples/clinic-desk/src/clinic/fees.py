"""Cancellation money. The late fee is lower than the spec requires."""

from datetime import datetime, timedelta

from clinic.limits import CANCEL_WINDOW_HOURS, EARLY_CANCEL_FEE, LATE_CANCEL_FEE, NO_SHOW_FEE


def cancellation_fee(slot_start: datetime, cancelled_at: datetime) -> float:
    """Fee owed when a patient cancels, in currency units."""
    if cancelled_at > slot_start - timedelta(hours=CANCEL_WINDOW_HOURS):
        return LATE_CANCEL_FEE
    return EARLY_CANCEL_FEE


def no_show_fee() -> float:
    return NO_SHOW_FEE
