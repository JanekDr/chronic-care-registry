from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from registry.forms import DiagnosisForm, MeasurementForm, PatientForm, ReportForm, VisitForm
from registry.models import Diagnosis, ICD10Code, Measurement, Patient, Report, Visit
from registry.validation import validate_model_instance


class ModelValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.patient = Patient.objects.create(first_name="Anna", last_name="Testowa",
                                             birth_date=date(1980, 1, 1), gender="female")
        cls.code = ICD10Code.objects.create(code="I10", name="Nadciśnienie")
        cls.day = timezone.localdate() - timedelta(days=10)
        cls.visit = Visit.objects.create(patient=cls.patient, visit_date=cls.day)

    def assert_invalid(self, instance, field):
        with self.assertRaises(ValidationError) as error:
            instance.full_clean()
        self.assertIn(field, error.exception.message_dict)

    def test_required_trimmed_names_in_model_and_form(self):
        candidate = validate_model_instance(self.patient, {"first_name": "  Ewa  ", "last_name": "  Test  "})
        self.assertEqual((candidate.first_name, candidate.last_name), ("Ewa", "Test"))
        self.assertEqual(self.patient.first_name, "Anna")
        for field in ("first_name", "last_name"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError) as error:
                    validate_model_instance(self.patient, {field: " \t\n "})
                self.assertIn(field, error.exception.message_dict)
        form = PatientForm(data={"first_name": " Anna ", "last_name": " Testowa ",
                                 "birth_date": "1980-01-01", "gender": "female"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().first_name, "Anna")

    def test_names_length_is_checked_after_trimming(self):
        candidate = validate_model_instance(self.patient, {"first_name": " " + "A" * 80 + " "})
        self.assertEqual(len(candidate.first_name), 80)
        with self.assertRaises(ValidationError):
            validate_model_instance(self.patient, {"first_name": "A" * 81})

    def test_future_birth_date_and_invalid_gender(self):
        for attrs, field in (({"birth_date": timezone.localdate() + timedelta(days=1)}, "birth_date"),
                             ({"gender": "invalid"}, "gender"),
                             ({"gender": "unknown"}, "gender")):
            with self.subTest(field=field), self.assertRaises(ValidationError) as error:
                validate_model_instance(self.patient, attrs)
            self.assertIn(field, error.exception.message_dict)

    def test_clinical_dates_before_birth_future_and_equal_boundaries(self):
        for model, field in ((Diagnosis, "diagnosed_on"), (Visit, "visit_date")):
            defaults = {"patient": self.patient}
            if model == Diagnosis:
                defaults["icd10"] = self.code
            for invalid in (date(1979, 12, 31), timezone.localdate() + timedelta(days=1), "bad-date"):
                with self.subTest(model=model, invalid=invalid):
                    self.assert_invalid(model(**defaults, **{field: invalid}), field)
            for valid in (self.patient.birth_date, timezone.localdate()):
                model(**defaults, **{field: valid}).full_clean()

    def test_birth_date_change_checks_existing_visits_and_diagnoses(self):
        Diagnosis.objects.create(patient=self.patient, icd10=self.code, diagnosed_on=date(2000, 1, 1))
        for new_birth in (self.day + timedelta(days=1), date(2000, 1, 2)):
            with self.subTest(new_birth=new_birth), self.assertRaises(ValidationError) as error:
                validate_model_instance(self.patient, {"birth_date": new_birth})
            self.assertIn("birth_date", error.exception.message_dict)
        validate_model_instance(self.patient, {"birth_date": date(2000, 1, 1)})

    def test_changing_patient_validates_unchanged_date_for_partial_update(self):
        newborn = Patient.objects.create(first_name="Dziecko", last_name="Testowe", birth_date=timezone.localdate(), gender="female")
        diagnosis = Diagnosis.objects.create(patient=self.patient, icd10=self.code, diagnosed_on=self.day)
        for instance, field in ((self.visit, "visit_date"), (diagnosis, "diagnosed_on")):
            with self.subTest(model=type(instance)), self.assertRaises(ValidationError) as error:
                validate_model_instance(instance, {"patient": newborn})
            self.assertIn(field, error.exception.message_dict)
            self.assertEqual(instance.patient_id, self.patient.pk)
            self.assertEqual(instance.patient, self.patient)  # Kopia nie zmienia cache FK.

    def test_duplicate_diagnosis_validated_and_constrained_in_database(self):
        Diagnosis.objects.create(patient=self.patient, icd10=self.code, diagnosed_on=self.day)
        duplicate = Diagnosis(patient=self.patient, icd10=self.code, diagnosed_on=self.day)
        with self.assertRaises(ValidationError):
            duplicate.full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            duplicate.save()

    def test_dictionary_must_exist_and_clinical_fk_must_exist(self):
        self.assert_invalid(Diagnosis(patient=self.patient, icd10_id=9999, diagnosed_on=self.day), "icd10")
        self.assert_invalid(Report(name="Test", date_from=self.day, date_to=self.day, icd10_id=9999), "icd10")
        self.assert_invalid(Visit(patient_id=9999, visit_date=self.day), "patient")
        self.assert_invalid(Visit(patient_id="bad-id", visit_date=self.day), "patient")
        self.assert_invalid(Measurement(visit_id=9999, kind="body_weight", value="1.00"), "visit")

    def test_notes_lengths(self):
        self.assert_invalid(Diagnosis(patient=self.patient, icd10=self.code, diagnosed_on=self.day, notes="x" * 1001), "notes")
        self.assert_invalid(Visit(patient=self.patient, visit_date=self.day, notes="x" * 2001), "notes")

    def test_positive_finite_decimal_precision_and_digit_limits(self):
        for invalid in ("0", "-1.00", "0.001", "1.234", "1000000.00", "12345678", "NaN", "sNaN", "Infinity", "-Infinity", "bad"):
            with self.subTest(value=invalid):
                self.assert_invalid(Measurement(visit=self.visit, kind="blood_glucose", value=invalid), "value")
        for valid in ("0.01", "999999.99", "100.00"):
            measurement = Measurement(visit=self.visit, kind="blood_glucose", value=valid)
            measurement.full_clean()
            self.assertIsInstance(measurement.value, Decimal)
            measurement.save()
            measurement.refresh_from_db()
            self.assertEqual(measurement.value, Decimal(valid))

    def test_kind_mapping_and_no_duplicated_measurement_fields(self):
        self.assert_invalid(Measurement(visit=self.visit, kind="other", value="1.00"), "kind")
        fields = {field.name for field in Measurement._meta.fields}
        self.assertFalse(fields & {"patient", "date", "measurement_date", "unit", "loinc", "category"})
        self.assertEqual(Measurement.DEFINITIONS, {
            "blood_glucose": {"unit": "mg/dL", "loinc": "2339-0", "category": "laboratory", "display": "Glucose [Mass/volume] in Blood"},
            "body_weight": {"unit": "kg", "loinc": "29463-7", "category": "vital-signs", "display": "Body weight"},
        })

    def test_report_period_including_unchanged_field_on_partial_update(self):
        report = Report(name="Próbka", date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
        report.full_clean()
        with self.assertRaises(ValidationError) as error:
            validate_model_instance(report, {"date_from": date(2026, 11, 1)})
        self.assertIn("date_to", error.exception.message_dict)
        self.assertEqual(report.date_from, date(2026, 10, 1))
        validate_model_instance(report, {"date_to": date(2026, 10, 1)})

    def test_forms_use_model_rules(self):
        cases = (
            (PatientForm, {"first_name": "  ", "last_name": "Test", "birth_date": "1980-01-01", "gender": "female"}, "first_name"),
            (DiagnosisForm, {"patient": self.patient.pk, "icd10": self.code.pk, "diagnosed_on": "1979-12-31"}, "diagnosed_on"),
            (VisitForm, {"patient": self.patient.pk, "visit_date": "1979-12-31"}, "visit_date"),
            (MeasurementForm, {"visit": self.visit.pk, "kind": "body_weight", "value": "NaN"}, "value"),
            (ReportForm, {"name": "Raport", "date_from": "2026-10-31", "date_to": "2026-10-01"}, "date_to"),
        )
        for form_class, data, field in cases:
            with self.subTest(form=form_class):
                form = form_class(data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_form_reassignment_and_birth_edit_cannot_bypass_rules(self):
        newborn = Patient.objects.create(first_name="Dziecko", last_name="Testowe", birth_date=timezone.localdate(), gender="female")
        form = VisitForm(instance=self.visit, data={"patient": newborn.pk, "visit_date": self.day})
        self.assertFalse(form.is_valid())
        self.assertIn("visit_date", form.errors)
        form = PatientForm(instance=self.patient, data={"first_name": "Anna", "last_name": "Testowa", "birth_date": timezone.localdate(), "gender": "female"})
        self.assertFalse(form.is_valid())
        self.assertIn("birth_date", form.errors)

    def test_all_clinical_models_and_report_have_timestamps(self):
        for instance in (self.patient, self.visit,
                         Diagnosis.objects.create(patient=self.patient, icd10=self.code, diagnosed_on=self.day),
                         Measurement.objects.create(visit=self.visit, kind="body_weight", value=Decimal("70.50")),
                         Report.objects.create(name="Raport", date_from=self.day, date_to=self.day)):
            with self.subTest(model=type(instance)):
                self.assertIsNotNone(instance.created_at)
                self.assertIsNotNone(instance.updated_at)

    def test_protected_relations_and_deletion_order(self):
        diagnosis = Diagnosis.objects.create(patient=self.patient, icd10=self.code, diagnosed_on=self.day)
        measurement = Measurement.objects.create(visit=self.visit, kind="body_weight", value=Decimal("70.50"))
        report = Report.objects.create(name="Raport", date_from=self.day, date_to=self.day, icd10=self.code)
        for obj in (self.patient, self.visit, self.code):
            with self.subTest(model=type(obj)), self.assertRaises(ProtectedError):
                obj.delete()
        diagnosis.delete()
        with self.assertRaises(ProtectedError):
            self.code.delete()  # Nadal chroniony przez Report.icd10.
        report.delete()
        self.code.delete()
        measurement.delete()
        self.visit.delete()
        self.patient.delete()
