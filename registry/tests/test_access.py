from django.contrib.auth.models import Permission
from django.core.exceptions import NON_FIELD_ERRORS
from django.urls import reverse

from registry.models import AuditLog

from .base import RoleTestCase


class RegistryAccessTests(RoleTestCase):
    def test_anonymous_visitors_are_redirected_to_login(self):
        for name in ["registry:patient-list", "registry:report-list"]:
            with self.subTest(name=name):
                url = reverse(name)
                self.assertRedirects(
                    self.client.get(url), f"{reverse('login')}?next={url}",
                )

    def test_authenticated_users_without_role_get_403(self):
        for user in [self.outsider, self.staff_outsider]:
            self.client.force_login(user)
            for name in ["registry:patient-list", "registry:report-list"]:
                with self.subTest(user=user.username, name=name):
                    response = self.client.get(reverse(name))
                    self.assertContains(response, "Brak dostępu", status_code=403)

    def test_personel_and_administrator_can_access_registry(self):
        for user in [self.personel, self.administrator]:
            self.client.force_login(user)
            for name in ["registry:patient-list", "registry:report-list"]:
                with self.subTest(user=user.username, name=name):
                    self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_removing_role_revokes_access_in_existing_session(self):
        self.client.force_login(self.personel)
        self.personel.groups.clear()
        self.assertEqual(
            self.client.get(reverse("registry:patient-list")).status_code, 403,
        )

    def test_deactivated_account_loses_session_access(self):
        self.client.force_login(self.personel)
        self.personel.is_active = False
        self.personel.save(update_fields=["is_active"])
        response = self.client.get(reverse("registry:patient-list"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("login")))

    def test_navigation_exposes_administration_only_to_superuser(self):
        for user in [self.personel, self.administrator]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("registry:patient-list"))
                if user.is_superuser:
                    self.assertContains(response, f'href="{reverse("admin:index")}"')
                else:
                    self.assertNotContains(response, f'href="{reverse("admin:index")}"')
                self.assertContains(response, 'method="post"')
                self.assertContains(response, f'action="{reverse("logout")}"')

    def test_non_superusers_cannot_access_admin_even_with_staff_and_permissions(self):
        self.staff_outsider.user_permissions.add(*Permission.objects.all())
        self.staff_outsider.groups.add(self.personel_group)
        for user in [self.personel, self.outsider, self.staff_outsider]:
            self.client.force_login(user)
            for name in ["admin:index", "admin:registry_auditlog_changelist"]:
                with self.subTest(user=user.username, name=name):
                    response = self.client.get(reverse(name))
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith(reverse("admin:login")))

    def test_admin_login_rejects_staff_without_superuser_role(self):
        response = self.client.post(
            reverse("admin:login"),
            {"username": self.staff_outsider.username, "password": self.password, "next": reverse("admin:index")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].has_error(NON_FIELD_ERRORS, "admin_required"))
        self.assertNotIn("_auth_user_id", self.client.session)


class AuditAdminTests(RoleTestCase):
    def setUp(self):
        self.client.force_login(self.administrator)
        self.entry = AuditLog.objects.create(
            user=self.personel, action=AuditLog.Action.READ_DETAIL,
            object_type="Patient", object_id="42",
        )

    def test_administrator_can_read_audit_list_and_detail(self):
        response = self.client.get(reverse("admin:registry_auditlog_changelist"))
        self.assertContains(response, "Patient")
        response = self.client.get(
            reverse("admin:registry_auditlog_change", args=[self.entry.pk]),
        )
        self.assertContains(response, "42")
        self.assertNotContains(response, 'name="_save"')
        self.assertNotContains(response, 'class="deletelink"')

    def test_even_administrator_cannot_add_change_or_delete_audit(self):
        urls = [
            reverse("admin:registry_auditlog_add"),
            reverse("admin:registry_auditlog_change", args=[self.entry.pk]),
            reverse("admin:registry_auditlog_delete", args=[self.entry.pk]),
        ]
        count = AuditLog.objects.count()
        for url in urls:
            with self.subTest(url=url):
                response = self.client.post(url, {"action": "delete", "object_id": "99"})
                self.assertEqual(response.status_code, 403)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.object_id, "42")
        self.assertEqual(AuditLog.objects.count(), count)

    def test_audit_cannot_be_deleted_by_bulk_action(self):
        count = AuditLog.objects.count()
        self.client.post(
            reverse("admin:registry_auditlog_changelist"),
            {"action": "delete_selected", "_selected_action": [self.entry.pk], "post": "yes"},
        )
        self.assertEqual(AuditLog.objects.count(), count)
