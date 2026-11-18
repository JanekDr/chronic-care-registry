from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.forms import ModelForm

from .models import Diagnosis, Measurement, Patient, Report, Visit


class LoginForm(AuthenticationForm):
    """Standardowe uwierzytelnianie Django z etykietą interfejsu rejestru."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Login"
        self.fields["username"].help_text = "Wpisz login nadany przez administratora."


class PatientForm(ModelForm):
    class Meta:
        model = Patient
        fields = ["first_name", "last_name", "birth_date", "gender"]
        widgets = {"birth_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
        help_texts = {"birth_date": "Data nie może być przyszła."}


class DiagnosisForm(ModelForm):
    class Meta:
        model = Diagnosis
        fields = ["patient", "icd10", "diagnosed_on", "notes"]


class VisitForm(ModelForm):
    class Meta:
        model = Visit
        fields = ["patient", "visit_date", "notes"]


class MeasurementForm(ModelForm):
    class Meta:
        model = Measurement
        fields = ["visit", "kind", "value"]


class ReportForm(ModelForm):
    class Meta:
        model = Report
        fields = ["name", "date_from", "date_to", "icd10"]


class ScopedParentFormMixin:
    """FK ustala adres; pozostaje on objęty walidacją modelu i constraints."""

    def __init__(self, *args, parent, **kwargs):
        super().__init__(*args, **kwargs)
        setattr(self.instance, self.parent_field, parent)

    def _get_validation_exclusions(self):
        exclude = super()._get_validation_exclusions()
        exclude.discard(self.parent_field)
        return exclude


class PatientDiagnosisForm(ScopedParentFormMixin, DiagnosisForm):
    parent_field = "patient"

    class Meta(DiagnosisForm.Meta):
        fields = ["icd10", "diagnosed_on", "notes"]
        widgets = {
            "diagnosed_on": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "diagnosed_on": "Od daty urodzenia pacjenta do dnia dzisiejszego.",
            "notes": "Opcjonalnie, do 1000 znaków.",
        }


class PatientVisitForm(ScopedParentFormMixin, VisitForm):
    parent_field = "patient"

    class Meta(VisitForm.Meta):
        fields = ["visit_date", "notes"]
        widgets = {
            "visit_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 5}),
        }
        help_texts = {
            "visit_date": "Od daty urodzenia pacjenta do dnia dzisiejszego.",
            "notes": "Opcjonalnie, do 2000 znaków.",
        }


class VisitMeasurementForm(ScopedParentFormMixin, MeasurementForm):
    parent_field = "visit"

    class Meta(MeasurementForm.Meta):
        fields = ["kind", "value"]
        help_texts = {"value": "Wartość dodatnia, do dwóch miejsc po przecinku. Glukoza: mg/dL; masa ciała: kg."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].choices = [("", "---------")] + [
            (kind, f"{label} ({Measurement.DEFINITIONS[kind]['unit']})")
            for kind, label in Measurement.Kind.choices
        ]
