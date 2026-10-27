from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Patient:
    email: str
    name: str
    age: int


@dataclass
class Clinician:
    id: str
    name: str
    available: bool = True


@dataclass
class Appointment:
    patient_email: str
    clinician_id: str
    start: datetime
    minutes: int


@dataclass
class AuditEntry:
    action: str
    detail: str
    at: datetime


@dataclass
class DeskState:
    patients: dict[str, Patient] = field(default_factory=dict)
    appointments: list[Appointment] = field(default_factory=list)
    audit: list[AuditEntry] = field(default_factory=list)
