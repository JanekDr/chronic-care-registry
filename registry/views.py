from django.contrib import messages
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import PatientDiagnosisForm, PatientForm, PatientVisitForm, VisitMeasurementForm, ReportForm
from .models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Visit, Report
from .permissions import RegistryAccessMixin
from .services import (
    PATIENT_DELETE_BLOCKED,
    VISIT_DELETE_BLOCKED,
    filter_patients,
    record_audit,
    save_report,
)


class ReadAuditMixin:
    """Audyt poprawnego GET bez parametrów żądania i treści odpowiedzi."""

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        obj = getattr(self, "object", None)
        parent = getattr(self, "visit", None) or getattr(self, "patient", None)
        if obj is not None or parent is not None:
            target = obj if obj is not None else parent
            record_audit(user=request.user, action=AuditLog.Action.READ_DETAIL,
                         object_type=target._meta.object_name, object_id=target.pk)
        elif isinstance(self, ListView):
            record_audit(user=request.user, action=AuditLog.Action.READ_LIST,
                         object_type=self.model._meta.object_name)
        for model in getattr(self, "read_lists", ()):
            record_audit(user=request.user, action=AuditLog.Action.READ_LIST,
                         object_type=model._meta.object_name)
        return response


class AuditedSaveMixin:
    template_name = "registry/object_form.html"
    http_method_names = ["get", "post", "head", "options"]

    def form_valid(self, form):
        action = AuditLog.Action.UPDATE if form.instance.pk else AuditLog.Action.CREATE
        with transaction.atomic():
            if isinstance(form.instance, Visit) and not form.instance.pk:
                form.instance.created_by = self.request.user
            response = super().form_valid(form)
            record_audit(user=self.request.user, action=action,
                         object_type=self.object._meta.object_name, object_id=self.object.pk)
        messages.success(self.request, "Zapisano dane.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title=self.page_title, cancel_url=self.get_cancel_url())
        return context

    def get_cancel_url(self):
        return self.get_success_url()


class AuditedDeleteMixin:
    template_name = "registry/confirm_delete.html"
    http_method_names = ["get", "post", "head", "options"]
    delete_blocked_message = "Rekord ma powiązane dane."

    def form_valid(self, form):
        object_id = self.object.pk
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                record_audit(user=self.request.user, action=AuditLog.Action.DELETE,
                             object_type=self.model._meta.object_name, object_id=object_id)
        except ProtectedError:
            form.add_error(None, self.delete_blocked_message)
            return self.form_invalid(form)
        messages.success(self.request, "Usunięto rekord.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title=self.page_title, cancel_url=self.get_cancel_url())
        return context


class PatientScopeMixin:
    """Adres ustala pacjenta; zagnieżdżony obiekt musi do niego należeć."""

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(patient=self.patient)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if isinstance(self, (CreateView, UpdateView)):
            kwargs["parent"] = self.patient
        return kwargs

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "patient": self.patient}

    def get_success_url(self):
        return reverse("registry:patient-detail", args=[self.patient.pk])

    def get_cancel_url(self):
        return self.get_success_url()


class VisitScopeMixin:
    def dispatch(self, request, *args, **kwargs):
        self.visit = get_object_or_404(Visit.objects.select_related("patient"), pk=kwargs["visit_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return super().get_queryset().filter(visit=self.visit)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if isinstance(self, (CreateView, UpdateView)):
            kwargs["parent"] = self.visit
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(visit=self.visit, patient=self.visit.patient)
        if isinstance(self, (CreateView, UpdateView)):
            context["measurement_units"] = {kind: item["unit"] for kind, item in Measurement.DEFINITIONS.items()}
            kind = context["form"]["kind"].value()
            context["selected_unit"] = context["measurement_units"].get(kind, "Wybierz rodzaj")
        return context

    def get_success_url(self):
        return reverse("registry:visit-detail", args=[self.visit.patient_id, self.visit.pk])

    def get_cancel_url(self):
        return self.get_success_url()


class PatientListView(RegistryAccessMixin, ReadAuditMixin, ListView):
    model = Patient
    template_name = "registry/patient_list.html"
    paginate_by = 20
    read_lists = (ICD10Code,)

    def get_queryset(self):
        return filter_patients(
            super().get_queryset(),
            search=self.request.GET.get("search", ""),
            icd10=self.request.GET.get("icd10", ""),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context.update(search=self.request.GET.get("search", ""),
                       selected_icd10=self.request.GET.get("icd10", "").strip(),
                       icd10_codes=ICD10Code.objects.order_by("code", "id"),
                       pagination_query=params.urlencode())
        return context


class PatientDetailView(RegistryAccessMixin, ReadAuditMixin, DetailView):
    model = Patient
    template_name = "registry/patient_detail.html"
    read_lists = (Diagnosis, Visit)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(diagnoses=self.object.diagnoses.select_related("icd10"),
                       visits=self.object.visits.select_related("created_by"))
        return context


class PatientSaveMixin(AuditedSaveMixin):
    model = Patient
    form_class = PatientForm

    def get_success_url(self):
        return reverse("registry:patient-detail", args=[self.object.pk])

    def get_cancel_url(self):
        return self.get_success_url() if self.object else reverse("registry:patient-list")


class PatientCreateView(RegistryAccessMixin, ReadAuditMixin, PatientSaveMixin, CreateView):
    page_title = "Dodaj pacjenta"


class PatientUpdateView(RegistryAccessMixin, ReadAuditMixin, PatientSaveMixin, UpdateView):
    page_title = "Edytuj pacjenta"


class PatientDeleteView(RegistryAccessMixin, ReadAuditMixin, AuditedDeleteMixin, DeleteView):
    model = Patient
    page_title = "Usuń pacjenta"
    delete_blocked_message = PATIENT_DELETE_BLOCKED

    def get_success_url(self):
        return reverse("registry:patient-list")

    def get_cancel_url(self):
        return reverse("registry:patient-detail", args=[self.object.pk])


class DiagnosisBaseMixin(PatientScopeMixin):
    model = Diagnosis

    def get_queryset(self):
        return super().get_queryset().select_related("icd10")


class DiagnosisDetailView(RegistryAccessMixin, ReadAuditMixin, DiagnosisBaseMixin, DetailView):
    template_name = "registry/diagnosis_detail.html"


class DiagnosisCreateView(RegistryAccessMixin, ReadAuditMixin, DiagnosisBaseMixin, AuditedSaveMixin, CreateView):
    form_class = PatientDiagnosisForm
    page_title = "Dodaj rozpoznanie"
    read_lists = (ICD10Code,)


class DiagnosisUpdateView(RegistryAccessMixin, ReadAuditMixin, DiagnosisBaseMixin, AuditedSaveMixin, UpdateView):
    form_class = PatientDiagnosisForm
    page_title = "Edytuj rozpoznanie"
    read_lists = (ICD10Code,)


class DiagnosisDeleteView(RegistryAccessMixin, ReadAuditMixin, DiagnosisBaseMixin, AuditedDeleteMixin, DeleteView):
    page_title = "Usuń rozpoznanie"


class VisitBaseMixin(PatientScopeMixin):
    model = Visit

    def get_queryset(self):
        return super().get_queryset().select_related("created_by")


class VisitDetailView(RegistryAccessMixin, ReadAuditMixin, VisitBaseMixin, DetailView):
    template_name = "registry/visit_detail.html"
    read_lists = (Measurement,)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "measurements": self.object.measurements.all()}


class VisitSaveMixin(AuditedSaveMixin):
    form_class = PatientVisitForm

    def get_success_url(self):
        if self.object:
            return reverse("registry:visit-detail", args=[self.patient.pk, self.object.pk])
        return super().get_success_url()


class VisitCreateView(RegistryAccessMixin, ReadAuditMixin, VisitSaveMixin, VisitBaseMixin, CreateView):
    page_title = "Dodaj wizytę"


class VisitUpdateView(RegistryAccessMixin, ReadAuditMixin, VisitSaveMixin, VisitBaseMixin, UpdateView):
    page_title = "Edytuj wizytę"


class VisitDeleteView(RegistryAccessMixin, ReadAuditMixin, VisitBaseMixin, AuditedDeleteMixin, DeleteView):
    page_title = "Usuń wizytę"
    delete_blocked_message = VISIT_DELETE_BLOCKED


class MeasurementBaseMixin(VisitScopeMixin):
    model = Measurement


class MeasurementDetailView(RegistryAccessMixin, ReadAuditMixin, MeasurementBaseMixin, DetailView):
    template_name = "registry/measurement_detail.html"


class MeasurementCreateView(RegistryAccessMixin, ReadAuditMixin, MeasurementBaseMixin, AuditedSaveMixin, CreateView):
    form_class = VisitMeasurementForm
    page_title = "Dodaj pomiar"


class MeasurementUpdateView(RegistryAccessMixin, ReadAuditMixin, MeasurementBaseMixin, AuditedSaveMixin, UpdateView):
    form_class = VisitMeasurementForm
    page_title = "Edytuj pomiar"


class MeasurementDeleteView(RegistryAccessMixin, ReadAuditMixin, MeasurementBaseMixin, AuditedDeleteMixin, DeleteView):
    page_title = "Usuń pomiar"


class ReportListView(RegistryAccessMixin, ReadAuditMixin, ListView):
    model = Report
    queryset = Report.objects.select_related("icd10", "created_by").order_by("id")
    template_name = "registry/report_list.html"
    paginate_by = 20


class ReportDetailView(RegistryAccessMixin, ReadAuditMixin, DetailView):
    model = Report
    template_name = "registry/report_detail.html"
    queryset = Report.objects.select_related("icd10", "created_by")


class ReportSaveMixin(AuditedSaveMixin):
    model = Report
    form_class = ReportForm
    read_lists = (ICD10Code,)

    def form_valid(self, form):
        self.object = save_report(report=form.instance, user=self.request.user)
        messages.success(self.request, "Zapisano i przeliczono raport.")
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse("registry:report-detail", args=[self.object.pk])

    def get_cancel_url(self):
        return self.get_success_url() if self.object else reverse("registry:report-list")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "submit_label": "Zapisz i przelicz"}


class ReportCreateView(RegistryAccessMixin, ReadAuditMixin, ReportSaveMixin, CreateView):
    page_title = "Dodaj raport"


class ReportUpdateView(RegistryAccessMixin, ReadAuditMixin, ReportSaveMixin, UpdateView):
    page_title = "Edytuj raport"


class ReportDeleteView(RegistryAccessMixin, ReadAuditMixin, AuditedDeleteMixin, DeleteView):
    model = Report
    page_title = "Usuń raport"

    def get_success_url(self):
        return reverse("registry:report-list")

    def get_cancel_url(self):
        return reverse("registry:report-detail", args=[self.object.pk])
