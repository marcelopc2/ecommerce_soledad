from django.apps import AppConfig


class PanelConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'panel'

    def ready(self):
        # Importar el módulo es lo que conecta los @receiver del registro de
        # accesos. Sin esto los decoradores nunca se ejecutan y las señales de
        # login quedan sin escuchar, en silencio.
        from . import registro  # noqa: F401
