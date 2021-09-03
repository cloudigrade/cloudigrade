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
    @patch("api.tasks.sources.unpause_from_sources_kafka_message")
    @patch("api.tasks.sources.pause_from_sources_kafka_message")
    @patch("api.tasks.sources.update_from_source_kafka_message")
    @patch("api.tasks.sources.delete_from_sources_kafka_message")
    @patch("api.tasks.sources.create_from_sources_kafka_message")
    def test_listen(
        self,
        mock_create_task,
        mock_delete_task,
        mock_update_task,
        mock_pause_task,
        mock_unpause_task,
        mock_consumer,
    ):
        """Assert listener processes messages."""
        message_create = create_mock_message("ApplicationAuthentication.create")
        message_destroy = create_mock_message("ApplicationAuthentication.destroy")
        message_update = create_mock_message("Authentication.update")
        message_pause = create_mock_message("Application.pause")
        message_unpause = create_mock_message("Application.unpause")

        message_invalid_json = create_mock_message("Authentication.update")
        message_invalid_json.value.return_value = b"this is not json"

        message_invalid_encoding = create_mock_message("Authentication.update")
        message_invalid_encoding.value.return_value = b'{"not":"utf-8 safe\x8a"}'

        # Make sure to send this message last,
        # since it raises the TypeError that terminates the listener
        message_with_error = Mock()
        message_with_error.error.return_value = {"Borked."}
        message_with_error.value = "bad message"
        message_with_error.headers = []

        mock_message_bundle_items = [
            message_create,
            message_destroy,
            message_update,
            message_pause,
            message_unpause,
            message_invalid_json,
            message_invalid_encoding,
            message_with_error,
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
        mock_pause_task.delay.assert_called_once()
        mock_unpause_task.delay.assert_called_once()
        mock_consumer.assert_called_once()
        mock_consumer_poll.assert_called()

        info_records = [r for r in log_context.records if r.levelname == "INFO"]
        warning_records = [r for r in log_context.records if r.levelname == "WARNING"]
        error_records = [r for r in log_context.records if r.levelname == "ERROR"]

        # Why are there 13 info messages? We currently log:
        # + 2 at listener start
        # + 2 for each of the 5 successful messages (10 total logs)
        # + 1 at listener close
        self.assertEqual(13, len(info_records))

        # 1 error for each invalid message (2 total logs)
        self.assertEqual(2, len(error_records))
        self.assertIn("Expecting value", error_records[0].message)
        self.assertIn("invalid start byte", error_records[1].message)

        # 2 warnings for each of the 2 invalid messages (4 total logs)
        # 1 warning from the message that has an error.
        self.assertEqual(5, len(warning_records))
        warning_records[4].message = "Consumer error: {'Borked.'}"

    @patch("util.management.commands.listen_to_sources.logger")
    def test_listener_cleanup(self, mock_logger):
        """Assert listener SIGTERM is logged."""
        _listener_cleanup(signal.SIGTERM, Mock())
        mock_logger.info.assert_called_once()
