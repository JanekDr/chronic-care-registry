from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from registry.models import AuditLog, Diagnosis, Measurement, Report, Visit
from registry.services import calculate_report, save_report

from .base import RoleTestCase
from .report_sample import create_report_sample


class ReportTests(RoleTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sample = create_report_sample()

    def setUp(self):
        self.client.force_login(self.personel)
        AuditLog.objects.all().delete()
        self.data = {"name": "I10 październik", "date_from": "2026-10-01", "date_to": "2026-10-31", "icd10": self.sample["i10"].pk}

    def calculate(self, **overrides):
        params = dict(date_from=date(2026, 10, 1), date_to=date(2026, 10, 31), icd10_id=self.sample["i10"].pk)
        return calculate_report(**{**params, **overrides})

    def create(self):
        response = self.client.post(reverse("registry:report-create"), self.data)
        self.assertEqual(response.status_code, 302)
        return Report.objects.get()

    def test_spec_sample_exact_result_and_json_types(self):
        self.assertEqual(self.calculate(), {
            "patient_count": 1, "visit_count": 2, "measurements": [
                {"kind": "blood_glucose", "unit": "mg/dL", "count": 2, "avg": "110.00", "min": "100.00", "max": "120.00"},
                {"kind": "body_weight", "unit": "kg", "count": 0, "avg": None, "min": None, "max": None},
            ],
        })

    def test_extra_diagnosis_never_duplicates_visits_or_measurements(self):
        before = self.calculate()
        Diagnosis.objects.create(patient=self.sample["patients"]["A"], icd10=self.sample["other"], diagnosed_on=date(2026, 9, 1))
        self.assertEqual(before, self.calculate())
        self.assertEqual(self.calculate(icd10_id=None)["visit_count"], 3)

    def test_diagnosis_date_excludes_earlier_visit_and_includes_same_day(self):
        Diagnosis.objects.filter(patient=self.sample["patients"]["A"], icd10=self.sample["i10"]).update(diagnosed_on=date(2026, 10, 31))
        result = self.calculate()
        self.assertEqual((result["patient_count"], result["visit_count"]), (1, 1))
        self.assertEqual(result["measurements"][0]["avg"], "120.00")

    def test_both_period_boundaries_and_single_day_are_inclusive(self):
        for day, expected in ((date(2026, 10, 1), "100.00"), (date(2026, 10, 31), "120.00")):
            result = self.calculate(date_from=day, date_to=day)
            self.assertEqual(result["visit_count"], 1)
            self.assertEqual(result["measurements"][0]["avg"], expected)
        Visit.objects.create(patient=self.sample["patients"]["A"], visit_date=date(2026, 11, 1))
        self.assertEqual(self.calculate()["visit_count"], 2)

    def test_no_filter_includes_patients_without_diagnoses(self):
        Diagnosis.objects.filter(patient=self.sample["patients"]["B"]).delete()
        result = self.calculate(icd10_id=None)
        self.assertEqual((result["patient_count"], result["visit_count"]), (2, 3))
        self.assertEqual(result["measurements"][0]["avg"], "140.00")

    def test_empty_result_and_visits_without_measurements(self):
        for code in (None, self.sample["i10"].pk):
            result = self.calculate(date_from=date(2000, 1, 1), date_to=date(2000, 1, 1), icd10_id=code)
            self.assertEqual((result["patient_count"], result["visit_count"]), (0, 0))
            for row in result["measurements"]:
                self.assertEqual((row["count"], row["avg"], row["min"], row["max"]), (0, None, None, None))
        Measurement.objects.all().delete()
        self.assertEqual(self.calculate()["visit_count"], 2)
        self.assertEqual(self.calculate()["measurements"][0]["count"], 0)

    def test_decimal_rounding_and_separate_kinds(self):
        Measurement.objects.all().delete()
        visit = self.sample["visits"][0]
        for kind, values in (("blood_glucose", ["0.10", "0.11"]), ("body_weight", ["70.00", "80.01"])):
            for value in values:
                Measurement.objects.create(visit=visit, kind=kind, value=Decimal(value))
        glucose, weight = self.calculate()["measurements"]
        self.assertEqual((glucose["count"], glucose["avg"], glucose["min"], glucose["max"]), (2, "0.11", "0.10", "0.11"))
        self.assertEqual((weight["count"], weight["avg"], weight["min"], weight["max"]), (2, "75.01", "70.00", "80.01"))

    def test_calculator_rejects_invalid_period_dates_and_dictionary_id(self):
        for params in ({"date_from": date(2026, 11, 1)}, {"date_to": "bad"}, {"icd10_id": 999999}):
            with self.subTest(params=params), self.assertRaises(ValidationError):
                self.calculate(**params)

    def test_html_create_snapshot_read_edit_and_delete(self):
        report = self.create()
        original = report.result
        old_time = report.updated_at
        Measurement.objects.filter(visit=self.sample["visits"][0]).update(value=Decimal("200.00"))
        with patch("registry.services.calculate_report", side_effect=AssertionError("Odczyt nie przelicza")):
            for name in ("report-list", "report-detail"):
                response = self.client.get(reverse(f"registry:{name}", args=[] if name == "report-list" else [report.pk]))
                self.assertEqual(response.status_code, 200)
            self.assertContains(response, "110.00")
            self.assertContains(response, "Brak pomiarów")
            self.assertContains(response, "różnych pacjentów")
        report.refresh_from_db()
        self.assertEqual((report.result, report.updated_at), (original, old_time))
        self.client.force_login(self.administrator)
        response = self.client.post(reverse("registry:report-update", args=[report.pk]), {
            **self.data, "result": '{"patient_count":999}', "created_by": self.administrator.pk,
        })
        self.assertRedirects(response, reverse("registry:report-detail", args=[report.pk]))
        report.refresh_from_db()
        self.assertEqual(report.result["measurements"][0]["avg"], "160.00")
        self.assertGreater(report.updated_at, old_time)
        self.assertEqual(report.created_by, self.personel)
        url = reverse("registry:report-delete", args=[report.pk])
        self.assertContains(self.client.get(url), "Czy na pewno")
        self.assertTrue(Report.objects.filter(pk=report.pk).exists())
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse("registry:report-list"))
        self.assertFalse(Report.objects.exists())
        for action in ("create", "update", "delete"):
            self.assertEqual(AuditLog.objects.filter(object_type="Report", action=action, object_id=str(report.pk)).count(), 1)

    def test_html_optional_filter_invalid_inputs_and_escaped_name(self):
        for data, field in (({**self.data, "icd10": 999999}, "icd10"), ({**self.data, "date_to": "2026-09-01"}, "date_to"), ({**self.data, "date_from": "bad"}, "date_from")):
            response = self.client.post(reverse("registry:report-create"), data)
            self.assertIn(field, response.context["form"].errors)
            self.assertFalse(Report.objects.exists())
        self.data.update(icd10="", name="<script>syntetyczny</script>")
        report = self.create()
        self.assertIsNone(report.icd10_id)
        self.assertEqual(report.result["visit_count"], 3)
        response = self.client.get(reverse("registry:report-detail", args=[report.pk]))
        self.assertContains(response, "Wszystkie rozpoznania")
        self.assertContains(response, "&lt;script&gt;syntetyczny&lt;/script&gt;")
        self.assertNotContains(response, "<script>syntetyczny</script>")

    def test_all_report_pages_permissions_and_missing_ids(self):
        report = self.create()
        urls = [reverse("registry:report-list"), reverse("registry:report-create")]
        urls += [reverse(f"registry:report-{action}", args=[report.pk]) for action in ("detail", "update", "delete")]
        for user in (None, self.outsider, self.staff_outsider, self.personel, self.administrator):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for url in urls:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302 if user is None else (200 if user in (self.personel, self.administrator) else 403))
                if user not in (self.personel, self.administrator):
                    self.assertEqual(self.client.post(url, self.data).status_code, 302 if user is None else 403)
        for action in ("detail", "update", "delete"):
            self.assertEqual(self.client.get(reverse(f"registry:report-{action}", args=[999999])).status_code, 404)
        self.assertEqual(Report.objects.count(), 1)

    def test_csrf_for_create_update_delete(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.personel)
        url = reverse("registry:report-create")
        self.assertEqual(secure.post(url, self.data).status_code, 403)
        response = secure.get(url)
        self.assertContains(response, "Zapisz i przelicz")
        token = secure.cookies["csrftoken"].value
        self.assertEqual(secure.post(url, {**self.data, "csrfmiddlewaretoken": token}).status_code, 302)
        report = Report.objects.get()
        for action in ("update", "delete"):
            url = reverse(f"registry:report-{action}", args=[report.pk])
            self.assertEqual(secure.post(url, self.data).status_code, 403)
            self.assertEqual(secure.post(url, {**self.data, "csrfmiddlewaretoken": token}).status_code, 302)
        self.assertFalse(Report.objects.exists())

    def test_mutation_and_audit_are_atomic(self):
        with patch("registry.services.record_audit", side_effect=RuntimeError("Audyt")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("registry:report-create"), self.data)
        self.assertFalse(Report.objects.exists())
        report = self.create()
        original, timestamp = report.result, report.updated_at
        Measurement.objects.update(value=Decimal("500.00"))
        with patch("registry.services.record_audit", side_effect=RuntimeError("Audyt")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("registry:report-update", args=[report.pk]), {**self.data, "name": "Zmiana"})
        report.refresh_from_db()
        self.assertEqual((report.name, report.result, report.updated_at), (self.data["name"], original, timestamp))
        with patch("registry.views.record_audit", side_effect=RuntimeError("Audyt")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("registry:report-delete", args=[report.pk]))
        self.assertTrue(Report.objects.filter(pk=report.pk).exists())

    def test_read_audit_and_no_sensitive_payload(self):
        report = self.create()
        AuditLog.objects.all().delete()
        self.client.get(reverse("registry:report-list"))
        self.client.get(reverse("registry:report-detail", args=[report.pk]))
        self.assertEqual(set(AuditLog.objects.values_list("action", "object_type", "object_id")), {
            ("read_list", "Report", ""), ("read_detail", "Report", str(report.pk)),
        })
        self.assertNotIn(report.name, str(list(AuditLog.objects.values())))

    def test_service_can_save_without_html_and_keeps_original_author(self):
        report = Report(name="Usługa", date_from=date(2026, 10, 1), date_to=date(2026, 10, 31))
        save_report(report=report, user=self.personel)
        save_report(report=report, user=self.administrator)
        report.refresh_from_db()
        self.assertEqual(report.created_by, self.personel)
        self.assertEqual(report.result, self.calculate(icd10_id=None))

    def test_admin_audit_failure_rolls_back_report_and_recalculation(self):
        self.client.force_login(self.administrator)
        with patch("registry.admin.record_audit", side_effect=RuntimeError("Audyt")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("admin:registry_report_add"), self.data)
        self.assertFalse(Report.objects.exists())
        report = self.create()
        original = report.result
        Measurement.objects.update(value=Decimal("999.00"))
        with patch("registry.admin.record_audit", side_effect=RuntimeError("Audyt")):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("admin:registry_report_change", args=[report.pk]), {**self.data, "name": "Zmiana"})
        report.refresh_from_db()
        self.assertEqual((report.name, report.result), (self.data["name"], original))
