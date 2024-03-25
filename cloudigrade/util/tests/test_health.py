"""Collection of tests for ``util.health`` module."""

from unittest.mock import Mock

from botocore.exceptions import ClientError
from django.test import TestCase

from util.health import CeleryHealthCheckBackend


class CeleryHealthCheckBackendTest(TestCase):
    """Celery health check test case."""

    def do_mock_celery_app(self, celery_check_backend):
        """Set up test with a mock Celery app and return that mock."""
        mock_app = Mock()
        celery_check_backend._get_app = lambda: mock_app
        return mock_app

    def test_check_status_success(self):
        """Assert check_status records no error for normal use."""
        celery_check_backend = CeleryHealthCheckBackend()
        celery_app = self.do_mock_celery_app(celery_check_backend)
        celery_check_backend.check_status()
        connection = celery_app.connection.return_value
        connection.heartbeat_check.assert_called()
        self.assertEqual(len(celery_check_backend.errors), 0)

    def test_check_status_boto3_fail(self):
        """Assert check_status records an error for a boto3 exception."""
        celery_check_backend = CeleryHealthCheckBackend()
        celery_app = self.do_mock_celery_app(celery_check_backend)
        connection = celery_app.connection.return_value
        connection.heartbeat_check.side_effect = ClientError({}, "foo")
        celery_check_backend.check_status()
        self.assertEqual(len(celery_check_backend.errors), 1)

    def test_check_status_mystery_fail(self):
        """Assert check_status records an error for a mystery exception."""
        celery_check_backend = CeleryHealthCheckBackend()
        celery_app = self.do_mock_celery_app(celery_check_backend)
        connection = celery_app.connection.return_value
        connection.heartbeat_check.side_effect = Exception
        celery_check_backend.check_status()
        self.assertEqual(len(celery_check_backend.errors), 1)
