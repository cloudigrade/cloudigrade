"""Listens to the platform kafka instance."""
import logging
import os
import signal
import sys

import daemon
from confluent_kafka import Consumer
from django.conf import settings
from django.core.management import BaseCommand
from django.utils.translation import gettext as _
from lockfile import AlreadyLocked
from lockfile.pidlockfile import PIDLockFile

from api import tasks

logger = logging.getLogger(__name__)

PID_FILE = f"{settings.LISTENER_PID_PATH}/cloudilistener.pid"


class Command(BaseCommand):
    """Listen to sources data on platform kafka topic."""

    def __init__(self, *args, **kwargs):
        """Init the class."""
        super().__init__(*args, **kwargs)
        self.run = False

    def handle(self, *args, **options):
        """Launch the listener."""
        if os.path.exists(PID_FILE):
            pid = int(open(PID_FILE).read())
            logger.warning(_("Found existing pid file with pid: {}"))
            if os.getpid() != pid:
                logger.error(
                    _(
                        "Listener attempted to start with an existing stale pidfile."
                        "There should never be two instances of the listener running."
                        "Removing pid file before continuing..."
                    )
                )
                os.remove(PID_FILE)
                logger.debug(_("Stale PID file unlinked."))
        try:
            with daemon.DaemonContext(
                pidfile=PIDLockFile(PID_FILE),
                detach_process=False,
                signal_map={signal.SIGTERM: self.listener_cleanup},
                stdout=sys.stdout,
                stderr=sys.stderr,
            ):
                self.listen()
        except AlreadyLocked:
            logger.exception(
                _(
                    "Listener attempted to start with an existing pidfile, again??? "
                    "This should _really_ not be possible. "
                )
            )

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
            self.run = True
            consumer.subscribe([topic])

            while self.run:
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
        message_headers = message.headers()
        message_headers = [
            (
                key,
                value.decode("utf-8"),
            )
            for key, value in message_headers
        ]
        for header in message_headers:
            if header[0] == "event_type":
                event_type = header[1]
                break

        message_value = message.value().decode("utf-8")

        logger.info(
            _("Processing Message: %(message_value)s. Headers: %(message_headers)s"),
            {"message_value": message_value, "message_headers": message_headers},
        )

        if event_type == "ApplicationAuthentication.create":
            logger.info(
                _(
                    "An ApplicationAuthentication object was created. "
                    "Message: %(message_value)s. Headers: %(message_headers)s"
                ),
                {"message_value": message_value, "message_headers": message_headers},
            )
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
            if settings.SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA:
                tasks.update_from_source_kafka_message.delay(
                    message_value, message_headers
                )

    def listener_cleanup(self, signum, frame):
        """Stop listening when system signal is received."""
        logger.info(_("Received %s. Stopping."), signum)
        self.run = False
