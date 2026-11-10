from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models

from .validation import validate_not_future, validate_patient_date, validate_positive_decimal


class TimestampedModel(models.Model):
    created_at = models.DateTimeField("Utworzono", auto_now_add=True)
    updated_at = models.DateTimeField("Zmieniono", auto_now=True)

    class Meta:
        abstract = True


class Patient(TimestampedModel):
    class Gender(models.TextChoices):
        FEMALE = "female", "Kobieta"
        MALE = "male", "Mężczyzna"
        OTHER = "other", "Inna"

    first_name = models.CharField("Imię", max_length=80)
    last_name = models.CharField("Nazwisko", max_length=80)
    birth_date = models.DateField("Data urodzenia", validators=[validate_not_future])
    gender = models.CharField("Płeć", max_length=7, choices=Gender.choices)

    class Meta:
        ordering = ["last_name", "first_name", "id"]
        verbose_name = "Pacjent"
        verbose_name_plural = "Pacjenci"

    def clean_fields(self, exclude=None):
        for field in ("first_name", "last_name"):
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, value.strip())
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        errors = {}
        for field in ("first_name", "last_name"):
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, value.strip())
            if not getattr(self, field):
                errors[field] = "To pole jest wymagane."
        if self.pk and isinstance(self.birth_date, date):
            if (self.diagnoses.filter(diagnosed_on__lt=self.birth_date).exists()
                    or self.visits.filter(visit_date__lt=self.birth_date).exists()):
                errors["birth_date"] = "Data urodzenia nie może być późniejsza niż istniejące rozpoznania lub wizyty."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.last_name} {self.first_name}"


class ICD10Code(models.Model):
    code = models.CharField("Kod ICD-10", max_length=10, unique=True)
    name = models.CharField("Nazwa", max_length=255)

    class Meta:
        ordering = ["id"]
        verbose_name = "Kod ICD-10"
        verbose_name_plural = "Słownik ICD-10"

    def __str__(self):
        return f"{self.code} — {self.name}"


class Diagnosis(TimestampedModel):
    patient = models.ForeignKey(Patient, verbose_name="Pacjent", on_delete=models.PROTECT, related_name="diagnoses")
    icd10 = models.ForeignKey(ICD10Code, verbose_name="Rozpoznanie ICD-10", on_delete=models.PROTECT, related_name="diagnoses")
    diagnosed_on = models.DateField("Data rozpoznania", validators=[validate_not_future])
    notes = models.TextField("Notatka", blank=True, max_length=1000, validators=[MaxLengthValidator(1000)])

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["patient", "icd10"], name="unique_patient_icd10")]
        verbose_name = "Rozpoznanie"
        verbose_name_plural = "Rozpoznania"

    def clean(self):
        super().clean()
        validate_patient_date(self, "diagnosed_on")

    def __str__(self):
        return f"{self.patient} — {self.icd10.code}"


class Visit(TimestampedModel):
    patient = models.ForeignKey(Patient, verbose_name="Pacjent", on_delete=models.PROTECT, related_name="visits")
    visit_date = models.DateField("Data wizyty", validators=[validate_not_future])
    notes = models.TextField("Notatka", blank=True, max_length=2000, validators=[MaxLengthValidator(2000)])
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Autor", on_delete=models.SET_NULL, null=True, blank=True, related_name="registry_visits")

    class Meta:
        ordering = ["-visit_date", "id"]
        verbose_name = "Wizyta"
        verbose_name_plural = "Wizyty"

    def clean(self):
        super().clean()
        validate_patient_date(self, "visit_date")

    def __str__(self):
        return f"{self.patient} — {self.visit_date}"


class Measurement(TimestampedModel):
    class Kind(models.TextChoices):
        BLOOD_GLUCOSE = "blood_glucose", "Glukoza we krwi"
        BODY_WEIGHT = "body_weight", "Masa ciała"

    visit = models.ForeignKey(Visit, verbose_name="Wizyta", on_delete=models.PROTECT, related_name="measurements")
    kind = models.CharField("Rodzaj", max_length=13, choices=Kind.choices)
    value = models.DecimalField("Wartość", max_digits=8, decimal_places=2, validators=[validate_positive_decimal])

    # Jednostka/kod/kategoria są wyłącznie pochodnymi kind, bez kolumn w bazie.
    DEFINITIONS = {
        Kind.BLOOD_GLUCOSE: {
            "unit": "mg/dL", "loinc": "2339-0", "category": "laboratory",
            "display": "Glucose [Mass/volume] in Blood",
        },
        Kind.BODY_WEIGHT: {
            "unit": "kg", "loinc": "29463-7", "category": "vital-signs",
            "display": "Body weight",
        },
    }

    @property
    def unit(self):
        return self.DEFINITIONS[self.kind]["unit"]

    class Meta:
        ordering = ["id"]
        verbose_name = "Pomiar"
        verbose_name_plural = "Pomiary"

    def __str__(self):
        return f"{self.get_kind_display()}: {self.value} {self.unit}"


class Report(TimestampedModel):
    name = models.CharField("Nazwa", max_length=100)
    date_from = models.DateField("Od")
    date_to = models.DateField("Do")
    icd10 = models.ForeignKey(ICD10Code, verbose_name="Rozpoznanie ICD-10", on_delete=models.PROTECT, null=True, blank=True, related_name="reports")
    result = models.JSONField("Wynik", default=dict, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="Autor", on_delete=models.SET_NULL, null=True, blank=True, related_name="registry_reports")

    class Meta:
        ordering = ["id"]
        verbose_name = "Raport"
        verbose_name_plural = "Raporty"

    def clean(self):
        super().clean()
        if isinstance(self.date_from, date) and isinstance(self.date_to, date) and self.date_from > self.date_to:
            raise ValidationError({"date_to": "Koniec okresu nie może poprzedzać początku."})

    def __str__(self):
        return self.name


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
