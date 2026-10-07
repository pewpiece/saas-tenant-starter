from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self):
        # Registers the OpenAPI extensions before any schema is generated.
        from apps.core import schema  # noqa: F401
