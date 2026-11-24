from datetime import date, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import yaml
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from registry.models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Report, Visit
from registry.services import save_report

from .base import RoleTestCase
from .report_sample import create_report_sample


def api_url(resource, pk=None):
    collection = f"/api/v1/{resource}/"
    return collection if pk is None else f"{collection}{pk}/"


class RegistryAPITestCase(RoleTestCase, APITestCase):
    def setUp(self):
        self.client.force_login(self.personel)
        AuditLog.objects.all().delete()

    def create_record(self, resource, data):
        response = self.client.post(api_url(resource), data, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()


class RegistryAPITests(RegistryAPITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.patient = Patient.objects.create(
            first_name="Anna", last_name="Testowa", birth_date=date(1980, 1, 1), gender="female",
        )
        cls.second_patient = Patient.objects.create(
            first_name="Anna", last_name="Inna", birth_date=date(2020, 10, 30), gender="female",
        )
        cls.code = ICD10Code.objects.create(code="I10", name="Nadciśnienie")
        cls.other_code = ICD10Code.objects.create(code="E11.9", name="Cukrzyca bez powikłań")
        cls.diagnosis = Diagnosis.objects.create(patient=cls.patient, icd10=cls.code, diagnosed_on=date(2017, 1, 1))
        cls.visit = Visit.objects.create(patient=cls.patient, visit_date=date(2020, 10, 1), created_by=cls.personel)
        cls.measurement = Measurement.objects.create(visit=cls.visit, kind="body_weight", value="70.00")
        cls.report = save_report(report=Report(name="Październik", date_from=date(2020, 10, 1), date_to=date(2020, 10, 31)), user=cls.personel)

    def resources(self):
        return {
            "patients": self.patient, "diagnoses": self.diagnosis, "visits": self.visit,
            "measurements": self.measurement, "reports": self.report, "icd10": self.code,
        }

    def test_permissions_cover_all_resources_and_schema(self):
        read_urls = ["/api/schema/"]
        write_requests = []
        for resource, record in self.resources().items():
            collection, detail = api_url(resource), api_url(resource, record.pk)
            read_urls.extend([collection, detail])
            write_requests.extend([(self.client.post, collection), (self.client.put, detail),
                                   (self.client.patch, detail), (self.client.delete, detail)])
        for user in (None, self.outsider, self.staff_outsider, self.personel, self.administrator):
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            allowed = user in (self.personel, self.administrator)
            for url in read_urls:
                with self.subTest(user=user, url=url):
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200 if allowed else 403)
                    self.assertNotIn("Location", response.headers)
                    if not allowed:
                        self.assertIn("detail", response.json())
            if not allowed:
                for method, url in write_requests:
                    self.assertEqual(method(url, {}, format="json").status_code, 403, url)
                self.assertFalse(AuditLog.objects.exclude(object_type="User").exists())

    def test_revoking_personel_role_revokes_access_in_active_session(self):
        self.personel.groups.remove(self.personel_group)
        self.assertEqual(self.client.get(api_url("patients")).status_code, 403)
        self.assertEqual(self.client.get("/api/schema/").status_code, 403)

    def test_session_requires_csrf_for_post_put_patch_and_delete(self):
        client = APIClient(enforce_csrf_checks=True)
        login_url = reverse("login")
        self.assertEqual(client.get(login_url).status_code, 200)
        login_token = client.cookies[settings.CSRF_COOKIE_NAME].value
        response = client.post(login_url, {
            "username": self.personel.username, "password": self.password, "csrfmiddlewaretoken": login_token,
        })
        self.assertEqual(response.status_code, 302)
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertNotEqual(token, login_token)
        self.assertEqual(client.get(api_url("patients")).status_code, 200)
        for resource, record in self.resources().items():
            if resource == "icd10":
                continue
            detail = api_url(resource, record.pk)
            for method, url in ((client.post, api_url(resource)), (client.put, detail),
                                (client.patch, detail), (client.delete, detail)):
                with self.subTest(resource=resource, method=method.__name__):
                    response = method(url, {}, format="json")
                    self.assertEqual(response.status_code, 403)
                    self.assertIn("CSRF", response.json()["detail"])
                    self.assertEqual(method(url, {}, format="json", HTTP_X_CSRFTOKEN=login_token).status_code, 403)
        self.assertFalse(AuditLog.objects.filter(action__in=["create", "update", "delete"]).exists())
        headers = {"HTTP_X_CSRFTOKEN": token}
        payload = {"first_name": "Ada", "last_name": "Próbna", "birth_date": "1990-01-01", "gender": "female"}
        response = client.post(api_url("patients"), payload, format="json", **headers)
        self.assertEqual(response.status_code, 201)
        detail = api_url("patients", response.json()["id"])
        self.assertEqual(client.put(detail, payload, format="json", **headers).status_code, 200)
        self.assertEqual(client.patch(detail, {"last_name": "Nowa"}, format="json", **headers).status_code, 200)
        self.assertEqual(client.delete(detail, **headers).status_code, 204)

    def test_clinical_crud_and_read_audit(self):
        patient_data = {"first_name": "Ola", "last_name": "Próbna", "birth_date": "1980-01-01", "gender": "female"}
        patient = self.create_record("patients", patient_data)
        diagnosis_data = {"patient": patient["id"], "icd10": self.code.pk, "diagnosed_on": "2020-09-30", "notes": "Próba"}
        diagnosis = self.create_record("diagnoses", diagnosis_data)
        visit_data = {"patient": patient["id"], "visit_date": "2020-10-01", "notes": "Próba", "created_by": self.administrator.pk}
        visit = self.create_record("visits", visit_data)
        self.assertEqual(visit["created_by"], self.personel.pk)
        measurement_data = {"visit": visit["id"], "kind": "blood_glucose", "value": "100.00"}
        measurement = self.create_record("measurements", measurement_data)
        cases = [
            ("patients", Patient, patient, patient_data, {"first_name": " Olga "}, {"first_name": "Olga"}),
            ("diagnoses", Diagnosis, diagnosis, diagnosis_data, {"notes": "Po edycji"}, {"notes": "Po edycji"}),
            ("visits", Visit, visit, visit_data, {"notes": "Po edycji"}, {"notes": "Po edycji", "created_by": self.personel.pk}),
            ("measurements", Measurement, measurement, measurement_data, {"value": "71", "kind": "body_weight"},
             {"value": "71.00", "kind": "body_weight"}),
        ]
        for resource, model, item, full_data, patch_data, expected in cases:
            with self.subTest(resource=resource):
                url = api_url(resource, item["id"])
                self.assertEqual(self.client.get(api_url(resource)).status_code, 200)
                self.assertEqual(self.client.get(url).json(), item)
                self.assertEqual(self.client.put(url, full_data, format="json").status_code, 200)
                self.assertEqual(self.client.patch(url, patch_data, format="json").status_code, 200)
                saved = self.client.get(url).json()
                self.assertEqual({key: saved[key] for key in expected}, expected)
                self.assertEqual(saved["created_at"], item["created_at"])
        for resource, model, item, *_ in reversed(cases):
            url = api_url(resource, item["id"])
            response = self.client.delete(url)
            self.assertEqual((response.status_code, response.content), (204, b""))
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertFalse(model.objects.filter(pk=item["id"]).exists())
            audit = AuditLog.objects.filter(object_type=model.__name__).order_by("id")
            self.assertEqual(list(audit.values_list("action", "object_id", "user_id")), [
                (action, "" if action == "read_list" else str(item["id"]), self.personel.pk)
                for action in ("create", "read_list", "read_detail", "update", "update", "read_detail", "delete")
            ])

    def test_shared_validation_checks_the_whole_record_on_patch(self):
        cases = [
            ("patients", self.patient.pk, {"first_name": "  "}, "first_name"),
            ("patients", self.patient.pk, {"birth_date": "2018-01-01"}, "birth_date"),
            ("patients", self.patient.pk, {"birth_date": (timezone.localdate() + timedelta(days=1)).isoformat()}, "birth_date"),
            ("diagnoses", self.diagnosis.pk, {"patient": self.second_patient.pk}, "diagnosed_on"),
            ("diagnoses", self.diagnosis.pk, {"icd10": 999999}, "icd10"),
            ("visits", self.visit.pk, {"patient": self.second_patient.pk}, "visit_date"),
            ("visits", self.visit.pk, {"patient": self.patient.pk + 0.5}, "patient"),
            ("visits", self.visit.pk, {"notes": "X" * 2001}, "notes"),
            ("measurements", self.measurement.pk, {"kind": "invalid"}, "kind"),
        ]
        second_diagnosis = Diagnosis.objects.create(patient=self.patient, icd10=self.other_code, diagnosed_on=date(2017, 1, 1))
        cases.append(("diagnoses", second_diagnosis.pk, {"icd10": self.code.pk}, "non_field_errors"))
        for resource, pk, payload, field in cases:
            with self.subTest(resource=resource, field=field):
                response = self.client.patch(api_url(resource, pk), payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.json()[field], list)
        response = self.client.put(api_url("patients", self.patient.pk), {"first_name": "Anna"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"last_name", "birth_date", "gender"})
        self.assertFalse(AuditLog.objects.exists())

    def test_measurement_decimal_limits_and_json_strings(self):
        url = api_url("measurements", self.measurement.pk)
        for value in ("0", "-0.01", "0.001", "1000000.00", "NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                response = self.client.patch(url, {"value": value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("value", response.json())
        for value in ("0.01", "999999.99"):
            response = self.client.patch(url, {"value": value}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["value"], value)

    def test_filters_combine_search_and_relationships_with_inclusive_visit_dates(self):
        october_end = Visit.objects.create(patient=self.patient, visit_date=date(2020, 10, 31))
        october_end_tie = Visit.objects.create(patient=self.patient, visit_date=date(2020, 10, 31))
        Visit.objects.create(patient=self.patient, visit_date=date(2020, 9, 30))
        Visit.objects.create(patient=self.second_patient, visit_date=date(2020, 10, 31))
        cases = [
            ("patients", {"search": "test anna", "icd10": "I10"}, [self.patient.pk]),
            ("patients", {"search": "inna", "icd10": "I10"}, []),
            ("diagnoses", {"patient": self.patient.pk}, [self.diagnosis.pk]),
            ("diagnoses", {"patient": self.second_patient.pk}, []),
            ("visits", {"patient": self.patient.pk, "date_from": "2020-10-01", "date_to": "2020-10-31"},
             [october_end.pk, october_end_tie.pk, self.visit.pk]),
            ("visits", {"patient": self.patient.pk, "date_from": "2020-10-02"}, [october_end.pk, october_end_tie.pk]),
            ("measurements", {"visit": self.visit.pk}, [self.measurement.pk]),
            ("measurements", {"visit": october_end.pk}, []),
            ("icd10", {"search": "e11"}, [self.other_code.pk]),
            ("icd10", {"search": "cukrzyca"}, [self.other_code.pk]),
        ]
        for resource, filters, expected in cases:
            with self.subTest(resource=resource, filters=filters):
                response = self.client.get(api_url(resource), filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.json()["results"]], expected)
        self.assertEqual(self.client.get(api_url("visits", self.visit.pk), {"patient": "bad"}).status_code, 200)

    def test_filter_validation_returns_field_errors_without_read_audit(self):
        cases = [
            ("diagnoses", {"patient": "bad"}, "patient"),
            ("measurements", {"visit": "1.5"}, "visit"),
            ("visits", {"date_from": "20201001"}, "date_from"),
            ("visits", {"date_to": "2020-10-1"}, "date_to"),
            ("visits", {"date_to": "2020-02-30"}, "date_to"),
            ("visits", {"date_from": ""}, "date_from"),
            ("visits", {"date_from": "2020-10-31", "date_to": "2020-10-01"}, "date_to"),
        ]
        for resource, query, field in cases:
            with self.subTest(query=query):
                response = self.client.get(api_url(resource), query)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
        self.assertFalse(AuditLog.objects.exists())

    def test_page_number_pagination_has_stable_order_and_preserves_filters(self):
        patients = Patient.objects.bulk_create([
            Patient(first_name=first_name, last_name=last_name, birth_date=date(1980, 1, 1), gender="female")
            for first_name, last_name in (("Zofia", "Paginacja"), ("Anna", "Z Paginacja"), ("Anna", "Paginacja")) * 8
        ])
        expected = [item.pk for item in sorted(patients, key=lambda item: (item.last_name, item.first_name, item.pk))]
        response = self.client.get(api_url("patients"), {"search": "Paginacja"})
        self.assertEqual(response.status_code, 200)
        first_page = response.json()
        self.assertEqual(set(first_page), {"count", "next", "previous", "results"})
        self.assertEqual(first_page["count"], 24)
        self.assertIsNone(first_page["previous"])
        self.assertEqual([row["id"] for row in first_page["results"]], expected[:20])
        self.assertEqual(parse_qs(urlsplit(first_page["next"]).query), {"page": ["2"], "search": ["Paginacja"]})
        page = self.client.get(first_page["next"]).json()
        self.assertEqual([row["id"] for row in page["results"]], expected[20:])
        self.assertIsNone(page["next"])
        self.assertIsNotNone(page["previous"])
        self.assertEqual(self.client.get(api_url("patients"), {"page": 99}).status_code, 404)

    def test_missing_resources_protected_deletes_and_read_only_dictionary(self):
        for resource, record in self.resources().items():
            response = self.client.get(api_url(resource, 999999))
            self.assertEqual(response.status_code, 404)
            self.assertIn("detail", response.json())
        for resource, record, reason in (("patients", self.patient, "rozpoznania lub wizyty"), ("visits", self.visit, "pomiary")):
            response = self.client.delete(api_url(resource, record.pk))
            self.assertEqual(response.status_code, 409)
            self.assertIn(reason, response.json()["detail"])
            self.assertTrue(type(record).objects.filter(pk=record.pk).exists())
        self.client.force_login(self.administrator)
        detail = api_url("icd10", self.code.pk)
        for method, url in ((self.client.post, api_url("icd10")), (self.client.put, detail),
                            (self.client.patch, detail), (self.client.delete, detail)):
            self.assertEqual(method(url, {}, format="json").status_code, 405)
        self.assertFalse(AuditLog.objects.exclude(object_type="User").exists())
        self.assertEqual(self.client.get(api_url("icd10")).status_code, 200)
        self.assertEqual(self.client.get(detail).json(), {"id": self.code.pk, "code": "I10", "name": self.code.name})
        self.assertEqual(list(AuditLog.objects.filter(object_type="ICD10Code").order_by("id").values_list("action", "object_id")),
                         [("read_list", ""), ("read_detail", str(self.code.pk))])

    def test_audit_failure_rolls_back_each_write(self):
        patient = Patient.objects.create(first_name="Jan", last_name="Próbny", birth_date=date(1980, 1, 1), gender="male")
        visit = Visit.objects.create(patient=self.patient, visit_date=date(2020, 10, 1))
        cases = [
            ("patients", patient, {"first_name": "Piotr", "last_name": "Próbny", "birth_date": "1990-01-01", "gender": "male"}, {"first_name": "Piotr"}),
            ("diagnoses", self.diagnosis, {"patient": self.patient.pk, "icd10": self.other_code.pk, "diagnosed_on": "2017-01-01"}, {"notes": "Zmieniona"}),
            ("visits", visit, {"patient": self.patient.pk, "visit_date": "2020-10-05"}, {"visit_date": "2020-10-06"}),
            ("measurements", self.measurement, {"visit": self.visit.pk, "kind": "blood_glucose", "value": "100.00"}, {"value": "81.00"}),
            ("reports", self.report, {"name": "Nowy raport", "date_from": "2020-10-01", "date_to": "2020-10-31"}, {"name": "Zmieniony raport"}),
        ]
        for resource, record, create_data, patch_data in cases:
            model = type(record)
            before = list(model.objects.order_by("id").values())
            detail = api_url(resource, record.pk)
            for method, url, payload in ((self.client.post, api_url(resource), create_data),
                                         (self.client.patch, detail, patch_data), (self.client.delete, detail, {})):
                with (
                    self.subTest(resource=resource, method=method.__name__),
                    patch("registry.api.record_audit", side_effect=RuntimeError("Błąd audytu")),
                    patch("registry.services.record_audit", side_effect=RuntimeError("Błąd audytu")),
                    self.assertRaisesMessage(RuntimeError, "Błąd audytu"),
                ):
                    method(url, payload, format="json")
                self.assertEqual(list(model.objects.order_by("id").values()), before)
        self.assertFalse(AuditLog.objects.exists())

    def test_live_schema_matches_checked_in_document(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        with (settings.BASE_DIR / "docs" / "openapi.yaml").open(encoding="utf-8") as document:
            self.assertEqual(schema, yaml.safe_load(document))
        self.assertEqual(schema["components"]["securitySchemes"]["cookieAuth"]["name"], settings.SESSION_COOKIE_NAME)
        visit_list = schema["paths"][api_url("visits")]["get"]
        self.assertEqual({parameter["name"] for parameter in visit_list["parameters"]},
                         {"page", "patient", "date_from", "date_to"})
        report_create = schema["paths"][api_url("reports")]["post"]
        self.assertIn("X-CSRFToken", {parameter["name"] for parameter in report_create["parameters"] if parameter["required"]})
        self.assertNotIn("result", schema["components"]["schemas"]["ReportRequest"]["properties"])
        self.assertTrue(schema["components"]["schemas"]["Report"]["properties"]["result"]["readOnly"])


class ReportAPITests(RegistryAPITestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sample = create_report_sample()
        cls.report_data = {"name": "I10 październik", "date_from": "2026-10-01", "date_to": "2026-10-31", "icd10": cls.sample["i10"].pk}

    def test_report_matches_html_and_recalculates_only_on_write(self):
        response = self.client.post(reverse("registry:report-create"), self.report_data)
        self.assertEqual(response.status_code, 302)
        html_report = Report.objects.get()
        report = self.create_record("reports", {
            **self.report_data, "id": 999999, "created_by": self.administrator.pk,
            "result": {"patient_count": 999}, "created_at": "2000-01-01T00:00:00Z", "updated_at": "2000-01-01T00:00:00Z",
        })
        self.assertNotEqual(report["id"], 999999)
        self.assertFalse(report["created_at"].startswith("2000-01-01"))
        self.assertFalse(report["updated_at"].startswith("2000-01-01"))
        self.assertEqual(report["created_by"], self.personel.pk)
        self.assertEqual(report["result"], html_report.result)
        self.assertEqual(report["result"], {
            "patient_count": 1, "visit_count": 2,
            "measurements": [
                {"kind": "blood_glucose", "unit": "mg/dL", "count": 2, "avg": "110.00", "min": "100.00", "max": "120.00"},
                {"kind": "body_weight", "unit": "kg", "count": 0, "avg": None, "min": None, "max": None},
            ],
        })
        url = api_url("reports", report["id"])
        Measurement.objects.filter(visit=self.sample["visits"][0]).update(value="200.00")
        with patch("registry.services.calculate_report", side_effect=AssertionError("Odczyt nie przelicza raportu")):
            self.assertEqual(self.client.get(url).json(), report)
            self.assertEqual(self.client.get(api_url("reports")).json()["results"][1], report)
        self.client.force_login(self.administrator)
        response = self.client.patch(url, {}, format="json")
        self.assertEqual(response.status_code, 200)
        updated = response.json()
        self.assertEqual(updated["result"]["measurements"][0]["avg"], "160.00")
        self.assertEqual(updated["icd10"], self.report_data["icd10"])
        self.assertEqual(updated["created_by"], report["created_by"])
        self.assertEqual(updated["created_at"], report["created_at"])
        self.assertNotEqual(updated["updated_at"], report["updated_at"])
        payload = {name: value for name, value in self.report_data.items() if name != "icd10"}
        response = self.client.put(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["icd10"])
        self.assertEqual(response.json()["result"]["visit_count"], 3)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(Report.objects.filter(pk=report["id"]).exists())
        audit = AuditLog.objects.filter(object_type="Report", object_id=str(report["id"])).order_by("id")
        self.assertEqual(list(audit.values_list("action", "user_id")), [
            ("create", self.personel.pk), ("read_detail", self.personel.pk),
            ("update", self.administrator.pk), ("update", self.administrator.pk), ("delete", self.administrator.pk),
        ])

    def test_report_optional_filter_and_errors(self):
        payload = {name: value for name, value in self.report_data.items() if name != "icd10"}
        for data in (payload, {**payload, "icd10": None}):
            report = self.create_record("reports", data)
            self.assertIsNone(report["icd10"])
            self.assertEqual(report["result"]["visit_count"], 3)
        for changes, field in (({"icd10": 999999}, "icd10"), ({"date_to": "2026-09-01"}, "date_to"),
                               ({"date_from": "bad"}, "date_from")):
            response = self.client.post(api_url("reports"), {**self.report_data, **changes}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn(field, response.json())
        self.assertEqual(Report.objects.count(), 2)
