from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import router, transaction

from .forms import DiagnosisForm, MeasurementForm, PatientForm, VisitForm
from .models import AuditLog, Diagnosis, ICD10Code, Measurement, Patient, Report, Visit
from .services import record_audit


class AuditedAdminMixin:
    """Admin obejmuje POST zmiany/usunięcia transakcją, razem z tym audytem.

    Brak akcji i list_editable: nie istnieje zbiorcza ścieżka omijająca formularz
    lub indywidualny audyt. Nie zapisujemy change_message w AuditLog.
    """

    actions = None

    def _audit(self, request, obj, action):
        record_audit(user=request.user, action=action,
                     object_type=obj._meta.object_name, object_id=obj.pk)

    def log_addition(self, request, obj, message):
        self._audit(request, obj, AuditLog.Action.CREATE)
        return super().log_addition(request, obj, message)

    def log_change(self, request, obj, message):
        self._audit(request, obj, AuditLog.Action.UPDATE)
        return super().log_change(request, obj, message)

    def log_deletions(self, request, queryset):
        for obj in queryset:
            self._audit(request, obj, AuditLog.Action.DELETE)
        return super().log_deletions(request, queryset)

    def delete_queryset(self, request, queryset):
        # Dodatkowa ochrona przed przyszłym dodaniem akcji zbiorczej.
        raise PermissionDenied("Usuwaj rekordy pojedynczo z potwierdzeniem.")


class ClinicalAdmin(AuditedAdminMixin, admin.ModelAdmin):
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Patient)
class PatientAdmin(ClinicalAdmin):
    form = PatientForm
    list_display = ["id", "last_name", "first_name", "birth_date", "gender"]
    search_fields = ["first_name", "last_name"]


@admin.register(ICD10Code)
class ICD10CodeAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ["code", "name"]
    search_fields = ["code", "name"]


@admin.register(Diagnosis)
class DiagnosisAdmin(ClinicalAdmin):
    form = DiagnosisForm
    list_display = ["patient", "icd10", "diagnosed_on"]
    list_select_related = ["patient", "icd10"]


@admin.register(Visit)
class VisitAdmin(ClinicalAdmin):
    form = VisitForm
    list_display = ["patient", "visit_date", "created_by"]
    list_select_related = ["patient", "created_by"]
    readonly_fields = ClinicalAdmin.readonly_fields + ["created_by"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Measurement)
class MeasurementAdmin(ClinicalAdmin):
    form = MeasurementForm
    list_display = ["visit", "kind", "value", "unit"]
    list_select_related = ["visit__patient"]


@admin.register(Report)
class ReportAdmin(ClinicalAdmin):
    # Zapisy raportów wymagają przeliczenia wyniku, dostarczanego w etapie 4.
    list_display = ["name", "date_from", "date_to", "icd10", "updated_at"]
    list_select_related = ["icd10"]
    readonly_fields = ["name", "date_from", "date_to", "icd10", "result", "created_by", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


admin.site.unregister(get_user_model())
admin.site.unregister(Group)


@admin.register(get_user_model())
class RegistryUserAdmin(AuditedAdminMixin, UserAdmin):
    def has_delete_permission(self, request, obj=None):
        return False  # Konta autorów dezaktywujemy, zachowując ich tożsamość.

    def user_change_password(self, request, id, form_url=""):
        # Standardowy osobny widok hasła UserAdmin nie otwiera transakcji.
        with transaction.atomic(using=router.db_for_write(self.model)):
            return super().user_change_password(request, id, form_url)


@admin.register(Group)
class RegistryGroupAdmin(AuditedAdminMixin, GroupAdmin):
    pass


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "action", "object_type", "object_id"]
    list_filter = ["action", "object_type"]
    search_fields = ["user__username", "object_type", "object_id"]
    readonly_fields = ["created_at", "user", "action", "object_type", "object_id"]
    list_select_related = ["user"]
    actions = None

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
