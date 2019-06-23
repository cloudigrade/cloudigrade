"""Listens to the platform kafka instance."""
import json
import logging
import signal
import sys

import daemon
from environ import environ
from kafka import KafkaConsumer
from lockfile.pidlockfile import PIDLockFile

env = environ.Env()
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | '
                              '%(filename)s:%(funcName)s:%(lineno)d | '
                              '%(message)s')
handler.setFormatter(formatter)
handler.setLevel(env('LISTENER_LOG_LEVEL', default='INFO'))
logger.addHandler(handler)
logger.setLevel(env('LISTENER_LOG_LEVEL', default='INFO'))

run = False


def listen():
    """Listen to the configured topic."""
    topic = env('LISTENER_TOPIC', default='platform.sources.event-stream')
    group_id = env('LISTENER_GROUP_ID', default='cloudmeter_ci')
    bootstrap_server = env(
        'LISTENER_SERVER',
        default='platform-mq-ci-kafka-bootstrap.platform-mq-ci.svc')
    bootstrap_server_port = env('LISTENER_PORT', default='9092')
    enable_auto_commit = env.bool('LISTENER_AUTO_COMMIT', default=True)
    consumer_timeout_ms = env('LISTENER_TIMEOUT', default=1000)

    consumer = KafkaConsumer(
        topic,
        group_id=group_id,
        bootstrap_servers=[
            f'{bootstrap_server}:{bootstrap_server_port}'],
        auto_offset_reset='earliest',
        enable_auto_commit=enable_auto_commit,
        consumer_timeout_ms=consumer_timeout_ms,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')))

    global run
    run = True

    while run:
        message_bundle = consumer.poll()

        for topic_partition, messages in message_bundle.items():
            for message in messages:
                event_type = None
                # The headers are a list of... tuples.
                for header in message.headers:
                    if header[0] == 'event_type':
                        event_type = header[1]
                        break

                if event_type == b'Authentication.create':
                    logger.info(f'An authentication object was created. '
                                f'Message: {message.value}')
                elif event_type == b'Authentication.destroy':
                    logger.info(f'An authentication object was destroyed. '
                                f'Message: {message.value}')


def listener_cleanup(signum, frame):
    """Stop listening when system signal is received."""
    logger.info(f'Received {signum}, stopping.')
    global run
    run = False


if __name__ == '__main__':
    pid_path = env('LISTENER_PID_PATH', default='/var/run/cloudigrade')
    with daemon.DaemonContext(
            pidfile=PIDLockFile(f'{pid_path}/cloudilistener.pid'),
            files_preserve=[handler.stream, ],
            detach_process=False,
            signal_map={signal.SIGTERM: listener_cleanup},
            stdout=sys.stdout,
            stderr=sys.stderr):
        listen()
