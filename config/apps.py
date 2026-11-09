from django.contrib.admin.apps import AdminConfig


class RegistryAdminConfig(AdminConfig):
    default_site = "config.admin.RegistryAdminSite"

