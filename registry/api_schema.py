from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from drf_spectacular.views import SpectacularAPIView
from rest_framework import serializers
from rest_framework.renderers import JSONRenderer

from .fhir import FHIR_JSON_MEDIA_TYPE


class ErrorDetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


FORBIDDEN = OpenApiResponse(
    ErrorDetailSerializer,
    description="Brak sesji, wymaganej roli lub poprawnego tokenu CSRF dla żądania zmieniającego dane.",
)
NOT_FOUND = OpenApiResponse(ErrorDetailSerializer, description="Wskazany rekord lub strona nie istnieje.")
UNSUPPORTED_MEDIA_TYPE = OpenApiResponse(ErrorDetailSerializer, description="Treść żądania musi być w formacie JSON.")
INVALID_FILTERS = OpenApiResponse(
    response={"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
    description="Błąd walidacji parametrów listy.",
)
INVALID_DATA = OpenApiResponse(
    response={
        "type": "object",
        "additionalProperties": {
            "oneOf": [{"type": "array", "items": {"type": "string"}}, {"type": "string"}],
        },
    },
    description="Błąd walidacji pól. Błąd parsowania treści jest zwracany w polu `detail`.",
)
CSRF_HEADER = OpenApiParameter(
    "X-CSRFToken", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True,
    description="Token z ciasteczka `csrftoken` aktualnego po zalogowaniu.",
)


def list_schema(serializer, filters):
    responses = {200: serializer(many=True), 403: FORBIDDEN, 404: NOT_FOUND}
    if filters is not None:
        responses[400] = INVALID_FILTERS
    return extend_schema(parameters=[filters] if filters is not None else [], responses=responses)


def detail_schema(serializer):
    return extend_schema(responses={200: serializer, 403: FORBIDDEN, 404: NOT_FOUND})


def crud_schema(serializer, *, filters=None, delete_blocked_message=None):
    write_errors = {400: INVALID_DATA, 403: FORBIDDEN, 415: UNSUPPORTED_MEDIA_TYPE}
    update_responses = {200: serializer, **write_errors, 404: NOT_FOUND}
    delete_responses = {204: None, 403: FORBIDDEN, 404: NOT_FOUND}
    if delete_blocked_message:
        delete_responses[409] = OpenApiResponse(
            ErrorDetailSerializer, description=delete_blocked_message,
            examples=[OpenApiExample("Powiązane dane", value={"detail": delete_blocked_message})],
        )
    return extend_schema_view(
        list=list_schema(serializer, filters),
        retrieve=detail_schema(serializer),
        create=extend_schema(parameters=[CSRF_HEADER], responses={201: serializer, **write_errors}),
        update=extend_schema(parameters=[CSRF_HEADER], responses=update_responses),
        partial_update=extend_schema(parameters=[CSRF_HEADER], responses=update_responses),
        destroy=extend_schema(parameters=[CSRF_HEADER], responses=delete_responses),
    )


FHIR_BUNDLE_SCHEMA = {
    "type": "object",
    "required": ["resourceType", "type", "timestamp", "entry"],
    "properties": {
        "resourceType": {"type": "string", "enum": ["Bundle"]},
        "type": {"type": "string", "enum": ["collection"]},
        "timestamp": {"type": "string", "format": "date-time"},
        "entry": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["fullUrl", "resource"],
                "properties": {
                    "fullUrl": {"type": "string", "format": "uri", "description": "URN `urn:uuid:{uuid}`."},
                    "resource": {
                        "type": "object",
                        "required": ["resourceType", "id"],
                        "properties": {
                            "resourceType": {
                                "type": "string",
                                "enum": ["Patient", "Condition", "Encounter", "Observation"],
                            },
                            "id": {"type": "string", "format": "uuid"},
                            "valueQuantity": {
                                "type": "object",
                                "description": "Wartość pomiaru w zasobie Observation.",
                                "required": ["value", "unit", "system", "code"],
                                "properties": {
                                    "value": {"type": "number"},
                                    "unit": {"type": "string"},
                                    "system": {"type": "string", "enum": ["http://unitsofmeasure.org"]},
                                    "code": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}

_EXAMPLE_PATIENT_UUID = "c26e52c1-f686-53bd-b7df-853bbcfdfcdf"
_EXAMPLE_ENCOUNTER_UUID = "394360e7-d544-5e06-8d91-2afb3659f5c7"
_EXAMPLE_PATIENT_URL = f"urn:uuid:{_EXAMPLE_PATIENT_UUID}"
_EXAMPLE_ENCOUNTER_URL = f"urn:uuid:{_EXAMPLE_ENCOUNTER_UUID}"
FHIR_BUNDLE_EXAMPLE = {
    "resourceType": "Bundle",
    "type": "collection",
    "timestamp": "2026-11-24T09:30:00Z",
    "entry": [
        {
            "fullUrl": _EXAMPLE_PATIENT_URL,
            "resource": {
                "resourceType": "Patient",
                "id": _EXAMPLE_PATIENT_UUID,
                "identifier": [{"system": "urn:psim:patient-id", "value": "1"}],
                "name": [{"given": ["Ada"], "family": "Przykładowa"}],
                "birthDate": "1990-01-01",
                "gender": "female",
            },
        },
        {
            "fullUrl": "urn:uuid:dc41eb42-942f-5ccc-91b8-7eb9afe74ab5",
            "resource": {
                "resourceType": "Condition",
                "id": "dc41eb42-942f-5ccc-91b8-7eb9afe74ab5",
                "subject": {"reference": _EXAMPLE_PATIENT_URL},
                "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": "I10"}]},
                "clinicalStatus": {"coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"},
                ]},
                "verificationStatus": {"coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"},
                ]},
                "recordedDate": "2026-11-23T09:00:00Z",
            },
        },
        {
            "fullUrl": _EXAMPLE_ENCOUNTER_URL,
            "resource": {
                "resourceType": "Encounter",
                "id": _EXAMPLE_ENCOUNTER_UUID,
                "subject": {"reference": _EXAMPLE_PATIENT_URL},
                "status": "finished",
                "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
                "period": {"start": "2026-11-23"},
            },
        },
        {
            "fullUrl": "urn:uuid:f19d1252-2dfa-52a3-88e1-b8bee3c8d30e",
            "resource": {
                "resourceType": "Observation",
                "id": "f19d1252-2dfa-52a3-88e1-b8bee3c8d30e",
                "subject": {"reference": _EXAMPLE_PATIENT_URL},
                "encounter": {"reference": _EXAMPLE_ENCOUNTER_URL},
                "status": "final",
                "effectiveDateTime": "2026-11-23",
                "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/bodyweight"]},
                "code": {"coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]},
                "category": [{"coding": [
                    {"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"},
                ]}],
                "valueQuantity": {"value": 72.25, "unit": "kg", "system": "http://unitsofmeasure.org", "code": "kg"},
            },
        },
    ],
}

fhir_export_schema = extend_schema(
    summary="Pobierz eksport pacjenta w HL7 FHIR R4",
    description=(
        "Dostęp dla personelu i superużytkowników z aktywną sesją. "
        "Bundle R4 4.0.1 zawiera jednego pacjenta oraz jego rozpoznania, wizyty i pomiary. "
        "Referencje wskazują `fullUrl` w tym samym pliku, a `valueQuantity.value` jest liczbą JSON."
    ),
    external_docs={"url": "https://hl7.org/fhir/R4/bundle.html", "description": "Bundle w FHIR R4 4.0.1"},
    parameters=[
        OpenApiParameter("id", OpenApiTypes.INT, OpenApiParameter.PATH, description="Identyfikator pacjenta w rejestrze."),
        OpenApiParameter(
            "Content-Disposition", OpenApiTypes.STR, OpenApiParameter.HEADER, response=[200], required=True,
            description='Załącznik `attachment; filename="patient-{id}-fhir.json"`.',
        ),
    ],
    responses={
        (200, FHIR_JSON_MEDIA_TYPE): OpenApiResponse(
            response=FHIR_BUNDLE_SCHEMA,
            description="Plik JSON z Bundle typu `collection`.",
            examples=[OpenApiExample("Eksport w FHIR R4", value=FHIR_BUNDLE_EXAMPLE)],
        ),
        403: FORBIDDEN,
        404: NOT_FOUND,
    },
)


class RegistrySchemaView(SpectacularAPIView):
    renderer_classes = [JSONRenderer]

    @extend_schema(
        description="Pobierz opis OpenAPI w formacie JSON.",
        responses={200: OpenApiResponse(OpenApiTypes.OBJECT, description="Dokument OpenAPI 3."), 403: FORBIDDEN},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
