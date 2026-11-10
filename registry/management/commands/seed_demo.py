"""Mały, powtarzalny zestaw syntetyczny; nie jest próbką odbioru raportu."""

import os
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from registry.models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Visit
from registry.services import record_audit


class Command(BaseCommand):
    help = "Utwórz słownik, konta demo i 10 syntetycznych pacjentów bez nadpisywania danych."

    @transaction.atomic
    def handle(self, *args, **options):
        users = get_user_model()
        accounts = []
        # Sprawdź oba hasła przed zapisem. Istniejące konta zachowują hasła i role.
        for pk, username, variable, is_admin in (
            (10001, "demo-admin", "DEMO_ADMIN_PASSWORD", True),
            (10002, "demo-personel", "DEMO_PERSONEL_PASSWORD", False),
        ):
            account = users.objects.filter(pk=pk).first() or users.objects.filter(username=username).first()
            created = account is None
            if created:
                password = os.environ.get(variable, "")
                if not password.strip():
                    raise CommandError(f"Ustaw {variable} w środowisku, aby utworzyć {username}.")
                account = users(pk=pk, username=username, is_staff=is_admin, is_superuser=is_admin)
                try:
                    validate_password(password, user=account)
                except ValidationError as error:
                    raise CommandError(f"{variable}: {' '.join(error.messages)}") from error
                account.set_password(password)
                account.full_clean()
            accounts.append((account, created))

        administrator = accounts[0][0]
        for account, created in accounts:
            if created:
                account.save()
        group, group_created = Group.objects.get_or_create(name="personel")
        if accounts[1][1]:
            accounts[1][0].groups.add(group)
        for account, created in accounts:
            if created:
                self.audit(administrator, account)
        if group_created:
            self.audit(administrator, group)

        codes = [
            self.ensure(ICD10Code, {"pk": 10001}, {"code": "I10", "name": "Nadciśnienie samoistne (pierwotne)"}, administrator, natural_lookup={"code": "I10"}),
            self.ensure(ICD10Code, {"pk": 10002}, {"code": "E11.9", "name": "Cukrzyca typu 2 bez powikłań"}, administrator, natural_lookup={"code": "E11.9"}),
        ]
        # Stałe identyfikatory, niezależne od edytowalnych nazw/dat/wartości.
        # Zakresy są opisane w README; istniejących rekordów nie modyfikujemy.
        today = timezone.localdate()
        for index in range(10):
            patient = self.ensure(Patient, {"pk": 10001 + index}, {
                "first_name": f"Osoba {index + 1:02d}",
                "last_name": "Demonstracyjna",
                "birth_date": date(1960 + index * 3, 1, index + 1),
                "gender": Patient.Gender.FEMALE if index % 2 == 0 else Patient.Gender.MALE,
            }, administrator)
            self.ensure(Diagnosis, {"pk": 10001 + index}, {
                "patient": patient, "icd10": codes[index % 2],
                "diagnosed_on": today - timedelta(days=60),
                "notes": "Syntetyczne rozpoznanie demonstracyjne.",
            }, administrator)
            for number in range(2):
                visit = self.ensure(Visit, {"pk": 10001 + index * 2 + number}, {
                    "patient": patient, "visit_date": today - timedelta(days=30 - number * 14),
                    "notes": "Syntetyczna wizyta demonstracyjna.", "created_by": accounts[1][0],
                }, administrator)
                for offset, kind, value in (
                    (0, Measurement.Kind.BLOOD_GLUCOSE, Decimal(100 + index * 2 + number * 10)),
                    (1, Measurement.Kind.BODY_WEIGHT, Decimal(60 + index) + Decimal("0.50")),
                ):
                    self.ensure(Measurement, {"pk": 10001 + index * 4 + number * 2 + offset}, {
                        "visit": visit, "kind": kind, "value": value,
                    }, administrator)
        self.stdout.write(self.style.SUCCESS(
            "Inicjalizacja zakończona. Konta: " + ", ".join(account.username for account, _ in accounts) + ". "
            "Istniejące rekordy, role i hasła zachowano."
        ))

    def ensure(self, model, lookup, defaults, user, natural_lookup=None):
        obj = model.objects.filter(**lookup).first()
        if obj is None and natural_lookup:
            obj = model.objects.filter(**natural_lookup).first()
        if obj is None:
            obj = model(**lookup, **defaults)
            try:
                obj.full_clean()
            except ValidationError as error:
                # Błąd bez treści danych klinicznych ani wartości haseł.
                raise CommandError(f"Nie można utworzyć {model.__name__}; sprawdź istniejące dane i zależności.") from error
            obj.save()
            self.audit(user, obj)
        return obj

    @staticmethod
    def audit(user, obj):
        record_audit(user=user, action=AuditLog.Action.CREATE,
                     object_type=obj._meta.object_name, object_id=obj.pk)
