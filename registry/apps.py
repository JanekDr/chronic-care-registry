from django.apps import AppConfig


class RegistryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'registry'
    verbose_name = "Rejestr pacjentów"

    def ready(self):
        from . import signals  # noqa: F401 — rejestracja odbiorników sygnałów
