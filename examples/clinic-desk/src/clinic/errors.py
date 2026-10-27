class ClinicError(Exception):
    """Base type for refusals the desk shows to the caller."""


class UnderagePatient(ClinicError):
    pass


class DuplicatePatient(ClinicError):
    pass


class DailyLimitExceeded(ClinicError):
    pass


class SlotTaken(ClinicError):
    pass


class ClinicianUnavailable(ClinicError):
    """Defined, but the scheduler never raises it."""
