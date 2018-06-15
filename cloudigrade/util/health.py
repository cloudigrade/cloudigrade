"""Collection of custom backends to plug into ``django-health-check``."""
import logging

from botocore.exceptions import ClientError
from django.conf import settings
from django.utils.translation import gettext as _
from health_check.backends import BaseHealthCheckBackend

from account.util import _get_sqs_queue_url

logger = logging.getLogger(__name__)


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
        except ClientError as e:
            logger.exception(e)
            self.add_error(_('Celery heartbeat failed due to boto3 error.'))
        except Exception as e:
            logger.exception(e)
            self.add_error(_('Celery heartbeat failed due to unknown error.'))


class SqsHealthCheckBackend(BaseHealthCheckBackend):
    """SQS health check."""

    def check_status(self):
        """Check SQS health by using looking up a known queue's URL'."""
        try:
            queue_name = settings.HOUNDIGRADE_RESULTS_QUEUE_NAME
            _get_sqs_queue_url(queue_name)
        except ClientError as e:
            logger.exception(e)
            self.add_error(_('SQS check failed due to boto3 error.'))
        except Exception as e:
            logger.exception(e)
            self.add_error(_('SQS check failed due to unknown error.'))
