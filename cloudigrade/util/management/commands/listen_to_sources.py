"""Listens to the platform kafka instance."""
import json
import logging
import signal
import sys

import daemon
from django.conf import settings
from django.core.management import BaseCommand
from django.utils.translation import gettext as _
from kafka import KafkaConsumer
from lockfile.pidlockfile import PIDLockFile

from api import tasks

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Listen to sources data on platform kafka topic."""

    def __init__(self, *args, **kwargs):
        """Init the class."""
        super().__init__(*args, **kwargs)
        self.run = False

    def handle(self, *args, **options):
        """Launch the listener."""
        with daemon.DaemonContext(
                pidfile=PIDLockFile(
                    f'{settings.LISTENER_PID_PATH}/cloudilistener.pid'),
                detach_process=False,
                signal_map={signal.SIGTERM: self.listener_cleanup},
                stdout=sys.stdout,
                stderr=sys.stderr):
            self.listen()

    def listen(self):
        """Listen to the configured topic."""
        topic = settings.LISTENER_TOPIC
        group_id = settings.LISTENER_GROUP_ID
        bootstrap_server = settings.LISTENER_SERVER
        bootstrap_server_port = settings.LISTENER_PORT
        enable_auto_commit = settings.LISTENER_AUTO_COMMIT
        consumer_timeout_ms = settings.LISTENER_TIMEOUT

        consumer = KafkaConsumer(
            topic,
            group_id=group_id,
            bootstrap_servers=[
                f'{bootstrap_server}:{bootstrap_server_port}'],
            auto_offset_reset='earliest',
            enable_auto_commit=enable_auto_commit,
            consumer_timeout_ms=consumer_timeout_ms,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')))

        self.run = True

        while self.run:
            message_bundle = consumer.poll()
            for topic_partition, messages in message_bundle.items():
                for message in messages:
                    self._process_message(message)

    def _process_message(self, message):
        """Process a single Kafka message."""
        event_type = None
        # The headers are a list of... tuples.
        for header in message.headers:
            if header[0] == 'event_type':
                event_type = header[1]
                break

        message_value = getattr(message, 'value', {})

        if event_type == b'Authentication.create':
            logger.info(
                _('An authentication object was created. Message: %s'),
                message_value,
            )
            if settings.ENABLE_DATA_MANAGEMENT_FROM_KAFKA_SOURCES:
                tasks.create_from_sources_kafka_message.delay(message_value)

        elif event_type == b'Authentication.destroy':
            logger.info(
                _('An authentication object was destroyed. Message: %s'),
                message_value,
            )
            if settings.ENABLE_DATA_MANAGEMENT_FROM_KAFKA_SOURCES:
                tasks.delete_from_sources_kafka_message.delay(message_value)

    def listener_cleanup(self, signum, frame):
        """Stop listening when system signal is received."""
        logger.info(_('Received %s. Stopping.'), signum)
        self.run = False
