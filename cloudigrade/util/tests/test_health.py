"""Collection of tests for ``util.health`` module."""
from unittest.mock import patch

from django.test import TestCase

from util.health import MessageBrokerBackend


class UtilHealthTest(TestCase):
    """Utility health check function test case."""

    @patch('util.health.kombu')
    def test_check_broker_working(self, mock_kombu):
        """Assert good run_check health when connection is okay."""
        mock_conn = mock_kombu.Connection.return_value
        mock_conn.connected.return_value = True

        broker_check = MessageBrokerBackend()
        broker_check.run_check()

        self.assertFalse(broker_check.errors)

    @patch('util.health.kombu')
    def test_check_kombu_failing(self, mock_kombu):
        """Assert bad run_check health when no kombu connection."""
        mock_conn = mock_kombu.Connection.return_value
        mock_conn.connected = False

        broker_check = MessageBrokerBackend()
        broker_check.run_check()

        self.assertTrue(broker_check.errors)
        self.assertIn('Failed to connect.', broker_check.pretty_status())

    @patch('util.health.kombu')
    def test_check_conn_failing(self, mock_kombu):
        """Assert bad run_check health when kombu connection has error."""
        mock_conn = mock_kombu.Connection.return_value
        mock_conn.connect.side_effect = ConnectionError()

        broker_check = MessageBrokerBackend()
        broker_check.run_check()

        self.assertTrue(mock_conn.connect.called)
        self.assertEquals(mock_conn.connect.call_count, 1)
        self.assertTrue(broker_check.errors)
        self.assertGreater(len(broker_check.pretty_status()), 0)
