"""Collection of custom backends to plug into ``django-health-check``."""
import kombu
from django.conf import settings
from health_check.backends import BaseHealthCheckBackend


class RabbitMQCheckBackend(BaseHealthCheckBackend):
    """RabbitMQ Health Check."""

    def check_status(self):
        """Test RabbitMQ health check."""
        conn = kombu.Connection(settings.RABBITMQ_URL)
        try:
            conn.connect()
            if conn.connected:
                conn.release()
            else:
                self.add_error('Failed to connect.')
        except ConnectionError:
            self.add_error('Failed to connect to RabbitMQ')
