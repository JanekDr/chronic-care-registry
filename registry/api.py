from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from drf_spectacular.utils import extend_schema_view
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException
from rest_framework.response import Response

from .api_filters import DiagnosisFilters, ICD10Filters, MeasurementFilters, PatientFilters, VisitFilters
from .api_schema import crud_schema, detail_schema, list_schema
from .models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Report, Visit
from .serializers import (
    DiagnosisSerializer,
    ICD10CodeSerializer,
    MeasurementSerializer,
    PatientSerializer,
    ReportSerializer,
    VisitSerializer,
)
from .services import PATIENT_DELETE_BLOCKED, VISIT_DELETE_BLOCKED, filter_patients, record_audit


class ProtectedDelete(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "protected_delete"


class RegistryReadMixin:
    query_serializer_class = None

    def record_access(self, action, object_id=""):
        record_audit(
            user=self.request.user, action=action,
            object_type=self.queryset.model._meta.object_name, object_id=object_id,
        )

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.action == "list" and self.query_serializer_class is not None:
            # Waliduj także jawnie przekazane puste wartości, np. pustą datę.
            filters = self.query_serializer_class(data=self.request.query_params.dict())
            filters.is_valid(raise_exception=True)
            return self.filter_list(queryset, **filters.validated_data)
        return queryset

    def filter_list(self, queryset, **filters):
        return queryset.filter(**filters)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        self.record_access(AuditLog.Action.READ_LIST)
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = self.get_serializer(instance).data
        self.record_access(AuditLog.Action.READ_DETAIL, instance.pk)
        return Response(data)


class RegistryModelViewSet(RegistryReadMixin, viewsets.ModelViewSet):
    delete_blocked_message = "Rekord ma powiązane dane."

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        instance = serializer.save()
        self.record_access(AuditLog.Action.CREATE, instance.pk)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.record_access(AuditLog.Action.UPDATE, instance.pk)

    def perform_destroy(self, instance):
        object_id = instance.pk
        try:
            instance.delete()
        except ProtectedError as exc:
            raise ProtectedDelete(self.delete_blocked_message) from exc
        self.record_access(AuditLog.Action.DELETE, object_id)


@crud_schema(PatientSerializer, filters=PatientFilters, delete_blocked_message=PATIENT_DELETE_BLOCKED)
class PatientViewSet(RegistryModelViewSet):
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    query_serializer_class = PatientFilters
    delete_blocked_message = PATIENT_DELETE_BLOCKED
    filter_list = staticmethod(filter_patients)


@crud_schema(DiagnosisSerializer, filters=DiagnosisFilters)
class DiagnosisViewSet(RegistryModelViewSet):
    queryset = Diagnosis.objects.all()
    serializer_class = DiagnosisSerializer
    query_serializer_class = DiagnosisFilters


@crud_schema(VisitSerializer, filters=VisitFilters, delete_blocked_message=VISIT_DELETE_BLOCKED)
class VisitViewSet(RegistryModelViewSet):
    queryset = Visit.objects.all()
    serializer_class = VisitSerializer
    query_serializer_class = VisitFilters
    delete_blocked_message = VISIT_DELETE_BLOCKED

    def filter_list(self, queryset, date_from=None, date_to=None, **filters):
        if date_from is not None:
            filters["visit_date__gte"] = date_from
        if date_to is not None:
            filters["visit_date__lte"] = date_to
        return queryset.filter(**filters)


@crud_schema(MeasurementSerializer, filters=MeasurementFilters)
class MeasurementViewSet(RegistryModelViewSet):
    queryset = Measurement.objects.all()
    serializer_class = MeasurementSerializer
    query_serializer_class = MeasurementFilters


@crud_schema(ReportSerializer)
class ReportViewSet(RegistryModelViewSet):
    queryset = Report.objects.all()
    serializer_class = ReportSerializer

    # Serwisy zapisu raportu przeliczają wynik i rejestrują zmianę razem z zapisem.
    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()


@extend_schema_view(list=list_schema(ICD10CodeSerializer, ICD10Filters), retrieve=detail_schema(ICD10CodeSerializer))
class ICD10CodeViewSet(RegistryReadMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ICD10Code.objects.all()
    serializer_class = ICD10CodeSerializer
    query_serializer_class = ICD10Filters

    def filter_list(self, queryset, search=""):
        return queryset.filter(Q(code__icontains=search) | Q(name__icontains=search))
