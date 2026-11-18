from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import NON_FIELD_ERRORS
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from registry.forms import PatientDiagnosisForm, PatientVisitForm, VisitMeasurementForm
from registry.models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Visit

from .base import RoleTestCase
from .test_auth import FormMarkup


class RegistryHTMLTests(RoleTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.patient = Patient.objects.create(first_name="Anna", last_name="Testowa", birth_date=date(1980, 1, 1), gender="female")
        cls.other = Patient.objects.create(first_name="Jan", last_name="Drugi", birth_date=date(1990, 1, 1), gender="male")
        cls.code = ICD10Code.objects.create(code="I10", name="Nadciśnienie")
        cls.other_code = ICD10Code.objects.create(code="E11.9", name="Cukrzyca")
        cls.diagnosis = Diagnosis.objects.create(patient=cls.patient, icd10=cls.code, diagnosed_on=date(2000, 1, 1))
        cls.visit = Visit.objects.create(patient=cls.patient, visit_date=date(2000, 1, 2), created_by=cls.personel)
        cls.measurement = Measurement.objects.create(visit=cls.visit, kind="body_weight", value=Decimal("70.00"))

    def setUp(self):
        self.client.force_login(self.personel)
        AuditLog.objects.all().delete()

    def url(self, name, *args):
        return reverse(f"registry:{name}", args=args)

    def mutation_counts(self):
        return tuple(model.objects.count() for model in (Patient, Diagnosis, Visit, Measurement))

    def pages(self):
        yield self.url("patient-list")
        for action in ("create", "detail", "update", "delete"):
            yield self.url(f"patient-{action}", *([] if action == "create" else [self.patient.pk]))
            for kind, obj in (("diagnosis", self.diagnosis), ("visit", self.visit)):
                yield self.url(f"{kind}-{action}", self.patient.pk, *([] if action == "create" else [obj.pk]))
            yield self.url(f"measurement-{action}", self.visit.pk, *([] if action == "create" else [self.measurement.pk]))

    def test_personel_can_complete_create_read_update_delete_path(self):
        response = self.client.post(self.url("patient-create"), {
            "first_name": "  Ewa  ", "last_name": "  Syntetyczna  ", "birth_date": "1985-03-04", "gender": "female",
        })
        patient = Patient.objects.get(last_name="Syntetyczna")
        self.assertEqual(patient.first_name, "Ewa")
        self.assertRedirects(response, self.url("patient-detail", patient.pk))
        response = self.client.post(self.url("diagnosis-create", patient.pk), {
            "icd10": self.code.pk, "diagnosed_on": "2001-01-01", "notes": "Rozpoznanie testowe", "patient": self.other.pk,
        })
        diagnosis = patient.diagnoses.get()
        self.assertRedirects(response, self.url("patient-detail", patient.pk))
        self.assertContains(self.client.get(self.url("diagnosis-detail", patient.pk, diagnosis.pk)), "Rozpoznanie testowe")
        response = self.client.post(self.url("visit-create", patient.pk), {
            "visit_date": "2001-01-02", "notes": "Wizyta testowa", "created_by": self.administrator.pk, "patient": self.other.pk,
        })
        visit = patient.visits.get()
        self.assertEqual(visit.created_by, self.personel)
        self.assertRedirects(response, self.url("visit-detail", patient.pk, visit.pk))
        for kind, value, unit in (("blood_glucose", "100.00", "mg/dL"), ("body_weight", "75.50", "kg")):
            response = self.client.post(self.url("measurement-create", visit.pk), {
                "kind": kind, "value": value, "visit": self.visit.pk,
            })
            measurement = visit.measurements.get(kind=kind)
            self.assertRedirects(response, self.url("visit-detail", patient.pk, visit.pk))
            self.assertEqual(measurement.value, Decimal(value))
            self.assertContains(self.client.get(self.url("measurement-detail", visit.pk, measurement.pk)), unit)
        self.assertRedirects(self.client.post(self.url("patient-update", patient.pk), {
            "first_name": "Ewa", "last_name": "Poprawiona", "birth_date": "1985-03-04", "gender": "other",
        }), self.url("patient-detail", patient.pk))
        self.assertRedirects(self.client.post(self.url("diagnosis-update", patient.pk, diagnosis.pk), {
            "icd10": self.other_code.pk, "diagnosed_on": "2001-01-02", "notes": "Poprawione rozpoznanie",
        }), self.url("patient-detail", patient.pk))
        self.assertRedirects(self.client.post(self.url("visit-update", patient.pk, visit.pk), {
            "visit_date": "2001-01-03", "notes": "Poprawiona wizyta", "created_by": self.administrator.pk,
        }), self.url("visit-detail", patient.pk, visit.pk))
        glucose = visit.measurements.get(kind="blood_glucose")
        self.assertRedirects(self.client.post(self.url("measurement-update", visit.pk, glucose.pk), {
            "kind": "body_weight", "value": "80.25",
        }), self.url("visit-detail", patient.pk, visit.pk))
        patient.refresh_from_db()
        diagnosis.refresh_from_db()
        visit.refresh_from_db()
        glucose.refresh_from_db()
        self.assertEqual((patient.last_name, patient.gender), ("Poprawiona", "other"))
        self.assertEqual((diagnosis.icd10, diagnosis.notes), (self.other_code, "Poprawione rozpoznanie"))
        self.assertEqual((visit.visit_date, visit.created_by), (date(2001, 1, 3), self.personel))
        self.assertEqual((glucose.kind, glucose.value), ("body_weight", Decimal("80.25")))
        objects = [("Measurement", obj.pk) for obj in visit.measurements.all()]
        objects += [("Visit", visit.pk), ("Diagnosis", diagnosis.pk), ("Patient", patient.pk)]
        for measurement in list(visit.measurements.all()):
            self.assertRedirects(self.client.post(self.url("measurement-delete", visit.pk, measurement.pk)), self.url("visit-detail", patient.pk, visit.pk))
        self.assertRedirects(self.client.post(self.url("visit-delete", patient.pk, visit.pk)), self.url("patient-detail", patient.pk))
        self.assertRedirects(self.client.post(self.url("diagnosis-delete", patient.pk, diagnosis.pk)), self.url("patient-detail", patient.pk))
        self.assertRedirects(self.client.post(self.url("patient-delete", patient.pk)), self.url("patient-list"))
        for object_type, object_id in objects:
            for action in (AuditLog.Action.CREATE, AuditLog.Action.DELETE):
                self.assertEqual(AuditLog.objects.filter(action=action, object_type=object_type, object_id=str(object_id), user=self.personel).count(), 1)
        for object_type in ("Patient", "Diagnosis", "Visit", "Measurement"):
            self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.UPDATE, object_type=object_type).exists())

    def test_all_pages_render_for_both_roles(self):
        for user in (self.personel, self.administrator):
            self.client.force_login(user)
            for url in self.pages():
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_all_pages_reject_anonymous_and_accounts_without_role(self):
        for user in (None, self.outsider, self.staff_outsider):
            self.client.logout()
            if user:
                self.client.force_login(user)
            AuditLog.objects.all().delete()
            before = self.mutation_counts()
            for url in self.pages():
                for method in (self.client.get, self.client.post):
                    with self.subTest(user=user, url=url, method=method.__name__):
                        response = method(url)
                        self.assertEqual(response.status_code, 403 if user else 302)
                        if not user:
                            self.assertEqual(response.url, f"{reverse('login')}?next={url}")
            self.assertEqual(before, self.mutation_counts())
            self.assertFalse(AuditLog.objects.exists())

    def test_search_icd10_and_pagination_preserve_filters_and_stable_order(self):
        Patient.objects.bulk_create([
            Patient(first_name="Anna", last_name="Testowa", birth_date=date(1980, 1, 1), gender="female") for _ in range(23)
        ])
        Diagnosis.objects.bulk_create([
            Diagnosis(patient=patient, icd10=self.code, diagnosed_on=date(2000, 1, 1))
            for patient in Patient.objects.exclude(pk__in=[self.patient.pk, self.other.pk])
        ])
        Diagnosis.objects.create(patient=self.patient, icd10=self.other_code, diagnosed_on=date(2000, 1, 1))
        params = {"search": "Testowa Anna", "icd10": "I10"}
        response = self.client.get(self.url("patient-list"), params)
        first_page = list(response.context["object_list"])
        self.assertEqual(len(first_page), 20)
        self.assertEqual(response.context["paginator"].count, 24)
        self.assertContains(response, "search=Testowa+Anna&amp;icd10=I10&amp;page=2")
        second_page = list(self.client.get(self.url("patient-list"), {**params, "page": 2}).context["object_list"])
        expected = list(Patient.objects.exclude(pk=self.other.pk).order_by("last_name", "first_name", "id"))
        self.assertEqual(first_page + second_page, expected)
        for params in ({"search": "TeStoWa"}, {"search": "Anna"}, {"search": " Anna   Testowa "}):
            self.assertEqual(self.client.get(self.url("patient-list"), params).context["paginator"].count, 24)
        for params in ({"search": "nie-istnieje"}, {"icd10": "nie-istnieje"}):
            self.assertContains(self.client.get(self.url("patient-list"), params), "Brak pacjentów")
        for page in ("bad", "999", "0"):
            self.assertEqual(self.client.get(self.url("patient-list"), {"page": page}).status_code, 404)

    def test_list_orders_last_name_first_name_then_id(self):
        extra = [Patient.objects.create(first_name=first, last_name=last, birth_date=date(1980, 1, 1), gender="other")
                 for last, first in (("Aaa", "Zofia"), ("Aaa", "Anna"), ("Zzz", "Adam"))]
        response = self.client.get(self.url("patient-list"))
        self.assertEqual(list(response.context["object_list"]), [extra[1], extra[0], self.other, self.patient, extra[2]])

    def test_form_validation_errors_do_not_write_data_or_mutation_audit(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        cases = [
            ("patient-create", [], {"first_name": "  ", "last_name": "Test", "birth_date": "1980-01-01", "gender": "female"}, "first_name"),
            ("patient-create", [], {"first_name": "Anna", "last_name": "Test", "birth_date": tomorrow, "gender": "female"}, "birth_date"),
            ("patient-update", [self.patient.pk], {"first_name": "Anna", "last_name": "Testowa", "birth_date": "2000-01-03", "gender": "female"}, "birth_date"),
            ("diagnosis-create", [self.patient.pk], {"icd10": self.code.pk, "diagnosed_on": "2000-01-01"}, NON_FIELD_ERRORS),
            ("diagnosis-create", [self.patient.pk], {"icd10": 999999, "diagnosed_on": "2000-01-01"}, "icd10"),
            ("diagnosis-update", [self.patient.pk, self.diagnosis.pk], {"icd10": self.code.pk, "diagnosed_on": "1979-12-31"}, "diagnosed_on"),
            ("visit-create", [self.patient.pk], {"visit_date": tomorrow}, "visit_date"),
            ("visit-update", [self.patient.pk, self.visit.pk], {"visit_date": "bad"}, "visit_date"),
        ]
        for value in ("0", "-1", "NaN", "Infinity", "1.234", "1000000.00"):
            cases.append(("measurement-create", [self.visit.pk], {"kind": "blood_glucose", "value": value}, "value"))
        cases += [
            ("measurement-update", [self.visit.pk, self.measurement.pk], {"kind": "invalid", "value": "1"}, "kind"),
            ("diagnosis-create", [self.patient.pk], {"icd10": self.other_code.pk, "diagnosed_on": "2000-01-01", "notes": "x" * 1001}, "notes"),
            ("visit-create", [self.patient.pk], {"visit_date": "2000-01-01", "notes": "x" * 2001}, "notes"),
        ]
        before = self.mutation_counts()
        for name, args, data, field in cases:
            with self.subTest(name=name, data=data):
                response = self.client.post(self.url(name, *args), data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
                self.assertEqual(before, self.mutation_counts())
        self.patient.refresh_from_db()
        self.diagnosis.refresh_from_db()
        self.visit.refresh_from_db()
        self.measurement.refresh_from_db()
        self.assertEqual(self.patient.birth_date, date(1980, 1, 1))
        self.assertEqual(self.diagnosis.diagnosed_on, date(2000, 1, 1))
        self.assertEqual(self.visit.visit_date, date(2000, 1, 2))
        self.assertEqual(self.measurement.value, Decimal("70.00"))
        self.assertFalse(AuditLog.objects.filter(action__in=["create", "update", "delete"]).exists())

    def test_duplicate_diagnosis_edit_is_rejected_but_unchanged_code_is_valid(self):
        second = Diagnosis.objects.create(patient=self.patient, icd10=self.other_code, diagnosed_on=date(2000, 1, 1))
        response = self.client.post(self.url("diagnosis-update", self.patient.pk, second.pk), {"icd10": self.code.pk, "diagnosed_on": "2000-01-01"})
        self.assertIn(NON_FIELD_ERRORS, response.context["form"].errors)
        second.refresh_from_db()
        self.assertEqual(second.icd10, self.other_code)
        response = self.client.post(self.url("diagnosis-update", self.patient.pk, second.pk), {"icd10": self.other_code.pk, "diagnosed_on": "2000-01-01"})
        self.assertEqual(response.status_code, 302)

    def test_scoped_forms_validate_parent_and_never_expose_parent_or_author_fields(self):
        for form, parent, expected in ((PatientDiagnosisForm, self.patient, ["icd10", "diagnosed_on", "notes"]),
                                       (PatientVisitForm, self.patient, ["visit_date", "notes"]),
                                       (VisitMeasurementForm, self.visit, ["kind", "value"])):
            self.assertEqual(list(form(parent=parent).fields), expected)
        for form, field in ((PatientDiagnosisForm, "diagnosed_on"), (PatientVisitForm, "visit_date")):
            bound = form(parent=self.other, data={field: "1985-01-01", "icd10": self.code.pk})
            self.assertFalse(bound.is_valid())
            self.assertIn(field, bound.errors)

    def test_relationships_cannot_be_reassigned_by_post(self):
        for name, args, data, obj, field, expected in (
            ("diagnosis-update", [self.patient.pk, self.diagnosis.pk], {"patient": self.other.pk, "icd10": self.code.pk, "diagnosed_on": "2000-01-01"}, self.diagnosis, "patient_id", self.patient.pk),
            ("visit-update", [self.patient.pk, self.visit.pk], {"patient": self.other.pk, "visit_date": "2000-01-02", "created_by": self.administrator.pk}, self.visit, "patient_id", self.patient.pk),
            ("measurement-update", [self.visit.pk, self.measurement.pk], {"visit": 999999, "kind": "body_weight", "value": "71"}, self.measurement, "visit_id", self.visit.pk),
        ):
            self.assertEqual(self.client.post(self.url(name, *args), data).status_code, 302)
            obj.refresh_from_db()
            self.assertEqual(getattr(obj, field), expected)
        self.assertEqual(self.visit.created_by, self.personel)

    def test_mismatched_parent_and_missing_object_return_404_without_changes_or_audit(self):
        other_visit = Visit.objects.create(patient=self.other, visit_date=date(2000, 1, 1))
        urls = [self.url("patient-detail", 999999), self.url("patient-update", 999999), self.url("patient-delete", 999999)]
        for kind, obj in (("diagnosis", self.diagnosis), ("visit", self.visit)):
            urls += [self.url(f"{kind}-{action}", self.other.pk, obj.pk) for action in ("detail", "update", "delete")]
            urls += [self.url(f"{kind}-{action}", self.patient.pk, 999999) for action in ("detail", "update", "delete")]
            urls.append(self.url(f"{kind}-create", 999999))
        urls += [self.url(f"measurement-{action}", other_visit.pk, self.measurement.pk) for action in ("detail", "update", "delete")]
        urls += [self.url(f"measurement-{action}", self.visit.pk, 999999) for action in ("detail", "update", "delete")]
        urls.append(self.url("measurement-create", 999999))
        before = self.mutation_counts()
        for url in urls:
            for method in (self.client.get, self.client.post):
                with self.subTest(url=url, method=method.__name__):
                    expected = 405 if method == self.client.post and not url.endswith(("add/", "edit/", "delete/")) else 404
                    self.assertEqual(method(url).status_code, expected)
        self.assertEqual(before, self.mutation_counts())
        self.assertFalse(AuditLog.objects.exists())

    def test_delete_confirmation_get_and_other_http_verbs_cannot_delete(self):
        for name, args in (("patient-delete", [self.patient.pk]), ("diagnosis-delete", [self.patient.pk, self.diagnosis.pk]),
                           ("visit-delete", [self.patient.pk, self.visit.pk]), ("measurement-delete", [self.visit.pk, self.measurement.pk])):
            before = self.mutation_counts()
            url = self.url(name, *args)
            self.assertContains(self.client.get(url), "Czy na pewno")
            for method in (self.client.delete, self.client.put, self.client.patch):
                self.assertEqual(method(url).status_code, 405)
            self.assertEqual(before, self.mutation_counts())
        self.assertFalse(AuditLog.objects.filter(action="delete").exists())

    def test_protected_deletion_has_readable_reason_and_no_delete_audit(self):
        for name, args, text in (("patient-delete", [self.patient.pk], "Pacjent ma przypisane rozpoznania lub wizyty"),
                                 ("visit-delete", [self.patient.pk, self.visit.pk], "Wizyta ma przypisane pomiary")):
            response = self.client.post(self.url(name, *args))
            self.assertContains(response, text)
            self.assertTrue(response.context["form"].non_field_errors())
        self.assertTrue(Patient.objects.filter(pk=self.patient.pk).exists())
        self.assertTrue(Visit.objects.filter(pk=self.visit.pk).exists())
        self.assertFalse(AuditLog.objects.filter(action="delete").exists())

    def test_notes_are_escaped_plain_text_and_audit_contains_only_metadata(self):
        text = '<script>alert("x")</script>\n<b>notatka & dane</b>'
        for obj, name in ((self.diagnosis, "diagnosis"), (self.visit, "visit")):
            obj.notes = text
            obj.save()
            response = self.client.get(self.url(f"{name}-detail", self.patient.pk, obj.pk))
            self.assertContains(response, "&lt;script&gt;")
            self.assertContains(response, "&lt;b&gt;notatka &amp; dane&lt;/b&gt;")
            self.assertNotContains(response, text)
            self.assertNotContains(response, '<script>alert("x")</script>')
        for event in AuditLog.objects.values():
            self.assertNotIn("notatka", str(event))
            self.assertNotIn("<script>", str(event))
        self.assertEqual({field.name for field in AuditLog._meta.fields}, {"id", "created_at", "user", "action", "object_type", "object_id"})

    def test_read_audit_includes_embedded_lists_and_details_and_form_reads(self):
        for url, expected in (
            (self.url("patient-list"), [("read_list", "Patient", ""), ("read_list", "ICD10Code", "")]),
            (self.url("patient-detail", self.patient.pk), [("read_detail", "Patient", str(self.patient.pk)), ("read_list", "Diagnosis", ""), ("read_list", "Visit", "")]),
            (self.url("visit-detail", self.patient.pk, self.visit.pk), [("read_detail", "Visit", str(self.visit.pk)), ("read_list", "Measurement", "")]),
            (self.url("diagnosis-detail", self.patient.pk, self.diagnosis.pk), [("read_detail", "Diagnosis", str(self.diagnosis.pk))]),
            (self.url("measurement-detail", self.visit.pk, self.measurement.pk), [("read_detail", "Measurement", str(self.measurement.pk))]),
            (self.url("visit-update", self.patient.pk, self.visit.pk), [("read_detail", "Visit", str(self.visit.pk))]),
        ):
            AuditLog.objects.all().delete()
            self.client.get(url)
            actual = list(AuditLog.objects.order_by("id").values_list("action", "object_type", "object_id"))
            self.assertEqual(actual, expected)
            self.assertFalse(AuditLog.objects.exclude(user=self.personel).exists())

    def test_audit_failure_rolls_back_create_update_and_delete_for_every_model(self):
        for kind, parent, obj, create_data, update_data, field, original in (
            ("patient", [], self.other, {"first_name": "Nowa", "last_name": "Testowa", "birth_date": "1980-01-01", "gender": "female"}, {"first_name": "Zmiana", "last_name": "Drugi", "birth_date": "1990-01-01", "gender": "male"}, "first_name", "Jan"),
            ("diagnosis", [self.patient.pk], self.diagnosis, {"icd10": self.other_code.pk, "diagnosed_on": "2000-01-01"}, {"icd10": self.code.pk, "diagnosed_on": "2000-01-01", "notes": "Zmiana"}, "notes", ""),
            ("visit", [self.patient.pk], self.visit, {"visit_date": "2000-01-02"}, {"visit_date": "2000-01-02", "notes": "Zmiana"}, "notes", ""),
            ("measurement", [self.visit.pk], self.measurement, {"kind": "blood_glucose", "value": "100"}, {"kind": "body_weight", "value": "80"}, "value", Decimal("70.00")),
        ):
            before = self.mutation_counts()
            for action, args, data in (("create", parent, create_data), ("update", parent + [obj.pk], update_data)):
                with self.subTest(kind=kind, action=action), patch("registry.views.record_audit", side_effect=RuntimeError("Brak audytu")):
                    with self.assertRaisesMessage(RuntimeError, "Brak audytu"):
                        self.client.post(self.url(f"{kind}-{action}", *args), data)
                self.assertEqual(self.mutation_counts(), before)
                obj.refresh_from_db()
                self.assertEqual(getattr(obj, field), original)
        # Usuwamy osobne liście zależności, aby dojść do audytu DELETE.
        empty_visit = Visit.objects.create(patient=self.other, visit_date=date(2000, 1, 1))
        empty_patient = Patient.objects.create(first_name="Test", last_name="Bez zależności", birth_date=date(1980, 1, 1), gender="other")
        for kind, args, model in (("patient", [empty_patient.pk], Patient), ("diagnosis", [self.patient.pk, self.diagnosis.pk], Diagnosis),
                                  ("visit", [self.other.pk, empty_visit.pk], Visit), ("measurement", [self.visit.pk, self.measurement.pk], Measurement)):
            with self.subTest(kind=kind, action="delete"), patch("registry.views.record_audit", side_effect=RuntimeError("Brak audytu")):
                with self.assertRaisesMessage(RuntimeError, "Brak audytu"):
                    self.client.post(self.url(f"{kind}-delete", *args))
            self.assertTrue(model.objects.filter(pk=args[-1]).exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_form_markup_labels_help_errors_date_widgets_and_units(self):
        for name, args in (("patient-create", []), ("diagnosis-create", [self.patient.pk]), ("visit-create", [self.patient.pk]), ("measurement-create", [self.visit.pk])):
            response = self.client.get(self.url(name, *args))
            self.assertNotContains(response, "https://")
            markup = FormMarkup(response.content.decode())
            labels = {attrs.get("for") for tag, attrs in markup.elements if tag == "label"}
            ids = {attrs["id"] for _, attrs in markup.elements if "id" in attrs}
            for tag, attrs in markup.elements:
                if tag in ("input", "select", "textarea") and attrs.get("name") not in (None, "csrfmiddlewaretoken"):
                    self.assertIn(attrs["id"], labels)
                    for description in attrs.get("aria-describedby", "").split():
                        self.assertIn(description, ids)
            response = self.client.post(self.url(name, *args), {})
            markup = FormMarkup(response.content.decode())
            ids = {attrs["id"] for _, attrs in markup.elements if "id" in attrs}
            invalid = [attrs for _, attrs in markup.elements if attrs.get("aria-invalid") == "true"]
            self.assertTrue(invalid)
            for attrs in invalid:
                self.assertTrue(attrs.get("aria-describedby"))
                for description in attrs["aria-describedby"].split():
                    self.assertIn(description, ids)
        response = self.client.get(self.url("patient-update", self.patient.pk))
        self.assertContains(response, 'type="date"')
        self.assertContains(response, 'value="1980-01-01"')
        response = self.client.get(self.url("measurement-update", self.visit.pk, self.measurement.pk))
        self.assertContains(response, 'id="measurement-unit" aria-live="polite">kg</span>')
        self.assertContains(response, "Glukoza we krwi (mg/dL)")
        self.assertContains(response, "/static/registry/measurement-form.js")
        response = self.client.post(self.url("measurement-create", self.visit.pk), {"kind": "blood_glucose", "value": "-1"})
        self.assertContains(response, 'id="measurement-unit" aria-live="polite">mg/dL</span>')

    def test_all_mutations_require_csrf_and_valid_token_allows_full_path(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.personel)
        before = self.mutation_counts()
        for url in self.pages():
            if url.endswith(("add/", "edit/", "delete/")):
                self.assertEqual(secure.post(url).status_code, 403)
        self.assertEqual(self.mutation_counts(), before)
        AuditLog.objects.all().delete()
        secure.get(self.url("patient-create"))
        token = secure.cookies["csrftoken"].value
        response = secure.post(self.url("patient-create"), {"first_name": "CSRF", "last_name": "Test", "birth_date": "1980-01-01", "gender": "other", "csrfmiddlewaretoken": token})
        patient = Patient.objects.get(first_name="CSRF")
        self.assertEqual(response.status_code, 302)
        for name, args, data in (
            ("diagnosis-create", [patient.pk], {"icd10": self.code.pk, "diagnosed_on": "2000-01-01"}),
            ("visit-create", [patient.pk], {"visit_date": "2000-01-01"}),
        ):
            self.assertEqual(secure.post(self.url(name, *args), {**data, "csrfmiddlewaretoken": token}).status_code, 302)
        visit = patient.visits.get()
        self.assertEqual(secure.post(self.url("measurement-create", visit.pk), {"kind": "body_weight", "value": "70", "csrfmiddlewaretoken": token}).status_code, 302)
        for name, args, data in (
            ("patient-update", [patient.pk], {"first_name": "CSRF", "last_name": "Zmieniony", "birth_date": "1980-01-01", "gender": "other"}),
            ("diagnosis-update", [patient.pk, patient.diagnoses.get().pk], {"icd10": self.code.pk, "diagnosed_on": "2000-01-01", "notes": "Zmiana"}),
            ("visit-update", [patient.pk, visit.pk], {"visit_date": "2000-01-02"}),
            ("measurement-update", [visit.pk, visit.measurements.get().pk], {"kind": "blood_glucose", "value": "100"}),
        ):
            self.assertEqual(secure.post(self.url(name, *args), {**data, "csrfmiddlewaretoken": token}).status_code, 302)
        for name, args in (("measurement-delete", [visit.pk, visit.measurements.get().pk]), ("visit-delete", [patient.pk, visit.pk]),
                           ("diagnosis-delete", [patient.pk, patient.diagnoses.get().pk]), ("patient-delete", [patient.pk])):
            self.assertEqual(secure.post(self.url(name, *args), {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertFalse(Patient.objects.filter(pk=patient.pk).exists())
