from django.db import transaction

from registry.models import AuditLog
from registry.services import record_audit

from .base import RoleTestCase


class AuditTests(RoleTestCase):
    def test_audit_rolls_back_with_data_change(self):
        original_name = self.personel.first_name
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.personel.first_name = "Zmienione"
                self.personel.save(update_fields=["first_name"])
                record_audit(
                    user=self.personel, action=AuditLog.Action.UPDATE,
                    object_type="User", object_id=self.personel.pk,
                )
                raise RuntimeError("Wycofanie operacji testowej")
        self.personel.refresh_from_db()
        self.assertEqual(self.personel.first_name, original_name)
        self.assertFalse(AuditLog.objects.exists())

    def test_audit_retains_text_identifier_when_user_is_removed(self):
        identifier = str(self.personel.pk)
        entry = record_audit(
            user=self.personel, action=AuditLog.Action.DELETE,
            object_type="User", object_id=self.personel.pk,
        )
        self.personel.delete()
        entry.refresh_from_db()
        self.assertIsNone(entry.user)
        self.assertEqual(entry.object_id, identifier)
        self.assertIsNotNone(entry.created_at)
