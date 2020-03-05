"""Collection of tests for the Sources Listener."""
import random
import signal
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from lockfile import AlreadyLocked

from util.management.commands.listen_to_sources import Command


class SourcesListenerTest(TestCase):
    """Add App Configuration Test Case."""

    @patch("util.management.commands.listen_to_sources.PIDLockFile")
    @patch("util.management.commands.listen_to_sources.logger")
    @patch("util.management.commands.listen_to_sources.KafkaConsumer")
    @patch("api.tasks.update_from_source_kafka_message")
    @patch("api.tasks.delete_from_sources_kafka_message")
    @patch("api.tasks.create_from_sources_kafka_message")
    @patch("daemon.DaemonContext")
    def test_listen(
        self,
        mock_daemon_context,
        mock_create_task,
        mock_delete_task,
        mock_update_task,
        mock_consumer,
        mock_logger,
        mock_pid,
    ):
        """Assert listener processes messages."""
        message1 = Mock()
        message2 = Mock()
        message3 = Mock()
        message4 = Mock()
        message5 = Mock()

        message1.value = {
            "authtype": random.choice(settings.SOURCES_CLOUDMETER_AUTHTYPES)
        }
        message1.headers = [
            ("event_type", b"Authentication.create"),
            ("encoding", b"json"),
        ]

        message2.value = "test message 2"
        message2.headers = [
            ("event_type", b"Authentication.destroy"),
            ("encoding", b"json"),
        ]

        message3.value = "test message 3"
        message3.headers = [
            ("event_type", b"Authentication.update"),
            ("encoding", b"json"),
        ]

        message4.value = {"authtype": "INVALID"}
        message4.headers = [
            ("event_type", b"Authentication.create"),
            ("encoding", b"json"),
        ]

        # Make sure to send this message last,
        # since it raises the TypeError that terminates the listener
        message5.value = "bad message"
        message5.headers = [Mock(), Mock()]

        mock_message_bundle_items = {
            "Partition 1": [message1, message2, message3, message4, message5]
        }

        mock_consumer_poll = mock_consumer.return_value.poll
        mock_consumer_poll.return_value = mock_message_bundle_items

        with self.assertRaises(TypeError):
            call_command("listen_to_sources")

        mock_create_task.delay.assert_called_once()
        mock_delete_task.delay.assert_called_once()
        mock_update_task.delay.assert_called_once()
        mock_consumer.assert_called_once()
        mock_consumer_poll.assert_called_once()
        self.assertEqual(3, mock_logger.info.call_count)

    @patch("util.management.commands.listen_to_sources.logger")
    def test_listener_cleanup(self, mock_logger):
        """Assert listener SIGTERM is logged."""
        Command.listener_cleanup(Mock(), signal.SIGTERM, Mock())
        mock_logger.info.assert_called_once()

    @patch("util.management.commands.listen_to_sources.PIDLockFile")
    @patch("util.management.commands.listen_to_sources.logger")
    @patch("util.management.commands.listen_to_sources.KafkaConsumer")
    @patch("daemon.DaemonContext")
    def test_listener_does_not_start_when_pidfile_exists(
        self, mock_daemon_context, mock_consumer, mock_logger, mock_pid
    ):
        """Assert errors are logged if pidfile is already locked."""
        mock_pid.side_effect = AlreadyLocked()
        call_command("listen_to_sources")
        mock_logger.exception.assert_called_once()
        mock_consumer.assert_not_called()
