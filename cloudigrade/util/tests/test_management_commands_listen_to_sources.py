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
        message_create = Mock()
        message_create.error.return_value = None
        message_create.value.return_value = (
            b'{"application_id": 42, "authentication_id": 7}'
        )
        message_create.headers.return_value = [
            ("event_type", b"ApplicationAuthentication.create"),
            ("encoding", b"json"),
        ]

        message_destroy = Mock()
        message_destroy.error.return_value = None
        message_destroy.value.return_value = b'{"value": "test message 2"}'
        message_destroy.headers.return_value = [
            ("event_type", b"ApplicationAuthentication.destroy"),
            ("encoding", b"json"),
        ]

        message_update = Mock()
        message_update.error.return_value = None
        message_update.value.return_value = b'{"value": "test message 3"}'
        message_update.headers.return_value = [
            ("event_type", b"Authentication.update"),
            ("encoding", b"json"),
        ]

        message_invalid = Mock()
        message_invalid.error.return_value = None
        message_invalid.value.return_value = b'{"authtype": "INVALID"}'
        message_invalid.headers.return_value = [
            ("event_type", b"Authentication.create"),
            ("encoding", b"json"),
        ]

        # Make sure to send this message last,
        # since it raises the TypeError that terminates the listener
        message_broken = Mock()
        message_broken.error.return_value = {"Borked."}
        message_broken.value = "bad message"
        message_broken.headers = [Mock(), Mock()]

        mock_message_bundle_items = [
            message_create,
            message_destroy,
            message_update,
            message_invalid,
            message_broken,
        ]

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
