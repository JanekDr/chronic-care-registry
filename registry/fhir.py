from uuid import NAMESPACE_URL, uuid5

from django.utils import timezone

from .models import Measurement


FHIR_JSON_MEDIA_TYPE = "application/fhir+json"
TERMINOLOGY_SYSTEM = "http://terminology.hl7.org/CodeSystem"
BODY_WEIGHT_PROFILE = "http://hl7.org/fhir/StructureDefinition/bodyweight"


def _entry(resource_type, pk, fields):
    resource_id = str(uuid5(NAMESPACE_URL, f"urn:psim:{resource_type}:{pk}"))
    return {
        "fullUrl": f"urn:uuid:{resource_id}",
        "resource": {"resourceType": resource_type, "id": resource_id, **fields},
    }


def _concept(system, code, *, display=None):
    coding = {"system": system, "code": code}
    if display is not None:
        coding["display"] = display
    return {"coding": [coding]}


def _patient_entry(patient):
    return _entry("Patient", patient.pk, {
        "identifier": [{"system": "urn:psim:patient-id", "value": str(patient.pk)}],
        "name": [{"given": [patient.first_name], "family": patient.last_name}],
        "birthDate": patient.birth_date.isoformat(),
        "gender": patient.gender,
    })


def _condition_entry(diagnosis, subject):
    return _entry("Condition", diagnosis.pk, {
        "subject": subject,
        "code": _concept("http://hl7.org/fhir/sid/icd-10", diagnosis.icd10.code),
        "clinicalStatus": _concept(f"{TERMINOLOGY_SYSTEM}/condition-clinical", "active"),
        "verificationStatus": _concept(f"{TERMINOLOGY_SYSTEM}/condition-ver-status", "confirmed"),
        "recordedDate": diagnosis.created_at.isoformat(),
    })


def _encounter_entry(visit, subject):
    return _entry("Encounter", visit.pk, {
        "subject": subject,
        "status": "finished",
        "class": {"system": f"{TERMINOLOGY_SYSTEM}/v3-ActCode", "code": "AMB"},
        "period": {"start": visit.visit_date.isoformat()},
    })


def _observation_entry(measurement, *, subject, encounter, visit_date):
    definition = Measurement.DEFINITIONS[measurement.kind]
    unit = definition["unit"]
    fields = {
        "status": "final",
        "subject": subject,
        "encounter": encounter,
        "effectiveDateTime": visit_date.isoformat(),
        "code": _concept("http://loinc.org", definition["loinc"], display=definition["display"]),
        "category": [_concept(f"{TERMINOLOGY_SYSTEM}/observation-category", definition["category"])],
        "valueQuantity": {"value": measurement.value, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit},
    }
    if measurement.kind == Measurement.Kind.BODY_WEIGHT:
        fields["meta"] = {"profile": [BODY_WEIGHT_PROFILE]}
    return _entry("Observation", measurement.pk, fields)


def build_patient_bundle(patient):
    patient_entry = _patient_entry(patient)
    subject = {"reference": patient_entry["fullUrl"]}
    entries = [patient_entry]
    entries.extend(
        _condition_entry(diagnosis, subject)
        for diagnosis in patient.diagnoses.select_related("icd10")
    )
    for visit in patient.visits.prefetch_related("measurements"):
        encounter_entry = _encounter_entry(visit, subject)
        entries.append(encounter_entry)
        encounter = {"reference": encounter_entry["fullUrl"]}
        entries.extend(
            _observation_entry(measurement, subject=subject, encounter=encounter, visit_date=visit.visit_date)
            for measurement in visit.measurements.all()
        )
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": timezone.now().isoformat(),
        "entry": entries,
    }
