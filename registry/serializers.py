from django.core.exceptions import NON_FIELD_ERRORS, ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiExample, extend_schema_field, extend_schema_serializer
from rest_framework import serializers
from rest_framework.settings import api_settings

from .models import Diagnosis, ICD10Code, Measurement, Patient, Report, Visit
from .services import save_report
from .validation import validate_model_instance


class ValidatedModelSerializer(serializers.ModelSerializer):
    class Meta:
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        instance = self.instance if self.instance is not None else self.Meta.model()
        try:
            validated = validate_model_instance(instance, attrs)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY if name == NON_FIELD_ERRORS else name: errors
                for name, errors in exc.message_dict.items()
            }) from exc
        return {name: getattr(validated, name) for name in attrs}


class PatientSerializer(ValidatedModelSerializer):
    class Meta(ValidatedModelSerializer.Meta):
        model = Patient
        fields = ("id", "first_name", "last_name", "birth_date", "gender", "created_at", "updated_at")


class ICD10CodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ICD10Code
        fields = read_only_fields = ("id", "code", "name")


class DiagnosisSerializer(ValidatedModelSerializer):
    patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(), pk_field=serializers.IntegerField(),
        help_text="Identyfikator pacjenta.",
    )
    icd10 = serializers.PrimaryKeyRelatedField(
        queryset=ICD10Code.objects.all(), pk_field=serializers.IntegerField(),
        help_text="Identyfikator wpisu w słowniku ICD-10.",
    )

    class Meta(ValidatedModelSerializer.Meta):
        model = Diagnosis
        fields = ("id", "patient", "icd10", "diagnosed_on", "notes", "created_at", "updated_at")
        extra_kwargs = {"notes": {"default": ""}}
        validators = []  # Unikalność pary (patient, icd10) sprawdza full_clean().


class VisitSerializer(ValidatedModelSerializer):
    patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(), pk_field=serializers.IntegerField(),
        help_text="Identyfikator pacjenta.",
    )

    class Meta(ValidatedModelSerializer.Meta):
        model = Visit
        fields = ("id", "patient", "visit_date", "notes", "created_by", "created_at", "updated_at")
        read_only_fields = (*ValidatedModelSerializer.Meta.read_only_fields, "created_by")
        extra_kwargs = {"notes": {"default": ""}}

    def create(self, validated_data):
        return super().create({**validated_data, "created_by": self.context["request"].user})


MEASUREMENT_EXAMPLE = {"visit": 1, "kind": "blood_glucose", "value": "100.00"}


@extend_schema_serializer(examples=[
    OpenApiExample("Pomiar glukozy", value=MEASUREMENT_EXAMPLE, request_only=True),
    OpenApiExample(
        "Zapisany pomiar glukozy",
        value={
            **MEASUREMENT_EXAMPLE, "id": 1,
            "created_at": "2026-11-24T10:30:00+01:00", "updated_at": "2026-11-24T10:30:00+01:00",
        },
        response_only=True,
    ),
])
class MeasurementSerializer(ValidatedModelSerializer):
    visit = serializers.PrimaryKeyRelatedField(
        queryset=Visit.objects.all(), pk_field=serializers.IntegerField(),
        help_text="Identyfikator wizyty, z której wynikają pacjent i data pomiaru.",
    )

    class Meta(ValidatedModelSerializer.Meta):
        model = Measurement
        fields = ("id", "visit", "kind", "value", "created_at", "updated_at")
        extra_kwargs = {
            "value": {
                "coerce_to_string": True,
                "help_text": "Dodatnia wartość z dokładnością do dwóch miejsc. Glukoza w mg/dL, masa ciała w kg.",
            },
        }


class MeasurementStatisticsSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Measurement.Kind.choices)
    unit = serializers.ChoiceField(choices=[definition["unit"] for definition in Measurement.DEFINITIONS.values()])
    count = serializers.IntegerField(min_value=0)
    avg = serializers.CharField(allow_null=True, help_text="Średnia z dokładnością do dwóch miejsc po przecinku.")
    min = serializers.CharField(allow_null=True, help_text="Najmniejsza wartość z dokładnością do dwóch miejsc po przecinku.")
    max = serializers.CharField(allow_null=True, help_text="Największa wartość z dokładnością do dwóch miejsc po przecinku.")


class ReportResultSerializer(serializers.Serializer):
    patient_count = serializers.IntegerField(min_value=0, help_text="Liczba różnych pacjentów z wizytami w okresie.")
    visit_count = serializers.IntegerField(min_value=0)
    measurements = MeasurementStatisticsSerializer(many=True)


@extend_schema_field(ReportResultSerializer)
class ReportResultField(serializers.JSONField):
    """Zwraca migawkę zapisaną w bazie. Serializer wyniku opisuje jej kształt w OpenAPI."""


REPORT_EXAMPLE = {"name": "I10 październik", "date_from": "2026-10-01", "date_to": "2026-10-31", "icd10": 1}


@extend_schema_serializer(examples=[
    OpenApiExample("Raport dla I10", value=REPORT_EXAMPLE, request_only=True),
    OpenApiExample(
        "Zapisany raport dla I10",
        value={
            **REPORT_EXAMPLE, "id": 1, "created_by": 1,
            "created_at": "2026-11-24T10:30:00+01:00", "updated_at": "2026-11-24T10:30:00+01:00",
            "result": {
                "patient_count": 1, "visit_count": 2,
                "measurements": [
                    {"kind": "blood_glucose", "unit": "mg/dL", "count": 2, "avg": "110.00", "min": "100.00", "max": "120.00"},
                    {"kind": "body_weight", "unit": "kg", "count": 0, "avg": None, "min": None, "max": None},
                ],
            },
        },
        response_only=True,
    ),
])
class ReportSerializer(ValidatedModelSerializer):
    icd10 = serializers.PrimaryKeyRelatedField(
        queryset=ICD10Code.objects.all(), pk_field=serializers.IntegerField(),
        allow_null=True, default=None,
        help_text="Identyfikator wpisu w słowniku ICD-10. Null obejmuje wszystkie rozpoznania.",
    )
    result = ReportResultField(read_only=True, help_text="Migawka obliczana przy każdym zapisie raportu.")

    class Meta(ValidatedModelSerializer.Meta):
        model = Report
        fields = ("id", "name", "date_from", "date_to", "icd10", "result", "created_by", "created_at", "updated_at")
        read_only_fields = (*ValidatedModelSerializer.Meta.read_only_fields, "created_by")
        extra_kwargs = {
            "date_from": {"help_text": "Początek okresu włącznie."},
            "date_to": {"help_text": "Koniec okresu włącznie."},
            "updated_at": {"help_text": "Moment ostatniego obliczenia raportu."},
        }

    def create(self, validated_data):
        return save_report(report=Report(**validated_data), user=self.context["request"].user)

    def update(self, instance, validated_data):
        for name, value in validated_data.items():
            setattr(instance, name, value)
        return save_report(report=instance, user=self.context["request"].user)
