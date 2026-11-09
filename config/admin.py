from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError


class AdministratorAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise ValidationError(
                "Dostęp do administracji wymaga konta administratora.",
                code="admin_required",
            )


class RegistryAdminSite(AdminSite):
    login_form = AdministratorAuthenticationForm
    site_header = "Administracja rejestru pacjentów"
    site_title = "Rejestr pacjentów"
    index_title = "Administracja"

    def has_permission(self, request):
        return super().has_permission(request) and request.user.is_superuser

