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
