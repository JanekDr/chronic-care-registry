from django.contrib.auth.mixins import AccessMixin


def has_registry_access(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.groups.filter(name="personel").exists())
    )


class RegistryAccessMixin(AccessMixin):
    permission_denied_message = "Twoje konto nie ma uprawnień do rejestru."

    def dispatch(self, request, *args, **kwargs):
        if not has_registry_access(request.user):
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)
