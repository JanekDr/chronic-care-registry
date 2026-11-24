from rest_framework import serializers


class ISODateField(serializers.DateField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if isinstance(data, str) and data != value.isoformat():
            self.fail("invalid", format="YYYY-MM-DD")
        return value


class PatientFilters(serializers.Serializer):
    search = serializers.CharField(
        required=False, allow_blank=True,
        help_text="Fragment imienia lub nazwiska. Każdy człon musi pasować do imienia albo nazwiska.",
    )
    icd10 = serializers.CharField(
        required=False, allow_blank=True,
        help_text="Dokładny kod rozpoznania pacjenta, np. I10.",
    )


class DiagnosisFilters(serializers.Serializer):
    patient = serializers.IntegerField(required=False, min_value=1, help_text="Identyfikator pacjenta.")


class VisitFilters(DiagnosisFilters):
    date_from = ISODateField(required=False, help_text="Pierwszy uwzględniony dzień wizyt w formacie YYYY-MM-DD.")
    date_to = ISODateField(required=False, help_text="Ostatni uwzględniony dzień wizyt w formacie YYYY-MM-DD.")

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from is not None and date_to is not None and date_from > date_to:
            raise serializers.ValidationError({"date_to": "Koniec okresu nie może poprzedzać początku."})
        return attrs


class MeasurementFilters(serializers.Serializer):
    visit = serializers.IntegerField(required=False, min_value=1, help_text="Identyfikator wizyty.")


class ICD10Filters(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, help_text="Fragment kodu lub nazwy w słowniku ICD-10.")
