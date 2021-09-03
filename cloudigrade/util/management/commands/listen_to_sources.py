"""Listens to the platform kafka instance."""
import json
import logging
import signal

from confluent_kafka import Consumer
from django.conf import settings
from django.core.management import BaseCommand
from django.utils.translation import gettext as _
from prometheus_client import Counter, start_http_server

from api.tasks import sources

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
                    logger.warning(
                        _("Consumer error: %(error)s"), {"error": msg.error()}
                    )
                    continue

                process_message(msg)
        finally:
            logger.info(_("Listener closing."))
            consumer.close()


def process_message(message):
    """
    Process a single Kafka message object.

    Args:
        message(confluent_kafka.Message): message object from the Kafka listener
    """
    event_type, headers, value = extract_raw_sources_kafka_message(message)

    logger.info(
        _("Processing %(event_type)s Message: %(value)s. Headers: %(headers)s"),
        {"event_type": event_type, "value": value, "headers": headers},
    )
    total_events.inc()

    if event_type == "ApplicationAuthentication.create":
        create_events.inc()
        process_sources_create_event(value, headers)
    elif event_type == "ApplicationAuthentication.destroy":
        destroy_events.inc()
        process_sources_destroy_event(value, headers)
    elif event_type == "Authentication.update":
        update_events.inc()
        process_sources_update_event(value, headers)
    elif event_type == "Application.pause":
        pause_events.inc()
        process_sources_pause_event(value, headers)
    elif event_type == "Application.unpause":
        unpause_events.inc()
        process_sources_unpause_event(value, headers)


def extract_raw_sources_kafka_message(message):
    """
    Extract the useful bits from a Kafka message originating from sources-api.

    Args:
        message(confluent_kafka.Message): message object from the Kafka listener

    Returns:
        tuple(string, list, dict) of the event_type, headers, and value.
    """
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

    return event_type, message_headers, message_value


def process_sources_create_event(value, headers):
    """Process the given sources-api create event message."""
    logger.info(
        _(
            "An ApplicationAuthentication object was created. "
            "Message: %(value)s. Headers: %(headers)s"
        ),
        {"value": value, "headers": headers},
    )
    if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
        sources.create_from_sources_kafka_message.delay(value, headers)


def process_sources_destroy_event(value, headers):
    """Process the given sources-api destroy event message."""
    logger.info(
        _(
            "An ApplicationAuthentication object was destroyed. "
            "Message: %(value)s. Headers: %(headers)s"
        ),
        {"value": value, "headers": headers},
    )
    if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
        sources.delete_from_sources_kafka_message.delay(value, headers)


def process_sources_update_event(value, headers):
    """Process the given sources-api update event message."""
    logger.info(
        _(
            "An authentication object was updated. "
            "Message: %(value)s. Headers: %(headers)s"
        ),
        {"value": value, "headers": headers},
    )
    if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
        sources.update_from_source_kafka_message.delay(value, headers)


def process_sources_pause_event(value, headers):
    """Process the given sources-api pause event message."""
    logger.info(
        _(
            "An application object was paused. "
            "Message: %(value)s. Headers: %(headers)s"
        ),
        {"value": value, "headers": headers},
    )
    if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
        sources.pause_from_sources_kafka_message.delay(value, headers)


def process_sources_unpause_event(value, headers):
    """Process the given sources-api unpause event message."""
    logger.info(
        _(
            "An application object was unpaused. "
            "Message: %(value)s. Headers: %(headers)s"
        ),
        {"value": value, "headers": headers},
    )
    if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
        sources.unpause_from_sources_kafka_message.delay(value, headers)


# Metrics
total_events_metric = Counter(
    "listener_processed_events_total",
    "Total number of processed events.",
    ("event_type",),
)
create_events = total_events_metric.labels("create")
update_events = total_events_metric.labels("update")
destroy_events = total_events_metric.labels("destroy")
pause_events = total_events_metric.labels("pause")
unpause_events = total_events_metric.labels("unpause")
total_events = total_events_metric.labels("total")


# Signal handling
def _listener_cleanup(signum, frame):
    """Stop listening when system signal is received."""
    logger.info(_("Received signal %s. Stopping."), signum)
    global run_listener
    run_listener = False


signal.signal(signal.SIGTERM, _listener_cleanup)
signal.signal(signal.SIGINT, _listener_cleanup)
