from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import api
from .api_schema import RegistrySchemaView

app_name = "api"

router = SimpleRouter()
router.register("patients", api.PatientViewSet)
router.register("diagnoses", api.DiagnosisViewSet)
router.register("visits", api.VisitViewSet)
router.register("measurements", api.MeasurementViewSet)
router.register("reports", api.ReportViewSet)
router.register("icd10", api.ICD10CodeViewSet)

urlpatterns = [
    path("schema/", RegistrySchemaView.as_view(), name="schema"),
    path("v1/", include(router.urls)),
]
