"""Collection of tests for the Sources Listener."""
import signal
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from util.management.commands.listen_to_sources import Command


class SourcesListenerTest(TestCase):
    """Add App Configuration Test Case."""

    @patch('util.management.commands.listen_to_sources.PIDLockFile')
    @patch('util.management.commands.listen_to_sources.logger')
    @patch('util.management.commands.listen_to_sources.KafkaConsumer')
    @patch('api.tasks.delete_from_sources_kafka_message')
    @patch('api.tasks.create_from_sources_kafka_message')
    @patch('daemon.DaemonContext')
    def test_listen(
        self,
        mock_daemon_context,
        mock_create_task,
        mock_delete_task,
        mock_consumer,
        mock_logger,
        mock_pid,
    ):
        """Assert listener processes messages."""
        message1 = Mock()
        message2 = Mock()
        message3 = Mock()

        message1.value = 'test message 1'
        message1.headers = [('event_type', b'Authentication.create'),
                            ('encoding', b'json')]

        message2.value = 'test message 2'
        message2.headers = [('event_type', b'Authentication.destroy'),
                            ('encoding', b'json')]

        message3.value = 'bad message'
        message3.headers = [Mock(), Mock()]

        mock_message_bundle_items = {
            'Partition 1': [message1, message2, message3]}

        mock_consumer_poll = mock_consumer.return_value.poll
        mock_consumer_poll.return_value = mock_message_bundle_items

        with self.assertRaises(TypeError):
            call_command('listen_to_sources')

        mock_create_task.delay.assert_called_once()
        mock_delete_task.delay.assert_called_once()
        mock_consumer.assert_called_once()
        mock_consumer_poll.assert_called_once()
        self.assertEqual(2, mock_logger.info.call_count)

    @patch('util.management.commands.listen_to_sources.logger')
    def test_listener_cleanup(self, mock_logger):
        """Assert listener SIGTERM is logged."""
        Command.listener_cleanup(Mock(), signal.SIGTERM, Mock())
        mock_logger.info.assert_called_once()
