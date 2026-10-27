"""The folder checker skips tests/. These are not part of the report."""

from clinic.schedule import Desk


def test_register_stores_the_patient():
    desk = Desk()
    patient = desk.register("ada@example.com", "Ada", 30)
    assert patient.email == "ada@example.com"
