from django.apps import AppConfig


class PoliciesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "policies"
    verbose_name = "Policy knowledge base"

    def ready(self):
        from . import signals  # noqa: F401
