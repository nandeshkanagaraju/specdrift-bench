"""Booking. Age, slot length, daily cap, and audit order drift from the spec."""

from datetime import datetime

from clinic.errors import DailyLimitExceeded, DuplicatePatient, SlotTaken, UnderagePatient
from clinic.limits import MAX_PER_DAY, MIN_AGE, SLOT_MINUTES
from clinic.models import Appointment, AuditEntry, Clinician, DeskState, Patient


class Desk:
    def __init__(self) -> None:
        self.state = DeskState()

    def register(self, email: str, name: str, age: int) -> Patient:
        if age < MIN_AGE:
            raise UnderagePatient(f"{name} is {age}")
        if email in self.state.patients:
            raise DuplicatePatient(email)
        patient = Patient(email=email, name=name, age=age)
        self.state.patients[email] = patient
        return patient

    def book(self, email: str, clinician: Clinician, start: datetime) -> Appointment:
        same_day = [
            item
            for item in self.state.appointments
            if item.patient_email == email and item.start.date() == start.date()
        ]
        if len(same_day) >= MAX_PER_DAY:
            raise DailyLimitExceeded(email)

        taken = any(
            item.clinician_id == clinician.id and item.start == start
            for item in self.state.appointments
        )
        if taken:
            raise SlotTaken(f"{clinician.id} at {start.isoformat()}")

        # The spec says an unavailable clinician must be refused. This books them anyway.
        # The spec also says the audit line comes after the reservation. This writes it first.
        self.state.audit.append(
            AuditEntry(action="book", detail=f"{email} {clinician.id}", at=start)
        )
        appointment = Appointment(
            patient_email=email,
            clinician_id=clinician.id,
            start=start,
            minutes=SLOT_MINUTES,
        )
        self.state.appointments.append(appointment)
        return appointment
