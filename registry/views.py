from django.views.generic import TemplateView

from .permissions import RegistryAccessMixin


class PatientListView(RegistryAccessMixin, TemplateView):
    """Strona wejściowa; lista z bazy zostanie dodana wraz z CRUD pacjentów."""

    template_name = "registry/patient_list.html"


class ReportListView(RegistryAccessMixin, TemplateView):
    template_name = "registry/report_list.html"
