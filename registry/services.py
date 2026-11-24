from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from .models import AuditLog, Diagnosis, Measurement, Report, Visit


PATIENT_DELETE_BLOCKED = (
    "Pacjent ma przypisane rozpoznania lub wizyty. Najpierw usuń rozpoznania, pomiary i wizyty."
)
VISIT_DELETE_BLOCKED = "Wizyta ma przypisane pomiary. Najpierw usuń pomiary."


def filter_patients(queryset, *, search="", icd10=""):
    for term in search.split():
        queryset = queryset.filter(Q(first_name__icontains=term) | Q(last_name__icontains=term))
    code = icd10.strip()
    if code:
        queryset = queryset.filter(diagnoses__icd10__code=code)
    return queryset


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


def calculate_report(*, date_from, date_to, icd10_id=None):
    """Wynik dla domkniętego okresu; Decimal, zaokrąglenie ROUND_HALF_UP.

    Parametr ICD-10 to klucz słownika lub None. Funkcja nie zapisuje raportu
    ani audytu, dzięki czemu może być użyta przez HTML, Admin i API.
    """
    parameters = Report(name="Raport", date_from=date_from, date_to=date_to, icd10_id=icd10_id)
    parameters.full_clean()
    visits = Visit.objects.filter(visit_date__gte=parameters.date_from, visit_date__lte=parameters.date_to)
    if parameters.icd10_id is not None:
        diagnoses = Diagnosis.objects.filter(
            patient_id=OuterRef("patient_id"), icd10_id=parameters.icd10_id,
            diagnosed_on__lte=OuterRef("visit_date"),
        )
        visits = visits.filter(Exists(diagnoses))
    result = {
        "patient_count": visits.order_by().values("patient_id").distinct().count(),
        "visit_count": visits.count(),
        "measurements": [],
    }
    # SQLite AVG konwertuje do float. Sumujemy wartości Decimal z ORM.
    values = {kind: [] for kind in Measurement.Kind.values}
    for kind, value in Measurement.objects.filter(visit__in=visits).values_list("kind", "value"):
        values[kind].append(value)
    for kind in Measurement.Kind.values:
        samples = values[kind]
        stats = {"kind": kind, "unit": Measurement.DEFINITIONS[kind]["unit"],
                 "count": len(samples), "avg": None, "min": None, "max": None}
        if samples:
            for key, value in (("avg", sum(samples, Decimal("0")) / len(samples)),
                               ("min", min(samples)), ("max", max(samples))):
                stats[key] = format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")
        result["measurements"].append(stats)
    return result


@transaction.atomic
def save_report(*, report, user):
    """Każdy zapis odświeża migawkę i audyt w jednej transakcji."""
    action = AuditLog.Action.UPDATE if report.pk else AuditLog.Action.CREATE
    if not report.pk:
        report.created_by = user
    report.full_clean()
    report.result = calculate_report(date_from=report.date_from, date_to=report.date_to, icd10_id=report.icd10_id)
    report.save()
    record_audit(user=user, action=action, object_type="Report", object_id=report.pk)
    return report
