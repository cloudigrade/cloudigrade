"""Celery Metrics."""
import logging
import re
import threading
import time

from django.utils.translation import gettext as _
from prometheus_client import Counter, Gauge, Histogram

from config.celery import app as celery_app


logger = logging.getLogger(__name__)


class CeleryMetrics:
    """Celery Metrics class for processing and exposing Prometheus metrics."""

    def __init__(self, interval=2, buckets=None):
        """Celery Metrics Initializer."""
        self.listener_started = False
        self.interval = interval
        self.state_counters = {
            "task-sent": Counter(
                "celery_task_sent",
                "Sent when a task message is published.",
                ["name", "hostname"],
            ),
            "task-received": Counter(
                "celery_task_received",
                "Sent when the worker receives a task.",
                ["name", "hostname"],
            ),
            "task-started": Counter(
                "celery_task_started",
                "Sent just before the worker executes the task.",
                ["name", "hostname"],
            ),
            "task-succeeded": Counter(
                "celery_task_succeeded",
                "Sent if the task executed successfully.",
                ["name", "hostname"],
            ),
            "task-failed": Counter(
                "celery_task_failed",
                "Sent if the execution of the task failed.",
                ["name", "hostname", "exception"],
            ),
            "task-rejected": Counter(
                "celery_task_rejected",
                "The task was rejected by the worker, "
                "possibly to be re-queued or moved to a dead letter queue.",
                ["name", "hostname"],
            ),
            "task-revoked": Counter(
                "celery_task_revoked",
                "Sent if the task has been revoked.",
                ["name", "hostname"],
            ),
            "task-retried": Counter(
                "celery_task_retried",
                "Sent if the task failed, but will be retried in the future.",
                ["name", "hostname"],
            ),
        }
        self.celery_worker_up = Gauge(
            "celery_worker_up",
            "Indicates if a worker has recently sent a heartbeat.",
            ["hostname"],
        )
        self.worker_tasks_active = Gauge(
            "celery_worker_tasks_active",
            "The number of tasks the worker is currently processing",
            ["hostname"],
        )
        self.celery_task_runtime = Histogram(
            "celery_task_runtime",
            "Histogram of task runtime measurements.",
            ["name", "hostname"],
            buckets=buckets or Histogram.DEFAULT_BUCKETS,
        )

    def handle_task_event(self, event):
        """Handle Celery task events."""
        self.state.event(event)
        task = self.state.tasks.get(event["uuid"])
        logger.debug(
            _("Received celery event='%s' for task='%s'"), event["type"], task.name
        )

        if event["type"] not in self.state_counters:
            logger.warning(
                _("No celery counter matches task state='%s'"), event["type"]
            )

        labels = {"name": task.name, "hostname": task.hostname}

        for counter_name, counter in self.state_counters.items():
            _labels = labels.copy()

            if counter_name == "task-failed":
                if counter_name == event["type"]:
                    _labels["exception"] = get_exception_class(task.exception)
                else:
                    _labels["exception"] = ""

            if counter_name == event["type"]:
                counter.labels(**_labels).inc()
            else:
                # increase unaffected counters by zero in order to make them visible
                counter.labels(**_labels).inc(0)

            logger.debug(
                _("Incremented celery metric='%s' labels='%s'"), counter._name, labels
            )

        # observe task runtime
        if event["type"] == "task-succeeded":
            self.celery_task_runtime.labels(**labels).observe(task.runtime)
            logger.debug(
                _("Observed celery metric='%s' labels='%s': %ss"),
                self.celery_task_runtime._name,
                labels,
                task.runtime,
            )

    def handle_worker_status(self, event, is_online):
        """Handle Celery worker status updates."""
        value = 1 if is_online else 0
        event_name = "worker-online" if is_online else "worker-offline"
        hostname = event["hostname"]
        logger.debug(
            _("Received celery event='%s' for hostname='%s'"), event_name, hostname
        )
        self.celery_worker_up.labels(hostname=hostname).set(value)

    def handle_worker_heartbeat(self, event):
        """Handle Celery worker heartbeats."""
        logger.debug(
            _("Received celery event='%s' for worker='%s'"),
            event["type"],
            event["hostname"],
        )

        worker_state = self.state.event(event)[0][0]
        active = worker_state.active or 0
        up = 1 if worker_state.alive else 0
        self.celery_worker_up.labels(hostname=event["hostname"]).set(up)
        self.worker_tasks_active.labels(hostname=event["hostname"]).set(active)
        logger.debug(
            _("Updated celery gauge='%s' value='%s'"),
            self.worker_tasks_active._name,
            active,
        )
        logger.debug(
            _("Updated celery gauge='%s' value='%s'"), self.celery_worker_up._name, up
        )

    def listener(self, daemon=False):
        """If not started, start the Celery event handler in a thread."""
        if self.listener_started:
            logger.info(_("Celery Metrics Listener already started"))
            return None
        logger.info(_("Celery Metrics Listener started ..."))
        self.listener_started = True
        thread = threading.Thread(target=self.celery_handler)
        if daemon:
            thread.daemon = True
        thread.start()
        return thread

    def celery_handler(self):
        """Register and trigger Celery handlers on events."""
        self.app = celery_app
        self.state = self.app.events.State()

        handlers = {
            "worker-heartbeat": self.handle_worker_heartbeat,
            "worker-online": lambda event: self.handle_worker_status(event, True),
            "worker-offline": lambda event: self.handle_worker_status(event, False),
        }
        for key in self.state_counters:
            handlers[key] = self.handle_task_event

        while True:
            try:
                with self.app.connection() as connection:
                    recv = self.app.events.Receiver(connection, handlers=handlers)
                    logger.info(
                        _("Capturing Celery Events from %s"),
                        self.app.connection.as_uri(),
                    )
                    recv.capture(limit=None, timeout=None, wakeup=True)

            except (KeyboardInterrupt, SystemExit):
                raise

            except Exception as e:
                # unable to capture
                logger.info(
                    _(
                        "Celery Metrics Listener Exception %s,"
                        " retrying in %d seconds."
                    ),
                    str(e),
                    self.interval,
                )
                pass

            time.sleep(self.interval)


exception_pattern = re.compile(r"^(\w+)\(")


def get_exception_class(exception_name: str):
    """Given the exception name, return the exception class."""
    m = exception_pattern.match(exception_name)
    assert m
    return m.group(1)
