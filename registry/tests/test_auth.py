from html.parser import HTMLParser

from django.contrib.staticfiles import finders
from django.core.exceptions import NON_FIELD_ERRORS
from django.test import Client
from django.urls import reverse

from registry.models import AuditLog

from .base import RoleTestCase


class FormMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class AuthenticationTests(RoleTestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def login(self, **overrides):
        self.client.get(reverse("login"))
        data = {
            "username": self.personel.username,
            "password": self.password,
            "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
        }
        data.update(overrides)
        return self.client.post(reverse("login"), data)

    def test_login_with_csrf_creates_session_and_one_audit_entry(self):
        self.assertRedirects(self.login(), reverse("registry:patient-list"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.personel.pk)
        entry = AuditLog.objects.get(action=AuditLog.Action.LOGIN)
        self.assertEqual(entry.user, self.personel)
        self.assertEqual(entry.object_type, "User")
        self.assertEqual(entry.object_id, str(self.personel.pk))

    def test_login_without_csrf_is_rejected(self):
        response = self.client.post(
            reverse("login"), {"username": self.personel.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(AuditLog.objects.exists())

    def test_invalid_credentials_do_not_create_session_or_login_audit(self):
        response = self.login(password="invalid")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].has_error(NON_FIELD_ERRORS, "invalid_login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(AuditLog.objects.exists())

    def test_inactive_account_cannot_login(self):
        self.personel.is_active = False
        self.personel.save(update_fields=["is_active"])
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(AuditLog.objects.exists())

    def test_logout_requires_post_and_valid_csrf(self):
        self.login()
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("logout")).status_code, 403)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.LOGOUT).exists())
        response = self.client.post(
            reverse("logout"),
            {"csrfmiddlewaretoken": self.client.cookies["csrftoken"].value},
        )
        self.assertRedirects(response, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        entry = AuditLog.objects.get(action=AuditLog.Action.LOGOUT)
        self.assertEqual(entry.user, self.personel)
        self.assertEqual(entry.object_id, str(self.personel.pk))

    def test_login_accepts_local_next_but_rejects_external_redirect(self):
        self.assertRedirects(self.login(next=reverse("registry:report-list")), reverse("registry:report-list"))
        self.assertRedirects(self.login(next="https://example.com/"), reverse("registry:patient-list"))

    def test_account_without_role_cannot_read_registry_after_login(self):
        response = self.login(username=self.outsider.username)
        self.assertRedirects(
            response, reverse("registry:patient-list"), fetch_redirect_response=False,
        )
        self.assertEqual(self.client.get(response.url).status_code, 403)

    def test_form_uses_local_assets_labels_and_help_description(self):
        response = self.client.get(reverse("login"))
        markup = FormMarkup(response.content.decode())
        self.assertContains(response, '<html lang="pl">')
        self.assertContains(response, 'class="form-control"')
        self.assertNotContains(response, "https://")
        ids = {attrs["id"] for _, attrs in markup.elements if "id" in attrs}
        labels = {attrs.get("for") for tag, attrs in markup.elements if tag == "label"}
        inputs = {
            attrs["name"]: attrs for tag, attrs in markup.elements
            if tag == "input" and attrs.get("name") in ["username", "password"]
        }
        for attrs in inputs.values():
            self.assertIn(attrs["id"], labels)
        described_by = inputs["username"].get("aria-describedby", "").split()
        self.assertTrue(described_by)
        for description in described_by:
            self.assertIn(description, ids)
        for asset in ["vendor/bootstrap/css/bootstrap.min.css", "vendor/bootstrap/js/bootstrap.bundle.min.js"]:
            self.assertIsNotNone(finders.find(asset))
            self.assertContains(response, f'/static/{asset}')

    def test_required_errors_are_associated_with_fields(self):
        response = self.login(username="", password="")
        markup = FormMarkup(response.content.decode())
        ids = {attrs["id"] for _, attrs in markup.elements if "id" in attrs}
        inputs = [
            attrs for tag, attrs in markup.elements
            if tag == "input" and attrs.get("name") in ["username", "password"]
        ]
        self.assertEqual(len(inputs), 2)
        for attrs in inputs:
            self.assertEqual(attrs.get("aria-invalid"), "true")
            descriptions = attrs.get("aria-describedby", "").split()
            self.assertTrue(descriptions)
            for description in descriptions:
                self.assertIn(description, ids)
