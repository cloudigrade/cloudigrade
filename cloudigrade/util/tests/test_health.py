"""Collection of tests for ``util.health`` module."""
# from unittest.mock import patch
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from util.health import CeleryHealthCheckBackend, SqsHealthCheckBackend


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
        connection.heartbeat_check.side_effect = ClientError({}, 'foo')
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


class SqsHealthCheckBackendTest(TestCase):
    """SQS health check test case."""

    @patch('util.health.aws.get_sqs_queue_url')
    def test_check_status_success(self, mock_get_sqs_queue_url):
        """Assert check_status records no error for normal use."""
        queue_name = settings.HOUNDIGRADE_RESULTS_QUEUE_NAME
        sqs_check_backend = SqsHealthCheckBackend()
        sqs_check_backend.check_status()
        mock_get_sqs_queue_url.assert_called_with(queue_name)
        self.assertEqual(len(sqs_check_backend.errors), 0)

    @patch('util.health.aws.get_sqs_queue_url')
    def test_check_status_boto3_fail(self, mock_get_sqs_queue_url):
        """Assert check_status records an error for a boto3 exception."""
        queue_name = settings.HOUNDIGRADE_RESULTS_QUEUE_NAME
        mock_get_sqs_queue_url.side_effect = ClientError({}, 'foo')
        sqs_check_backend = SqsHealthCheckBackend()
        sqs_check_backend.check_status()
        mock_get_sqs_queue_url.assert_called_with(queue_name)
        self.assertEqual(len(sqs_check_backend.errors), 1)

    @patch('util.health.aws.get_sqs_queue_url')
    def test_check_status_mystery_fail(self, mock_get_sqs_queue_url):
        """Assert check_status records an error for a mystery exception."""
        queue_name = settings.HOUNDIGRADE_RESULTS_QUEUE_NAME
        mock_get_sqs_queue_url.side_effect = Exception
        sqs_check_backend = SqsHealthCheckBackend()
        sqs_check_backend.check_status()
        mock_get_sqs_queue_url.assert_called_with(queue_name)
        self.assertEqual(len(sqs_check_backend.errors), 1)
