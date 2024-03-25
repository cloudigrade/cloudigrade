"""Collection of custom backends to plug into ``django-health-check``."""

import logging

from botocore.exceptions import ClientError
from django.utils.translation import gettext as _
from health_check.backends import BaseHealthCheckBackend

logger = logging.getLogger(__name__)


# TODO FIXME: These health checks were causing (or highlighting)
# a memory leak issue, when the time comes we need to come back
# and refactor or replace these health checks.
class CeleryHealthCheckBackend(BaseHealthCheckBackend):
    """Celery connection health check."""

    def _get_app(self):
        """Get the current Celery app."""
        from config.celery import app

        return app

    def check_status(self):
        """Use Celery to check a connection heartbeat."""
        try:
            app = self._get_app()
            connection = app.connection()
            connection.heartbeat_check()
            connection.release()
        except ClientError as e:
            logger.exception(e)
            self.add_error(_("Celery heartbeat failed due to boto3 error."))
        except Exception as e:
            logger.exception(e)
            self.add_error(_("Celery heartbeat failed due to unknown error."))
