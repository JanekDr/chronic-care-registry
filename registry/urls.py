from django.urls import path
from django.views.generic import RedirectView

from .views import PatientListView, ReportListView

app_name = "registry"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="registry:patient-list"), name="home"),
    path("patients/", PatientListView.as_view(), name="patient-list"),
    path("reports/", ReportListView.as_view(), name="report-list"),
]
