"""Collection of tests for the Sources Listener."""
import signal
from unittest.mock import Mock, patch

from django.test import TestCase

from sources_listener import listen, listener_cleanup


class SourcesListenerTest(TestCase):
    """Add App Configuration Test Case."""

    @patch('sources_listener.logger')
    @patch('sources_listener.KafkaConsumer')
    def test_listen(self, mock_consumer, mock_logger):
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
            listen()

        mock_consumer.assert_called_once()
        mock_consumer_poll.assert_called_once()
        self.assertEqual(2, mock_logger.info.call_count)

    @patch('sources_listener.logger')
    def test_listener_cleanup(self, mock_logger):
        """Assert listener SIGTERM is logged."""
        listener_cleanup(signal.SIGTERM, Mock())
        mock_logger.info.assert_called_once()
