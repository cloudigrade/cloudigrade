"""Collection of tests for the Sources Listener."""
import signal
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from util.management.commands.listen_to_sources import _listener_cleanup


class SourcesListenerTest(TestCase):
    """Add App Configuration Test Case."""

    @patch("util.management.commands.listen_to_sources.logger")
    @patch("util.management.commands.listen_to_sources.Consumer")
    @patch("api.tasks.sources.update_from_source_kafka_message")
    @patch("api.tasks.sources.delete_from_sources_kafka_message")
    @patch("api.tasks.sources.create_from_sources_kafka_message")
    def test_listen(
        self,
        mock_create_task,
        mock_delete_task,
        mock_update_task,
        mock_consumer,
        mock_logger,
    ):
        """Assert listener processes messages."""
        message1 = Mock()
        message2 = Mock()
        message3 = Mock()
        message4 = Mock()
        message5 = Mock()

        message1.error.return_value = None
        message2.error.return_value = None
        message3.error.return_value = None
        message4.error.return_value = None
        message5.error.return_value = {"Borked."}

        message1.value.return_value = b'{"application_id": 42, "authentication_id": 7}'
        message1.headers.return_value = [
            ("event_type", b"ApplicationAuthentication.create"),
            ("encoding", b"json"),
        ]

        message2.value.return_value = b'{"value": "test message 2"}'
        message2.headers.return_value = [
            ("event_type", b"ApplicationAuthentication.destroy"),
            ("encoding", b"json"),
        ]

        message3.value.return_value = b'{"value": "test message 3"}'
        message3.headers.return_value = [
            ("event_type", b"Authentication.update"),
            ("encoding", b"json"),
        ]

        message4.value.return_value = b'{"authtype": "INVALID"}'
        message4.headers.return_value = [
            ("event_type", b"Authentication.create"),
            ("encoding", b"json"),
        ]

        # Make sure to send this message last,
        # since it raises the TypeError that terminates the listener
        message5.value = "bad message"
        message5.headers = [Mock(), Mock()]

        mock_message_bundle_items = [message1, message2, message3, message4, message5]

        mock_consumer_poll = mock_consumer.return_value.poll
        mock_consumer_poll.side_effect = mock_message_bundle_items

        # Let the script hit the end of the message list
        with self.assertRaises(StopIteration):
            call_command("listen_to_sources")

        mock_create_task.delay.assert_called_once()
        mock_delete_task.delay.assert_called_once()
        mock_update_task.delay.assert_called_once()
        mock_consumer.assert_called_once()
        mock_consumer_poll.assert_called()
        self.assertEqual(10, mock_logger.info.call_count)
        self.assertEqual(1, mock_logger.warning.call_count)

    @patch("util.management.commands.listen_to_sources.logger")
    def test_listener_cleanup(self, mock_logger):
        """Assert listener SIGTERM is logged."""
        _listener_cleanup(signal.SIGTERM, Mock())
        mock_logger.info.assert_called_once()
