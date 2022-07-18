from django.apps import AppConfig

from internal.prometheus import CachedMetricsRegistry


class InternalConfig(AppConfig):
    name = "internal"
    _cached_metrics_registry = None

    def ready(self):
        if not self._cached_metrics_registry:
            self._cached_metrics_registry = CachedMetricsRegistry()
            self._cached_metrics_registry.initialize()
