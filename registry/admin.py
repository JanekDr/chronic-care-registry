from django.contrib import admin

from .models import AuditLog


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
