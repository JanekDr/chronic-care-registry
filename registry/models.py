from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "Logowanie"
        LOGOUT = "logout", "Wylogowanie"
        READ_LIST = "read_list", "Odczyt listy"
        READ_DETAIL = "read_detail", "Odczyt szczegółów"
        CREATE = "create", "Utworzenie"
        UPDATE = "update", "Edycja"
        DELETE = "delete", "Usunięcie"
        FHIR_EXPORT = "fhir_export", "Eksport FHIR"

    created_at = models.DateTimeField("Czas", auto_now_add=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Użytkownik",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField("Akcja", max_length=30, choices=Action.choices)
    object_type = models.CharField("Typ obiektu", max_length=40)
    object_id = models.CharField("Identyfikator obiektu", max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Wpis audytu"
        verbose_name_plural = "Rejestr dostępu"

    def __str__(self):
        return f"{self.get_action_display()}: {self.object_type} {self.object_id}".strip()
