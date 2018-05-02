"""Various utility functions for the account app."""
import collections
from queue import Empty
import socket

import kombu
from django.conf import settings
from django.utils import timezone

from account import AWS_PROVIDER_STRING
from account import exceptions
from account.models import (AwsInstance, AwsInstanceEvent, AwsMachineImage,
                            InstanceEvent)


def create_initial_aws_instance_events(account, instances_data):
    """
    Create AwsInstance and AwsInstanceEvent the first time we see an instance.

    This function is a convenience helper for recording the first time we
    discover a running instance wherein we assume that "now" is the earliest
    known time that the instance was running.

    Args:
        account (AwsAccount): The account that owns the instance that spawned
            the data for these InstanceEvents.
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance

    Returns:
        dict: Similar to the incoming instances_data dict, the returned dict
        has keys that are AWS region IDs and values that are each a list of the
        created InstanceEvent objects.

    """
    saved_instances = collections.defaultdict(list)
    for region, instances in instances_data.items():
        for instance_data in instances:
            instance, __ = AwsInstance.objects.get_or_create(
                account=account,
                ec2_instance_id=instance_data['InstanceId'],
                region=region,
            )
            event = AwsInstanceEvent(
                instance=instance,
                event_type=InstanceEvent.TYPE.power_on,
                occurred_at=timezone.now(),
                subnet=instance_data['SubnetId'],
                ec2_ami_id=instance_data['ImageId'],
                instance_type=instance_data['InstanceType'],
            )
            event.save()
            saved_instances[region].append(instance)
    return dict(saved_instances)


def create_new_machine_images(account, instances_data):
    """
    Create AwsMachineImage that have not been seen before.

    Args:
        account (AwsAccount): The account associated with the machine image
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance

    Returns:
        list: A list of image ids that were added to the database

    """
    saved_amis = []
    for __, instances in instances_data.items():
        platforms = {instance['ImageId']: instance['Platform']
                     for instance in instances
                     if instance.get('Platform') == 'Windows'}
        seen_amis = set([instance['ImageId'] for instance in instances])
        known_amis = AwsMachineImage.objects.filter(
            ec2_ami_id__in=list(seen_amis)
        )
        new_amis = list(seen_amis.difference(known_amis))

        for new_ami in new_amis:
            ami = AwsMachineImage(
                account=account,
                ec2_ami_id=new_ami,
                is_windows=True if platforms.get(new_ami) else False
            )
            ami.save()

        saved_amis.extend(new_amis)
    return saved_amis


def generate_aws_ami_messages(instances_data, ami_list):
    """
    Format information about the machine image for messaging.

    This is a pre-step to sending messages to a message queue.

    Args:
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance
        ami_list (list): A list of machine images that need
            messages generated.

    Returns:
        list[dict]: A list of message dictionaries

    """
    messages = []
    for region, instances in instances_data.items():
        for instance in instances:
            if (instance['ImageId'] in ami_list and
                    instance.get('Platform') != 'Windows'):
                messages.append(
                    {
                        'cloud_provider': AWS_PROVIDER_STRING,
                        'region': region,
                        'image_id': instance['ImageId']
                    }
                )
    return messages


def _create_exchange_and_queue(queue_name):
    """
    Create a Kombu message Exchange and Queue.

    Args:
        queue_name (str): The target queue's name

    Returns:
        tuple(kombu.Exchange, kombu.Queue)

    """
    exchange = kombu.Exchange(
        settings.RABBITMQ_EXCHANGE_NAME,
        'direct',
        durable=True
    )
    message_queue = kombu.Queue(
        queue_name,
        exchange=exchange,
        routing_key=queue_name
    )
    return exchange, message_queue


def add_messages_to_queue(queue_name, messages):
    """
    Send messages to a message queue.

    Args:
        queue_name (str): The queue to add messages to
        messages (list[dict]): A list of message dictionaries. The message
            dicts will be serialized as JSON strings.

    Returns:
        dict: A mapping of machine image ID to result boolean value

    """
    exchange, message_queue = _create_exchange_and_queue(queue_name)

    with kombu.Connection(settings.RABBITMQ_URL) as conn:
        # Normally we shouldn't have to do an explicit
        # conn.connect(). But Kombu 4.1.0 has a bug where if we try to
        # just use a connection, Kombu will connect ignoring all of
        # the connection parameters, in particular the timeout. This
        # means that the connection object can hang indefinitely if it
        # can't reach RabbitMQ. Work around this by calling
        # conn.connect() before using conn.
        try:
            conn.connect()
        except socket.gaierror as exc:
            # The socket error message doesn't include the URL it
            # couldn't reach, which makes it difficult to debug, so
            # re-raise a different exception with more information.
            raise exceptions.RabbitMQUnreachableError() from exc
        producer = conn.Producer(serializer='json')
        for message in messages:
            producer.publish(
                message,
                retry=True,
                exchange=exchange,
                routing_key=queue_name,
                declare=[message_queue]
            )


def read_messages_from_queue(queue_name, max_count=1):
    """
    Read messages (up to max_count) from a message queue.

    Args:
        queue_name (str): The queue to read messages from
        max_count (int): Max number of messages to read

    Returns:
        list[object]: The dequeued messages.

    """
    __, message_queue = _create_exchange_and_queue(queue_name)
    messages = []
    with kombu.Connection(settings.RABBITMQ_URL) as conn:
        try:
            consumer = conn.SimpleQueue(name=message_queue)
            while len(messages) < max_count:
                message = consumer.get_nowait()
                messages.append(message.payload)
                message.ack()
        except Empty:
            pass
    return messages
