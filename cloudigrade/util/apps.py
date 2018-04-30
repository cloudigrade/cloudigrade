from django.apps import AppConfig

from health_check.plugins import plugin_dir


class UtilConfig(AppConfig):
    name = 'util'

    def ready(self):
        from .health import RabbitMQCheckBackend
        plugin_dir.register(RabbitMQCheckBackend)
