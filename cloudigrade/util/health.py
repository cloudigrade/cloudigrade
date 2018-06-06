"""Collection of custom backends to plug into ``django-health-check``."""
import kombu
from django.conf import settings
from django.utils.translation import gettext as _
from health_check.backends import BaseHealthCheckBackend


class MessageBrokerBackend(BaseHealthCheckBackend):
    """Celery/Kombu message broker health check."""

    def check_status(self):
        """Test a connection to the Celery/Kombu message broker."""
        conn = kombu.Connection(settings.CELERY_BROKER_URL)
        try:
            conn.connect()
            if conn.connected:
                conn.release()
            else:
                self.add_error(_('Failed to connect.'))
        except ConnectionError:
            self.add_error(_('Failed to connect to Celery/Kombu broker.'))
