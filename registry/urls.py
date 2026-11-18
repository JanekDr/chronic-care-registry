from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "registry"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="registry:patient-list"), name="home"),
    path("patients/", views.PatientListView.as_view(), name="patient-list"),
    path("patients/add/", views.PatientCreateView.as_view(), name="patient-create"),
    path("patients/<int:pk>/", views.PatientDetailView.as_view(), name="patient-detail"),
    path("patients/<int:pk>/edit/", views.PatientUpdateView.as_view(), name="patient-update"),
    path("patients/<int:pk>/delete/", views.PatientDeleteView.as_view(), name="patient-delete"),
    path("patients/<int:patient_pk>/diagnoses/add/", views.DiagnosisCreateView.as_view(), name="diagnosis-create"),
    path("patients/<int:patient_pk>/diagnoses/<int:pk>/", views.DiagnosisDetailView.as_view(), name="diagnosis-detail"),
    path("patients/<int:patient_pk>/diagnoses/<int:pk>/edit/", views.DiagnosisUpdateView.as_view(), name="diagnosis-update"),
    path("patients/<int:patient_pk>/diagnoses/<int:pk>/delete/", views.DiagnosisDeleteView.as_view(), name="diagnosis-delete"),
    path("patients/<int:patient_pk>/visits/add/", views.VisitCreateView.as_view(), name="visit-create"),
    path("patients/<int:patient_pk>/visits/<int:pk>/", views.VisitDetailView.as_view(), name="visit-detail"),
    path("patients/<int:patient_pk>/visits/<int:pk>/edit/", views.VisitUpdateView.as_view(), name="visit-update"),
    path("patients/<int:patient_pk>/visits/<int:pk>/delete/", views.VisitDeleteView.as_view(), name="visit-delete"),
    path("visits/<int:visit_pk>/measurements/add/", views.MeasurementCreateView.as_view(), name="measurement-create"),
    path("visits/<int:visit_pk>/measurements/<int:pk>/", views.MeasurementDetailView.as_view(), name="measurement-detail"),
    path("visits/<int:visit_pk>/measurements/<int:pk>/edit/", views.MeasurementUpdateView.as_view(), name="measurement-update"),
    path("visits/<int:visit_pk>/measurements/<int:pk>/delete/", views.MeasurementDeleteView.as_view(), name="measurement-delete"),
    path("reports/", views.ReportListView.as_view(), name="report-list"),
    path("reports/add/", views.ReportCreateView.as_view(), name="report-create"),
    path("reports/<int:pk>/", views.ReportDetailView.as_view(), name="report-detail"),
    path("reports/<int:pk>/edit/", views.ReportUpdateView.as_view(), name="report-update"),
    path("reports/<int:pk>/delete/", views.ReportDeleteView.as_view(), name="report-delete"),
]
