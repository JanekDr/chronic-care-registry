from django.contrib.auth.mixins import AccessMixin
from rest_framework.permissions import BasePermission


REGISTRY_ACCESS_DENIED = "Twoje konto nie ma uprawnień do rejestru."


def has_registry_access(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.groups.filter(name="personel").exists())
    )


class RegistryAccessMixin(AccessMixin):
    permission_denied_message = REGISTRY_ACCESS_DENIED

    def dispatch(self, request, *args, **kwargs):
        if not has_registry_access(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


class RegistryPermission(BasePermission):
    message = REGISTRY_ACCESS_DENIED

    def has_permission(self, request, view):
        return has_registry_access(request.user)
