from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "booking"

    def ready(self):
        from . import signals  # noqa: F401