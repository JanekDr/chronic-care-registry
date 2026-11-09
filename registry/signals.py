from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .models import AuditLog
from .services import record_audit


@receiver(user_logged_in, dispatch_uid="registry.audit.login")
def audit_login(sender, request, user, **kwargs):
    record_audit(
        user=user,
        action=AuditLog.Action.LOGIN,
        object_type="User",
        object_id=user.pk,
    )


@receiver(user_logged_out, dispatch_uid="registry.audit.logout")
def audit_logout(sender, request, user, **kwargs):
    if user is not None and user.is_authenticated:
        record_audit(
            user=user,
            action=AuditLog.Action.LOGOUT,
            object_type="User",
            object_id=user.pk,
        )
