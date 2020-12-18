"""Listens to the platform kafka instance."""
import json
import logging
import signal

from confluent_kafka import Consumer
from django.conf import settings
from django.core.management import BaseCommand
from django.utils.translation import gettext as _
from prometheus_client import Counter, start_http_server

from api import tasks

logger = logging.getLogger(__name__)

run_listener = False


class Command(BaseCommand):
    """Listen to sources data on platform kafka topic."""

    def __init__(self, *args, **kwargs):
        """Init the class."""
        super().__init__(*args, **kwargs)

        self.run = False

    def handle(self, *args, **options):
        """Launch the listener."""
        start_http_server(
            settings.LISTENER_METRICS_PORT
        )  # Start the metrics export server
        self.listen()

    def listen(self):
        """Listen to the configured topic."""
        topic = settings.LISTENER_TOPIC
        group_id = settings.LISTENER_GROUP_ID
        bootstrap_server = settings.LISTENER_SERVER
        bootstrap_server_port = settings.LISTENER_PORT
        bootstrap_servers = f"{bootstrap_server}:{bootstrap_server_port}"

        consumer_conf = {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
        }

        logger.info(
            _("Attempting to connect with following configuration: %(consumer_conf)s"),
            {"consumer_conf": consumer_conf},
        )

        consumer = Consumer(consumer_conf)

        try:
            logger.info(
                _("Listener ready to run, subscribing to %(topic)s"), {"topic": topic}
            )
            global run_listener
            run_listener = True
            consumer.subscribe([topic])

            while run_listener:
                msg = consumer.poll()
                if msg is None:
                    continue
                if msg.error():
                    logger.warning(_("Consumer error: {error}"), {"error": msg.error()})
                    continue

                self._process_message(msg)
        finally:
            logger.info(_("Listener closing."))
            consumer.close()

    def _process_message(self, message):
        """Process a single Kafka message."""
        event_type = None

        # The headers are a list of... tuples.
        # So we've established the headers are a list of tuples, but wait,
        # there's more! It is a tuple with a string key, and a bytestring
        # value because... reasons..? Let's clean that up.
        message_headers = [
            (
                key,
                value.decode("utf-8"),
            )
            for key, value in message.headers()
        ]
        for header in message_headers:
            if header[0] == "event_type":
                event_type = header[1]
                break

        message_value = json.loads(message.value().decode("utf-8"))

        logger.info(
            _("Processing Message: %(message_value)s. Headers: %(message_headers)s"),
            {"message_value": message_value, "message_headers": message_headers},
        )
        total_events.inc()

        if event_type == "ApplicationAuthentication.create":
            logger.info(
                _(
                    "An ApplicationAuthentication object was created. "
                    "Message: %(message_value)s. Headers: %(message_headers)s"
                ),
                {"message_value": message_value, "message_headers": message_headers},
            )
            create_events.inc()
            if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
                tasks.create_from_sources_kafka_message.delay(
                    message_value, message_headers
                )

        elif event_type in settings.KAFKA_DESTROY_EVENTS:
            logger.info(
                _(
                    "A Sources object was destroyed. "
                    "Message: %(message_value)s. Headers: %(message_headers)s"
                ),
                {"message_value": message_value, "message_headers": message_headers},
            )
            destroy_events.inc()
            if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
                tasks.delete_from_sources_kafka_message.delay(
                    message_value, message_headers, event_type
                )

        elif event_type == "Authentication.update":
            logger.info(
                _(
                    "An authentication object was updated. "
                    "Message: %(message_value)s. Headers: %(message_headers)s"
                ),
                {"message_value": message_value, "message_headers": message_headers},
            )
            update_events.inc()
            if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
                tasks.update_from_source_kafka_message.delay(
                    message_value, message_headers
                )


# Metrics
total_events_metric = Counter(
    "listener_processed_events_total",
    "Total number of processed events.",
    ("event_type",),
)
create_events = total_events_metric.labels("create")
update_events = total_events_metric.labels("update")
destroy_events = total_events_metric.labels("destroy")
total_events = total_events_metric.labels("total")


# Signal handling
def _listener_cleanup(signum, frame):
    """Stop listening when system signal is received."""
    logger.info(_("Received signal %s. Stopping."), signum)
    global run_listener
    run_listener = False


signal.signal(signal.SIGTERM, _listener_cleanup)
signal.signal(signal.SIGINT, _listener_cleanup)
