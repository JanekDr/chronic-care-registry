from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from registry.models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Report, Visit

from .base import RoleTestCase


class DataAdminTests(RoleTestCase):
    def setUp(self):
        self.client.force_login(self.administrator)
        self.initial_audit_count = AuditLog.objects.count()
        self.patient = Patient.objects.create(first_name="Anna", last_name="Testowa", birth_date=date(1980, 1, 1), gender="female")
        self.code = ICD10Code.objects.create(code="I10", name="Nadciśnienie")
        self.day = timezone.localdate() - timedelta(days=1)

    def url(self, model, action, obj=None):
        return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_{action}", args=[obj.pk] if obj else None)

    def assert_audit(self, obj, action):
        self.assertTrue(AuditLog.objects.filter(user=self.administrator, action=action,
                                               object_type=obj._meta.object_name, object_id=str(obj.pk)).exists())

    def test_create_update_delete_and_metadata_only_audit(self):
        response = self.client.post(self.url(Diagnosis, "add"), {
            "patient": self.patient.pk, "icd10": self.code.pk, "diagnosed_on": self.day,
            "notes": "Poufna notatka testowa", "_save": "Zapisz",
        })
        self.assertEqual(response.status_code, 302)
        obj = Diagnosis.objects.get()
        self.assert_audit(obj, AuditLog.Action.CREATE)
        response = self.client.post(self.url(Diagnosis, "change", obj), {
            "patient": self.patient.pk, "icd10": self.code.pk, "diagnosed_on": self.day,
            "notes": "Zmieniona notatka", "_save": "Zapisz",
        })
        self.assertEqual(response.status_code, 302)
        self.assert_audit(obj, AuditLog.Action.UPDATE)
        response = self.client.post(self.url(Diagnosis, "delete", obj), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Diagnosis.objects.exists())
        self.assert_audit(obj, AuditLog.Action.DELETE)
        text = str(list(AuditLog.objects.values()))
        self.assertNotIn("notatka", text)
        self.assertEqual(AuditLog.objects.count(), self.initial_audit_count + 3)

    def test_admin_rejects_invalid_dates_duplicates_and_decimals_without_audit(self):
        visit = Visit.objects.create(patient=self.patient, visit_date=self.day)
        diagnosis = Diagnosis.objects.create(patient=self.patient, icd10=self.code, diagnosed_on=self.day)
        cases = (
            (Visit, {"patient": self.patient.pk, "visit_date": "1979-12-31"}, "visit_date"),
            (Diagnosis, {"patient": self.patient.pk, "icd10": self.code.pk, "diagnosed_on": self.day}, "__all__"),
            (Measurement, {"visit": visit.pk, "kind": "body_weight", "value": "Infinity"}, "value"),
            (Patient, {"first_name": "  ", "last_name": "Test", "birth_date": "1980-01-01", "gender": "female"}, "first_name"),
        )
        for model, data, field in cases:
            with self.subTest(model=model):
                response = self.client.post(self.url(model, "add"), data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["adminform"].form.errors)
        self.assertEqual(Diagnosis.objects.get(), diagnosis)
        self.assertEqual(AuditLog.objects.count(), self.initial_audit_count)

    def test_admin_birth_change_and_reassignment_validate_dependencies(self):
        visit = Visit.objects.create(patient=self.patient, visit_date=date(2000, 1, 1))
        response = self.client.post(self.url(Patient, "change", self.patient), {
            "first_name": "Anna", "last_name": "Testowa", "birth_date": "2000-01-02", "gender": "female",
        })
        self.assertIn("birth_date", response.context["adminform"].form.errors)
        child = Patient.objects.create(first_name="Dziecko", last_name="Testowe", birth_date=self.day, gender="female")
        response = self.client.post(self.url(Visit, "change", visit), {"patient": child.pk, "visit_date": visit.visit_date})
        self.assertIn("visit_date", response.context["adminform"].form.errors)
        self.assertEqual(AuditLog.objects.count(), self.initial_audit_count)

    def test_visit_author_is_set_by_server_and_not_changed_by_post(self):
        data = {"patient": self.patient.pk, "visit_date": self.day, "created_by": self.personel.pk}
        response = self.client.post(self.url(Visit, "add"), data)
        self.assertEqual(response.status_code, 302)
        visit = Visit.objects.get()
        self.assertEqual(visit.created_by, self.administrator)
        response = self.client.post(self.url(Visit, "change", visit), data)
        self.assertEqual(response.status_code, 302)
        visit.refresh_from_db()
        self.assertEqual(visit.created_by, self.administrator)

    def test_patient_with_dependencies_cannot_be_deleted(self):
        Visit.objects.create(patient=self.patient, visit_date=self.day)
        response = self.client.post(self.url(Patient, "delete", self.patient), {"post": "yes"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Patient.objects.filter(pk=self.patient.pk).exists())
        self.assertEqual(AuditLog.objects.count(), self.initial_audit_count)

    def test_bulk_deletion_is_disabled_for_all_registered_data(self):
        visit = Visit.objects.create(patient=self.patient, visit_date=self.day)
        measurement = Measurement.objects.create(visit=visit, kind="body_weight", value=Decimal("70.00"))
        report = Report.objects.create(name="Próbka", date_from=self.day, date_to=self.day)
        for obj in (self.patient, self.code, visit, measurement, report, self.personel, self.personel_group):
            with self.subTest(model=type(obj)):
                response = self.client.post(self.url(type(obj), "changelist"), {
                    "action": "delete_selected", "_selected_action": [obj.pk], "post": "yes",
                })
                self.assertIn(response.status_code, (200, 302))
                self.assertTrue(type(obj).objects.filter(pk=obj.pk).exists())
        self.assertEqual(AuditLog.objects.count(), self.initial_audit_count)

    def test_audit_failure_rolls_back_clinical_save(self):
        with patch("registry.admin.record_audit", side_effect=RuntimeError("test rollback")), self.assertRaises(RuntimeError):
            self.client.post(self.url(Visit, "add"), {"patient": self.patient.pk, "visit_date": self.day})
        self.assertFalse(Visit.objects.exists())
        self.assertEqual(AuditLog.objects.count(), self.initial_audit_count)

    def test_accounts_can_be_deactivated_and_cannot_be_deleted(self):
        response = self.client.post(self.url(get_user_model(), "delete", self.personel), {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        response = self.client.post(self.url(get_user_model(), "change", self.personel), {
            "username": self.personel.username, "first_name": "", "last_name": "", "email": "",
            "groups": [self.personel_group.pk], "_save": "Zapisz",
            "date_joined_0": self.personel.date_joined.strftime("%Y-%m-%d"),
            "date_joined_1": "12:00:00",
        })
        self.assertEqual(response.status_code, 302)
        self.personel.refresh_from_db()
        self.assertFalse(self.personel.is_active)
        self.assert_audit(self.personel, AuditLog.Action.UPDATE)

    def test_password_change_is_audited_and_rolls_back_on_audit_failure(self):
        url = reverse("admin:auth_user_password_change", args=[self.personel.pk])
        password = get_random_string(40)
        data = {"password1": password, "password2": password, "usable_password": "true"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.personel.refresh_from_db()
        self.assertTrue(self.personel.check_password(password))
        self.assert_audit(self.personel, AuditLog.Action.UPDATE)
        self.assertNotIn(password, str(list(AuditLog.objects.values())))
        password_hash = self.personel.password
        password2 = get_random_string(40)
        with patch("registry.admin.record_audit", side_effect=RuntimeError("test rollback")), self.assertRaises(RuntimeError):
            self.client.post(url, {"password1": password2, "password2": password2, "usable_password": "true"})
        self.personel.refresh_from_db()
        self.assertEqual(self.personel.password, password_hash)

    def test_dictionary_and_group_edits_are_audited(self):
        response = self.client.post(self.url(ICD10Code, "change", self.code), {"code": "I10", "name": "Nowa nazwa"})
        self.assertEqual(response.status_code, 302)
        self.assert_audit(self.code, AuditLog.Action.UPDATE)
        response = self.client.post(self.url(Group, "add"), {"name": "Grupa testowa"})
        self.assertEqual(response.status_code, 302)
        self.assert_audit(Group.objects.get(name="Grupa testowa"), AuditLog.Action.CREATE)

    def test_account_creation_is_audited_without_password_content(self):
        password = get_random_string(40)
        response = self.client.post(self.url(get_user_model(), "add"), {
            "username": "nowe-konto", "usable_password": "true",
            "password1": password, "password2": password,
        })
        self.assertEqual(response.status_code, 302)
        account = get_user_model().objects.get(username="nowe-konto")
        self.assertTrue(account.check_password(password))
        self.assert_audit(account, AuditLog.Action.CREATE)
        self.assertNotIn(password, str(list(AuditLog.objects.values())))

    def test_personel_cannot_manage_any_registered_data_or_accounts(self):
        self.client.force_login(self.personel)
        for model in (Patient, ICD10Code, Diagnosis, Visit, Measurement, Report, get_user_model(), Group):
            with self.subTest(model=model):
                response = self.client.get(self.url(model, "changelist"))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("admin:login")))

    def test_report_cannot_be_created_or_edited_before_calculator_exists(self):
        report = Report.objects.create(name="Próbka", date_from=self.day, date_to=self.day)
        for action, obj in (("add", None), ("change", report)):
            with self.subTest(action=action):
                self.assertEqual(self.client.post(self.url(Report, action, obj), {"name": "Zmiana"}).status_code, 403)

    def test_author_relations_can_be_set_null_technically(self):
        user = get_user_model().objects.create_user("autor-testowy")
        visit = Visit.objects.create(patient=self.patient, visit_date=self.day, created_by=user)
        report = Report.objects.create(name="Próbka", date_from=self.day, date_to=self.day, created_by=user)
        user.delete()  # Techniczny SET_NULL; interfejs administracji zabrania usuwania.
        visit.refresh_from_db()
        report.refresh_from_db()
        self.assertIsNone(visit.created_by)
        self.assertIsNone(report.created_by)
