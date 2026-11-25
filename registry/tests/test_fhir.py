from datetime import date, datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from registry.models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Report, Visit

from .base import RoleTestCase


def resource_url(resource_type, pk):
    resource_id = uuid5(NAMESPACE_URL, f"urn:psim:{resource_type}:{pk}")
    return f"urn:uuid:{resource_id}"


class PatientFHIRExportTests(RoleTestCase, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.patient = Patient.objects.create(first_name="Ada", last_name="Przykładowa",
                                             birth_date=date(1990, 1, 1), gender=Patient.Gender.FEMALE)
        cls.other_patient = Patient.objects.create(first_name="Jan", last_name="Inny",
                                                   birth_date=date(1980, 1, 1), gender=Patient.Gender.MALE)
        cls.empty_patient = Patient.objects.create(first_name="Kaja", last_name="Testowa",
                                                   birth_date=date(2000, 1, 1), gender=Patient.Gender.OTHER)
        hypertension = ICD10Code.objects.create(code="I10", name="Nadciśnienie")
        diabetes = ICD10Code.objects.create(code="E11.9", name="Cukrzyca bez powikłań")
        cls.diagnosis = Diagnosis.objects.create(patient=cls.patient, icd10=hypertension,
                                                 diagnosed_on=date(2024, 9, 1), notes="Notatka rozpoznania")
        cls.recorded_at = datetime(2024, 9, 5, 12, 10, 1, 123456, tzinfo=datetime_timezone.utc)
        Diagnosis.objects.filter(pk=cls.diagnosis.pk).update(created_at=cls.recorded_at)
        Diagnosis.objects.create(patient=cls.other_patient, icd10=diabetes, diagnosed_on=date(2024, 9, 1))
        cls.visit = Visit.objects.create(patient=cls.patient, visit_date=date(2024, 9, 10),
                                         notes="Notatka wizyty", created_by=cls.personel)
        cls.second_visit = Visit.objects.create(patient=cls.patient, visit_date=date(2024, 9, 15))
        other_visit = Visit.objects.create(patient=cls.other_patient, visit_date=date(2024, 9, 10))
        cls.glucose = Measurement.objects.create(visit=cls.visit, kind=Measurement.Kind.BLOOD_GLUCOSE,
                                                  value=Decimal("100.00"))
        cls.weight = Measurement.objects.create(visit=cls.visit, kind=Measurement.Kind.BODY_WEIGHT,
                                                 value=Decimal("60.50"))
        cls.max_value = Measurement.objects.create(visit=cls.second_visit, kind=Measurement.Kind.BLOOD_GLUCOSE,
                                                    value=Decimal("999999.99"))
        Measurement.objects.create(visit=other_visit, kind=Measurement.Kind.BODY_WEIGHT, value=Decimal("85.25"))
        Report.objects.create(name="Raport zbiorczy", date_from=date(2024, 9, 1), date_to=date(2024, 9, 30),
                              created_by=cls.administrator)

    def setUp(self):
        self.client.force_login(self.personel)
        self.url = reverse("api:patient-fhir-export", args=[self.patient.pk])

    def test_download_maps_fhir_r4_resources_and_preserves_decimal_precision(self):
        before = timezone.now()
        response = self.client.get(self.url, HTTP_ACCEPT="application/fhir+json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/fhir+json")
        self.assertEqual(response["Content-Disposition"], f'attachment; filename="patient-{self.patient.pk}-fhir.json"')
        self.assertIn("no-store", response["Cache-Control"])
        bundle = response.json(parse_float=Decimal)
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "collection")
        timestamp = datetime.fromisoformat(bundle["timestamp"])
        self.assertTrue(timezone.is_aware(timestamp))
        self.assertLessEqual(before, timestamp)
        self.assertLessEqual(timestamp, timezone.now())

        resources = {entry["fullUrl"]: entry["resource"] for entry in bundle["entry"]}
        patient = resources[resource_url("Patient", self.patient.pk)]
        self.assertEqual(patient["identifier"], [{"system": "urn:psim:patient-id", "value": str(self.patient.pk)}])
        self.assertEqual(patient["name"], [{"given": ["Ada"], "family": "Przykładowa"}])
        self.assertEqual(patient["birthDate"], "1990-01-01")
        self.assertEqual(patient["gender"], "female")

        systems = "http://terminology.hl7.org/CodeSystem"
        condition = resources[resource_url("Condition", self.diagnosis.pk)]
        self.assertEqual(condition["code"]["coding"], [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "I10"}])
        self.assertEqual(condition["clinicalStatus"]["coding"], [
            {"system": f"{systems}/condition-clinical", "code": "active"},
        ])
        self.assertEqual(condition["verificationStatus"]["coding"], [
            {"system": f"{systems}/condition-ver-status", "code": "confirmed"},
        ])
        self.assertEqual(datetime.fromisoformat(condition["recordedDate"]), self.recorded_at)
        self.assertFalse(any(key.startswith("onset") for key in condition))

        encounter = resources[resource_url("Encounter", self.visit.pk)]
        self.assertEqual(encounter["class"], {"system": f"{systems}/v3-ActCode", "code": "AMB"})
        self.assertEqual(encounter["status"], "finished")
        self.assertEqual(encounter["period"], {"start": "2024-09-10"})

        for measurement, loinc, unit, category, value, visit_date in (
            (self.glucose, "2339-0", "mg/dL", "laboratory", "100.00", "2024-09-10"),
            (self.weight, "29463-7", "kg", "vital-signs", "60.50", "2024-09-10"),
            (self.max_value, "2339-0", "mg/dL", "laboratory", "999999.99", "2024-09-15"),
        ):
            with self.subTest(measurement=measurement.pk):
                observation = resources[resource_url("Observation", measurement.pk)]
                coding, = observation["code"]["coding"]
                self.assertEqual((coding["system"], coding["code"]), ("http://loinc.org", loinc))
                self.assertEqual(observation["category"], [
                    {"coding": [{"system": f"{systems}/observation-category", "code": category}]},
                ])
                self.assertEqual(observation["status"], "final")
                self.assertEqual(observation["effectiveDateTime"], visit_date)
                quantity = observation["valueQuantity"]
                self.assertEqual(
                    (quantity["system"], quantity["code"], quantity["unit"]), ("http://unitsofmeasure.org", unit, unit),
                )
                self.assertIsInstance(quantity["value"], Decimal)
                self.assertEqual(quantity["value"].as_tuple(), Decimal(value).as_tuple())
                if unit == "kg":
                    self.assertEqual(observation["meta"]["profile"], ["http://hl7.org/fhir/StructureDefinition/bodyweight"])
                else:
                    self.assertNotIn("meta", observation)

        for excluded in ("null", "Notatka rozpoznania", "Notatka wizyty", "Raport zbiorczy", "Jan", "E11.9"):
            self.assertNotContains(response, excluded)

    def test_uuid_and_references_are_stable_and_scoped_to_the_patient(self):
        expected = [
            ("Patient", self.patient), ("Condition", self.diagnosis),
            ("Encounter", self.visit), ("Encounter", self.second_visit),
            ("Observation", self.glucose), ("Observation", self.weight), ("Observation", self.max_value),
        ]
        entries = self.client.get(self.url).json()["entry"]
        self.assertEqual(entries, self.client.get(self.url, HTTP_ACCEPT="application/json").json()["entry"])
        self.assertEqual(len(entries), len(expected))
        resources = {entry["fullUrl"]: entry["resource"] for entry in entries}
        self.assertEqual(set(resources), {resource_url(kind, instance.pk) for kind, instance in expected})
        for kind, instance in expected:
            full_url = resource_url(kind, instance.pk)
            resource = resources[full_url]
            self.assertEqual(resource["id"], full_url.removeprefix("urn:uuid:"))
            self.assertEqual(resource["resourceType"], kind)
            if kind != "Patient":
                self.assertEqual(resource["subject"]["reference"], resource_url("Patient", self.patient.pk))
            if kind == "Observation":
                self.assertEqual(resource["encounter"]["reference"], resource_url("Encounter", instance.visit_id))

    def test_patient_without_related_records_has_one_entry(self):
        response = self.client.get(reverse("api:patient-fhir-export", args=[self.empty_patient.pk]))
        self.assertEqual(response.status_code, 200)
        entry, = response.json()["entry"]
        self.assertEqual(entry["fullUrl"], resource_url("Patient", self.empty_patient.pk))
        self.assertEqual(entry["resource"]["resourceType"], "Patient")
        self.assertEqual(entry["resource"]["gender"], "other")

    def test_patient_card_links_to_the_same_export_and_records_one_audit(self):
        card = self.client.get(reverse("registry:patient-detail", args=[self.patient.pk]))
        self.assertContains(card, f'href="{self.url}">Pobierz plik FHIR</a>')
        AuditLog.objects.all().delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(AuditLog.objects.values_list("user_id", "action", "object_type", "object_id")), [
            (self.personel.pk, AuditLog.Action.FHIR_EXPORT, "Patient", str(self.patient.pk)),
        ])
        self.client.force_login(self.administrator)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_access_errors_use_drf_json_and_do_not_record_an_export(self):
        self.client.logout()
        for account in (None, self.outsider, self.staff_outsider, self.personel):
            with self.subTest(account=account):
                if account == self.personel:
                    self.personel.groups.remove(self.personel_group)
                if account is not None:
                    self.client.force_login(account)
                response = self.client.get(self.url, HTTP_ACCEPT="application/fhir+json")
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertIn("detail", response.json())
                self.assertNotIn("Content-Disposition", response)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.FHIR_EXPORT).exists())

    def test_missing_patient_and_unsupported_method_do_not_record_an_export(self):
        missing_url = reverse("api:patient-fhir-export", args=[self.empty_patient.pk + 1])
        response = self.client.get(missing_url, HTTP_ACCEPT="application/fhir+json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("detail", response.json())
        self.assertNotIn("Content-Disposition", response)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.FHIR_EXPORT).exists())

    def test_audit_failure_prevents_the_download(self):
        with (
            patch("registry.api.record_audit", side_effect=RuntimeError("Błąd audytu")),
            self.assertRaisesMessage(RuntimeError, "Błąd audytu"),
        ):
            self.client.get(self.url)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.FHIR_EXPORT).exists())
