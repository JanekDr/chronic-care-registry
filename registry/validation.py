"""Reguły modeli wspólne dla ModelForm i przyszłych serializerów REST."""

from copy import copy
from datetime import date

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone


def validate_not_future(value):
    if value > timezone.localdate():
        raise ValidationError("Data nie może być przyszła.", code="future_date")


def validate_positive_decimal(value):
    # DecimalField.to_python odrzuca także NaN i nieskończoności.
    if not value.is_finite() or value <= 0:
        raise ValidationError("Podaj dodatnią, skończoną wartość.", code="positive_decimal")


def validate_patient_date(instance, field_name):
    value = getattr(instance, field_name)
    if not isinstance(value, date):
        return  # full_clean zgłosi błąd typu pola; clean nadal jest wywoływane.
    try:
        patient = instance.patient
    except (ObjectDoesNotExist, ValueError, TypeError):
        return  # Nieistniejący lub błędny FK sprawdza full_clean.
    if isinstance(patient.birth_date, date) and value < patient.birth_date:
        raise ValidationError({field_name: "Data nie może poprzedzać daty urodzenia pacjenta."})


def validate_model_instance(instance, attrs=None):
    """Sprawdź pełny stan obiektu bez zapisu i bez zmiany oryginału.

    ModelForm wywołuje full_clean automatycznie. Serializery mają przekazać tu
    nową instancję albo istniejący obiekt i attrs (również dla PATCH), zamienić
    ValidationError.message_dict na błędy DRF i użyć znormalizowanych pól wyniku.
    Brakujące attrs zachowują wartości istniejącego obiektu. save() ani
    QuerySet.update/bulk_create nie uruchamiają tej walidacji.
    """
    candidate = copy(instance)
    candidate._state = copy(instance._state)
    candidate._state.fields_cache = instance._state.fields_cache.copy()
    for name, value in (attrs or {}).items():
        setattr(candidate, name, value)
    candidate.full_clean()
    return candidate
