import os
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils.crypto import get_random_string

from registry.models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Visit

from .report_sample import create_report_sample


class SeedDemoTests(TestCase):
    def setUp(self):
        self.passwords = {"DEMO_ADMIN_PASSWORD": get_random_string(40),
                          "DEMO_PERSONEL_PASSWORD": get_random_string(40)}

    def seed(self, passwords=None):
        output = StringIO()
        with patch.dict(os.environ, passwords if passwords is not None else self.passwords, clear=True):
            call_command("seed_demo", stdout=output)
        for password in self.passwords.values():
            self.assertNotIn(password, output.getvalue())

    def snapshot(self):
        return {model.__name__: list(model.objects.order_by("pk").values())
                for model in (get_user_model(), Group, Patient, ICD10Code, Diagnosis, Visit, Measurement, AuditLog)}

    def test_seed_creates_valid_synthetic_graph_and_roles(self):
        self.seed()
        users = get_user_model()
        administrator = users.objects.get(username="demo-admin")
        personel = users.objects.get(username="demo-personel")
        self.assertTrue(administrator.is_superuser and administrator.is_staff and administrator.is_active)
        self.assertFalse(personel.is_staff or personel.is_superuser)
        self.assertTrue(personel.groups.filter(name="personel").exists())
        self.assertTrue(administrator.check_password(self.passwords["DEMO_ADMIN_PASSWORD"]))
        self.assertTrue(personel.check_password(self.passwords["DEMO_PERSONEL_PASSWORD"]))
        self.assertEqual(Patient.objects.count(), 10)
        self.assertEqual(Diagnosis.objects.count(), 10)
        self.assertEqual(Visit.objects.count(), 20)
        self.assertEqual(Measurement.objects.count(), 40)
        self.assertSetEqual(set(ICD10Code.objects.values_list("code", flat=True)), {"I10", "E11.9"})
        self.assertSetEqual(set(Measurement.objects.values_list("kind", flat=True)), {"body_weight", "blood_glucose"})
        self.assertTrue(all(visit.created_by == personel for visit in Visit.objects.all()))
        for model in (Patient, Diagnosis, Visit, Measurement):
            for obj in model.objects.all():
                obj.full_clean()
        self.assertEqual(AuditLog.objects.count(), 85)  # 82 dane + 2 konta + grupa.

    def test_second_run_is_noop_without_passwords(self):
        self.seed()
        snapshot = self.snapshot()
        self.seed(passwords={})
        self.assertEqual(self.snapshot(), snapshot)

    def test_second_run_preserves_edits_passwords_roles_and_ids(self):
        self.seed()
        patient = Patient.objects.get(pk=10001)
        patient.first_name = "Imię po zmianie"
        patient.last_name = "Nazwisko po zmianie"
        patient.save()
        diagnosis = Diagnosis.objects.get(pk=10001)
        diagnosis.notes = "Zmieniona notatka"
        diagnosis.diagnosed_on -= timedelta(days=1)
        diagnosis.save()
        visit = Visit.objects.get(pk=10001)
        visit.visit_date -= timedelta(days=1)
        visit.notes = "Zmieniona wizyta"
        visit.save()
        measurement = Measurement.objects.get(pk=10001)
        measurement.value = Decimal("222.22")
        measurement.save()
        code = ICD10Code.objects.get(pk=10001)
        code.code = "I15"
        code.name = "Zmieniony słownik"
        code.save()
        personel = get_user_model().objects.get(pk=10002)
        personel.username = "zmieniony-login"
        personel.is_active = False
        personel.set_password(get_random_string(40))
        personel.save()
        personel.groups.clear()
        snapshot = self.snapshot()
        self.seed(passwords={"DEMO_PERSONEL_PASSWORD": get_random_string(40)})
        self.assertEqual(self.snapshot(), snapshot)
        self.assertFalse(personel.groups.exists())

    def test_missing_either_password_leaves_no_partial_data(self):
        for missing in self.passwords:
            with self.subTest(variable=missing):
                env = {key: value for key, value in self.passwords.items() if key != missing}
                with patch.dict(os.environ, env, clear=True), self.assertRaisesMessage(CommandError, missing):
                    call_command("seed_demo", stdout=StringIO())
                self.assertEqual(self.snapshot(), {key: [] for key in self.snapshot()})

    def test_weak_password_rejected(self):
        env = {**self.passwords, "DEMO_PERSONEL_PASSWORD": "123"}
        with patch.dict(os.environ, env, clear=True), self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(get_user_model().objects.exists())

    def test_failure_in_audit_rolls_back_whole_seed(self):
        with patch.dict(os.environ, self.passwords, clear=True), patch(
            "registry.management.commands.seed_demo.record_audit", side_effect=RuntimeError("test rollback")
        ), self.assertRaises(RuntimeError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(Group.objects.exists())
        self.assertFalse(Patient.objects.exists())

    def test_existing_named_accounts_and_dictionary_are_preserved(self):
        personel = get_user_model().objects.create_user("demo-personel", password=get_random_string(40))
        code = ICD10Code.objects.create(code="I10", name="Nazwa administratora")
        password_hash = personel.password
        self.seed(passwords={"DEMO_ADMIN_PASSWORD": self.passwords["DEMO_ADMIN_PASSWORD"]})
        personel.refresh_from_db()
        code.refresh_from_db()
        self.assertEqual(personel.password, password_hash)
        self.assertFalse(personel.groups.exists())
        self.assertEqual(code.name, "Nazwa administratora")
        self.assertEqual(ICD10Code.objects.count(), 2)

    def test_report_sample_is_separate_from_demo_data(self):
        sample = create_report_sample()
        self.seed()
        self.assertEqual(Patient.objects.count(), 13)
        self.assertEqual(sample["patients"]["C"].visits.count(), 0)
        self.assertEqual(sample["patients"]["A"].visits.filter(visit_date__month=10).count(), 2)
