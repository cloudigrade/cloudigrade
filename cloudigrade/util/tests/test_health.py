"""Collection of tests for ``util.health`` module."""
from unittest.mock import patch

from django.test import TestCase

from util.health import RabbitMQCheckBackend


class UtilHealthTest(TestCase):
    """Utility health check function test case."""

    @patch('util.health.kombu')
    def test_check_rabbit_working(self, mock_kombu):
        """Test with passing conditions."""
        mock_conn = mock_kombu.Connection.return_value
        mock_conn.connected.return_value = True

        rabbitmq_check = RabbitMQCheckBackend()
        rabbitmq_check.run_check()

        self.assertFalse(rabbitmq_check.errors)

    @patch('util.health.kombu')
    def test_check_rabbit_kombu_failing(self, mock_kombu):
        """Test with kombu issue."""
        mock_conn = mock_kombu.Connection.return_value
        mock_conn.connected = False

        rabbitmq_check = RabbitMQCheckBackend()
        rabbitmq_check.run_check()

        self.assertTrue(rabbitmq_check.errors)
        self.assertIn('Failed to connect.', rabbitmq_check.pretty_status())

    @patch('util.health.kombu')
    def test_check_rabbit_conn_failing(self, mock_kombu):
        """Test with amqp issue."""
        mock_conn = mock_kombu.Connection.return_value
        mock_conn.connect.side_effect = ConnectionError()

        rabbitmq_check = RabbitMQCheckBackend()
        rabbitmq_check.run_check()

        self.assertTrue(mock_conn.connect.called)
        self.assertEquals(mock_conn.connect.call_count, 1)
        self.assertTrue(rabbitmq_check.errors)
        self.assertIn('Failed to connect to RabbitMQ',
                      rabbitmq_check.pretty_status())
