from django.apps import AppConfig


class InternalConfig(AppConfig):
    name = "internal"

    def ready(self):
        from internal.prometheus import initialize_cached_metrics

        initialize_cached_metrics()
