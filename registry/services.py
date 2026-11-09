from .models import AuditLog


def record_audit(*, user, action, object_type, object_id=""):
    """Zapisz metadane zdarzenia w bieżącej transakcji wywołującego.

    Zapis danych i wywołanie tej funkcji obejmować wspólnym transaction.atomic().
    Nie przekazywać treści notatek, haseł ani pełnych odpowiedzi.
    """
    return AuditLog.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else "",
    )
