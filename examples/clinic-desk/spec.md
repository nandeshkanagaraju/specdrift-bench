# Clinic desk

The clinic desk registers patients, books clinician slots, and charges cancellation fees.
Every rule below is one requirement.

## Patients

- **R01** A patient MUST be at least 16 years old to register.
- **R02** Registration of a patient who does not meet R01 MUST raise `UnderagePatient`.
- **R03** Registering an email that already belongs to a patient MUST raise `DuplicatePatient`.

## Appointments

- **R04** A slot MUST be 30 minutes long.
- **R05** A patient MUST NOT hold more than 3 appointments on the same calendar day.
- **R06** Booking that would exceed R05 MUST raise `DailyLimitExceeded`.
- **R07** Booking a slot that is already taken MUST raise `SlotTaken`.
- **R08** Booking with a clinician who is marked unavailable MUST raise `ClinicianUnavailable`.

## Cancellation and fees

- **R09** A cancellation made less than 24 hours before the slot MUST incur a fee of 25.00.
- **R10** A cancellation made 24 hours or more before the slot MUST incur a fee of 0.
- **R11** The no-show fee MUST be 40.00.

## Records

- **R12** The audit entry for a booking MUST be written only after the slot has been reserved.
