from django.apps import AppConfig


class DrmagdyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'drmagdy'

    def ready(self):
        super().ready()
        from . import extensions  # noqa: F401
