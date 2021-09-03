"""Collection of tests for the Sources Listener."""
import json
import signal
from unittest.mock import Mock, patch

import faker
from django.core.management import call_command
from django.test import TestCase

from util.management.commands.listen_to_sources import _listener_cleanup

_faker = faker.Faker()


def create_mock_message(event_type):
    """
    Create a mock sources kafka message.

    Args:
        event_type (str): the value for the message's event_type header

    Returns:
        Mock object populated to look and behave like a sources kafka message.
    """
    message = Mock()
    message.error.return_value = None
    message.value.return_value = json.dumps(
        {
            "id": _faker.pyint(),
            _faker.slug(): _faker.pyint(),
            _faker.slug(): _faker.pyint(),
        }
    ).encode()
    message.headers.return_value = [
        ("event_type", event_type.encode()),
        ("encoding", b"json"),
    ]
    return message


class SourcesListenerTest(TestCase):
    """Add App Configuration Test Case."""

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
    ):
        """Assert listener processes messages."""
        message_create = create_mock_message("ApplicationAuthentication.create")
        message_destroy = create_mock_message("ApplicationAuthentication.destroy")
        message_update = create_mock_message("Authentication.update")

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
        message_broken.headers = []

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
        with self.assertRaises(StopIteration), self.assertLogs(
            "util.management.commands.listen_to_sources", level="INFO"
        ) as log_context:
            call_command("listen_to_sources")

        mock_create_task.delay.assert_called_once()
        mock_delete_task.delay.assert_called_once()
        mock_update_task.delay.assert_called_once()
        mock_consumer.assert_called_once()
        mock_consumer_poll.assert_called()

        info_records = [r for r in log_context.records if r.levelname == "INFO"]
        warning_records = [r for r in log_context.records if r.levelname == "WARNING"]

        # Why are there 10 info messages? We currently log:
        # + 2 at listener start
        # + 2 for each of the 3 successful messages (6 total logs)
        # + 1 for the invalid message
        # + 1 at listener close
        self.assertEqual(10, len(info_records))
        # 1 warning from the broken message.
        self.assertEqual(1, len(warning_records))
        warning_records[0].message = "Consumer error: {'Borked.'}"

    @patch("util.management.commands.listen_to_sources.logger")
    def test_listener_cleanup(self, mock_logger):
        """Assert listener SIGTERM is logged."""
        _listener_cleanup(signal.SIGTERM, Mock())
        mock_logger.info.assert_called_once()
