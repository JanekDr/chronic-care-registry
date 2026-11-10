"""Niezależna od seed_demo, stała próbka A/B/C z SPEC §10."""

from datetime import date
from decimal import Decimal

from registry.models import Diagnosis, ICD10Code, Measurement, Patient, Visit


def create_report_sample():
    i10 = ICD10Code.objects.create(code="I10", name="Nadciśnienie")
    other = ICD10Code.objects.create(code="E11.9", name="Cukrzyca bez powikłań")
    patients = {
        letter: Patient.objects.create(first_name=letter, last_name="Próbka raportu",
                                       birth_date=date(1980, 1, 1), gender=Patient.Gender.FEMALE)
        for letter in "ABC"
    }
    for letter, code in (("A", i10), ("B", other), ("C", i10)):
        Diagnosis.objects.create(patient=patients[letter], icd10=code, diagnosed_on=date(2026, 9, 1))
    visits = []
    for letter, day, value in (
        ("A", date(2026, 10, 1), "100.00"),
        ("A", date(2026, 10, 31), "120.00"),
        ("A", date(2026, 9, 30), "150.00"),
        ("B", date(2026, 10, 15), "200.00"),
    ):
        visit = Visit.objects.create(patient=patients[letter], visit_date=day)
        Measurement.objects.create(visit=visit, kind=Measurement.Kind.BLOOD_GLUCOSE, value=Decimal(value))
        visits.append(visit)
    return {"patients": patients, "i10": i10, "other": other, "visits": visits}
