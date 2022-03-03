"""Collection of tests for Celery Metrics in the internal API."""

import uuid
from threading import Thread
from unittest.mock import MagicMock, patch

import faker
from django.test import TestCase

from internal import metrics


_faker = faker.Faker()
metrics_listener_retry_interval = 1
celery_metrics = metrics.CeleryMetrics(interval=metrics_listener_retry_interval)


class InternalMetricsTest(TestCase):
    """
    Internal Celery Metrics test case.

    These tests verify that the Prometheus counters labels are appropriately
    updated upon receiving Celery task events.
    """

    def setUp(self):
        """Set up test data."""
        self.task_name = "api.analyze_logs"
        self.broker_url = "redis://" + _faker.hostname() + ":6379"
        self.event_uuid = str(uuid.uuid4())
        self.hostname = "celery@" + _faker.hostname()
        self.task = MagicMock()
        self.task.name = self.task_name
        self.task.hostname = self.hostname

    def test_listener(self):
        """Test the listener gets started."""
        thread = celery_metrics.listener(daemon=True)
        self.assertIsNot(thread, None)
        self.assertIsInstance(thread, Thread)
        self.assertTrue(celery_metrics.listener_started)

    def test_listener_already_started(self):
        """Test the listener is already started."""
        celery_metrics.listener_started = True
        thread = celery_metrics.listener(daemon=True)
        self.assertIsNone(thread)

    @patch("internal.metrics.celery_app")
    def test_celery_handler_system_exit(self, mock_celery_app):
        """Test the celery_handler with a system exit exception."""
        mock_capture = MagicMock(side_effect=SystemExit)
        mock_recv = MagicMock()
        mock_recv().capture = mock_capture
        mock_celery_app.connection = MagicMock()
        mock_celery_app.connection().as_uri.return_value = self.broker_url
        mock_celery_app.events = MagicMock(Receiver=mock_recv)
        with self.assertRaises(SystemExit), self.assertLogs(
            "internal.metrics", level="INFO"
        ) as logging_watcher:
            celery_metrics.celery_handler()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }

        expected_info_message = f"Capturing Celery Events from {self.broker_url}"
        self.assertIn(expected_info_message, info_messages)

    @patch("internal.metrics.celery_app")
    def test_celery_handler_exception(self, mock_celery_app):
        """Test exceptions in the celery_handler."""
        exception_name = "bad_exception"
        mock_capture = MagicMock(side_effect=[Exception(exception_name), SystemExit])
        mock_recv = MagicMock()
        mock_recv().capture = mock_capture
        mock_celery_app.connection = MagicMock()
        mock_celery_app.connection().as_uri.return_value = self.broker_url
        mock_celery_app.events = MagicMock(Receiver=mock_recv)
        with self.assertRaises(SystemExit), self.assertLogs(
            "internal.metrics", level="INFO"
        ) as logging_watcher:
            celery_metrics.celery_handler()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }
        expected_info_messages = [
            f"Capturing Celery Events from {self.broker_url}",
            f"Celery Metrics Listener Exception {exception_name},"
            f" retrying in {metrics_listener_retry_interval} seconds.",
        ]

        for expected_info_message in expected_info_messages:
            self.assertIn(expected_info_message, info_messages)

    def test_task_started_event(self):
        """Test the handle_task_event handler for a task-started event."""
        event = {
            "type": "task-started",
            "hostname": self.hostname,
            "uuid": self.event_uuid,
        }
        task_started_counter = MagicMock(labels=MagicMock())
        celery_metrics.state_counters = {"task-started": task_started_counter}
        tasks = {self.event_uuid: self.task}
        celery_metrics.state = MagicMock(tasks=tasks)
        celery_metrics.handle_task_event(event)
        task_started_counter.labels.assert_called_with(
            name=self.task_name, hostname=self.hostname
        )
        task_started_counter.labels.return_value.inc.assert_called_with()

    def test_invalid_task_event(self):
        """Test the handle_task_event handler with an invalid task event."""
        task_event = "unknown-task-event"
        event = {"type": task_event, "hostname": self.hostname, "uuid": self.event_uuid}
        celery_metrics.state = MagicMock()

        with self.assertLogs("internal.metrics", level="WARNING") as logging_watcher:
            celery_metrics.handle_task_event(event)

        warn_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "WARNING"
        }

        expected_info_message = f"No celery counter matches task state='{task_event}'"
        self.assertIn(expected_info_message, warn_messages)

    def test_task_succeeded_event(self):
        """Test the handle_task_event handler for a succeeded task event."""
        event = {
            "type": "task-succeeded",
            "hostname": self.hostname,
            "uuid": self.event_uuid,
        }
        task_succeeded_counter = MagicMock(labels=MagicMock())
        task_runtime_histogram = MagicMock(labels=MagicMock())
        celery_metrics.state_counters = {"task-succeeded": task_succeeded_counter}
        celery_metrics.celery_task_runtime = task_runtime_histogram
        self.task.runtime = 1000
        tasks = {self.event_uuid: self.task}
        celery_metrics.state = MagicMock(tasks=tasks)
        celery_metrics.handle_task_event(event)
        task_succeeded_counter.labels.assert_called_with(
            name=self.task_name, hostname=self.hostname
        )
        task_succeeded_counter.labels.return_value.inc.assert_called_with()
        task_runtime_histogram.labels.assert_called_with(
            name=self.task_name, hostname=self.hostname
        )
        task_runtime_histogram.labels.return_value.observe.assert_called_with(
            self.task.runtime
        )

    def test_task_failed_event(self):
        """Test the handle_task_event handler for a failed task event."""
        event = {
            "type": "task-failed",
            "hostname": self.hostname,
            "uuid": self.event_uuid,
        }
        task_failed_counter = MagicMock(labels=MagicMock())
        celery_metrics.state_counters = {"task-failed": task_failed_counter}
        self.task.exception = "SomeException(Some Error)"
        tasks = {self.event_uuid: self.task}
        celery_metrics.state = MagicMock(tasks=tasks)
        celery_metrics.handle_task_event(event)
        task_failed_counter.labels.assert_called_with(
            name=self.task_name, hostname=self.hostname, exception="SomeException"
        )
        task_failed_counter.labels.return_value.inc.assert_called_with()

    def test_worker_heartbeat(self):
        """Test the handle_worker_heartbeat handler."""
        event = {"type": "worker-heartbeat", "hostname": self.hostname}
        worker_up_gauge = MagicMock(labels=MagicMock())
        tasks_active_gauge = MagicMock(labels=MagicMock())
        celery_metrics.celery_worker_up = worker_up_gauge
        celery_metrics.celery_tasks_active = tasks_active_gauge
        celery_metrics.state = MagicMock(return_value=[[MagicMock(active=1)]])
        celery_metrics.handle_worker_heartbeat(event)
        worker_up_gauge.labels.assert_called_with(hostname=self.hostname)
        worker_up_gauge.labels.return_value.set.assert_any_call(1)

    def test_worker_online_status(self):
        """Test the handle_worker_status handler for worker-online."""
        event = {"hostname": self.hostname}
        worker_up_gauge = MagicMock(labels=MagicMock())
        celery_metrics.celery_worker_up = worker_up_gauge
        celery_metrics.handle_worker_status(event, 1)
        worker_up_gauge.labels.assert_called_with(hostname=self.hostname)
        worker_up_gauge.labels.return_value.set.assert_any_call(1)

    def test_worker_offline_status(self):
        """Test the handle_worker_status handler for worker-offline."""
        event = {"hostname": self.hostname}
        worker_up_gauge = MagicMock(labels=MagicMock())
        celery_metrics.celery_worker_up = worker_up_gauge
        celery_metrics.handle_worker_status(event, 0)
        worker_up_gauge.labels.assert_called_with(hostname=self.hostname)
        worker_up_gauge.labels.return_value.set.assert_any_call(0)
