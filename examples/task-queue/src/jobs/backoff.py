MAX_ATTEMPTS = 4
MAX_DELAY = 120


def retry_delay(attempt: int) -> float:
    return min(2**attempt, MAX_DELAY)
