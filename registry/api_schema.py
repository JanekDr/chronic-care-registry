from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from drf_spectacular.views import SpectacularAPIView
from rest_framework import serializers
from rest_framework.renderers import JSONRenderer


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


class RegistrySchemaView(SpectacularAPIView):
    renderer_classes = [JSONRenderer]

    @extend_schema(
        description="Pobierz opis OpenAPI w formacie JSON.",
        responses={200: OpenApiResponse(OpenApiTypes.OBJECT, description="Dokument OpenAPI 3."), 403: FORBIDDEN},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
