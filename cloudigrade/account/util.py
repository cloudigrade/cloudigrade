"""Various utility functions for the account app."""
import collections
import logging
import math
import uuid

import boto3
import jsonpickle
from botocore.exceptions import ClientError
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from account import AWS_PROVIDER_STRING
from account.models import (AwsInstance, AwsInstanceEvent, AwsMachineImage,
                            AwsMachineImageCopy, ImageTag, InstanceEvent)
from util.aws import is_instance_windows

logger = logging.getLogger(__name__)

SQS_SEND_BATCH_SIZE = 10  # boto3 supports sending up to 10 items.
SQS_RECEIVE_BATCH_SIZE = 10  # boto3 supports receiving of up to 10 items.


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
            saved_instances[region].append(
                save_instance_events(account, instance_data, region))
    return dict(saved_instances)


def save_instance_events(account, instance_data, region, events=None):
    """
    Save provided events, and create the instance object if it does not exist.

    Args:
        account (AwsAccount): The account that owns the instance that spawned
            the data for these InstanceEvents.
        instance_data (dict): Dictionary containing instance information.
        region (str): AWS Region.
        events (list): List of Events to be saved.

    Returns:
        AwsInstance: Object representing the saved instance.

    """
    instance, __ = AwsInstance.objects.get_or_create(
        account=account,
        ec2_instance_id=instance_data['InstanceId'] if isinstance(
            instance_data, dict) else instance_data.instance_id,
        region=region,
    )
    if events is None:
        # Assume this is the initial event
        event = AwsInstanceEvent(
            instance=instance,
            event_type=InstanceEvent.TYPE.power_on,
            occurred_at=timezone.now(),
            subnet=instance_data['SubnetId'],
            ec2_ami_id=instance_data['ImageId'],
            instance_type=instance_data['InstanceType'],
        )
        event.save()
    else:
        for event in events:
            event = AwsInstanceEvent(
                instance=instance,
                event_type=event['event_type'],
                occurred_at=event['occurred_at'],
                subnet=event['subnet'],
                ec2_ami_id=event['ec2_ami_id'],
                instance_type=event['instance_type'],
            )
            event.save()
    return instance


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
        windows_instances = {
            instance['ImageId']
            for instance in instances
            if is_instance_windows(instance)}
        seen_amis = set([instance['ImageId'] for instance in instances])
        known_amis = AwsMachineImage.objects.filter(
            ec2_ami_id__in=list(seen_amis)
        )
        new_amis = list(seen_amis.difference(known_amis))

        for ami_id in new_amis:
            ami, __ = save_machine_images(account, ami_id)
            if ami_id in windows_instances:
                tag_windows(ami)

        saved_amis.extend(new_amis)
    return saved_amis


def save_machine_images(account, ami_id):
    """
    Save the image object.

    Args:
        account (AwsAccount): The account associated with the machine image
        ami_id (str): The AWS AMI ID.

    Returns:

    """
    ami, new = AwsMachineImage.objects.get_or_create(
        account=account,
        ec2_ami_id=ami_id,
    )

    return ami, new


def tag_windows(ami):
    """
    Tags the provided image with the windows tag.

    Args:
        ami (AwsMachineImage): Object representing the image.

    Returns:
        AwsMachineImage: Updated object.

    """
    ami.tags.add(ImageTag.objects.filter(description='windows').first())
    ami.status = ami.INSPECTED
    ami.save()

    return ami


def start_image_inspection(arn, image_id, region):
    """
    Start image inspection of the provided image.

    Args:
        arn (str):  The AWS Resource Number for the account with the snapshot
        image_id (str): The AWS ID for the machine image
        region (str): The region the snapshot resides in

    """
    image = AwsMachineImage.objects.get(ec2_ami_id=image_id)
    image.status = image.PREPARING
    image.save()

    from account.tasks import copy_ami_snapshot

    copy_ami_snapshot.delay(str(arn), image_id, region)


def create_aws_machine_image_copy(copy_ami_id, reference_ami_id):
    """
    Create an AwsMachineImageCopy given the copy and reference AMI IDs.

    Args:
        copy_ami_id (str): the AMI IS of the copied image
        reference_ami_id (str): the AMI ID of the original reference image
    """
    reference = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
    AwsMachineImageCopy.objects.create(ec2_ami_id=copy_ami_id,
                                       account=reference.account,
                                       reference_awsmachineimage=reference)


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
                    not is_instance_windows(instance)):
                messages.append(
                    {
                        'cloud_provider': AWS_PROVIDER_STRING,
                        'region': region,
                        'image_id': instance['ImageId']
                    }
                )
    return messages


def _get_sqs_queue_url(queue_name):
    """
    Get the SQS queue URL for the given queue name.

    This has the side-effect on ensuring that the queue exists.

    Args:
        queue_name (str): the name of the target SQS queue

    Returns:
        str: the queue's URL.

    """
    sqs = boto3.client('sqs')
    try:
        return sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
    except ClientError as e:
        if e.response['Error']['Code'].endswith('.NonExistentQueue'):
            return sqs.create_queue(QueueName=queue_name)['QueueUrl']
        raise


def _sqs_wrap_message(message):
    """
    Wrap the message in a dict for SQS batch sending.

    Args:
        message (object): message to encode and wrap

    Returns:
        dict: structured entry for sending to send_message_batch

    """
    return {
        'Id': str(uuid.uuid4()),
        # Yes, the outgoing message uses MessageBody, not Body.
        'MessageBody': jsonpickle.encode(message),
    }


def _sqs_unwrap_message(sqs_message):
    """
    Unwrap the sqs_message to get the original message.

    Args:
        sqs_message (dict): object to unwrap and decode

    Returns:
        object: the unwrapped and decoded message object

    """
    return jsonpickle.decode(
        # Yes, the response has Body, not MessageBody.
        sqs_message['Body']
    )


def add_messages_to_queue(queue_name, messages):
    """
    Send messages to an SQS queue.

    Args:
        queue_name (str): The queue to add messages to
        messages (list[dict]): A list of message dictionaries. The message
            dicts will be serialized as JSON strings.
    """
    queue_url = _get_sqs_queue_url(queue_name)
    sqs = boto3.client('sqs')

    wrapped_messages = [_sqs_wrap_message(message) for message in messages]
    batch_count = math.ceil(len(messages) / SQS_SEND_BATCH_SIZE)

    for batch_num in range(batch_count):
        start_pos = batch_num * SQS_SEND_BATCH_SIZE
        end_pos = start_pos + SQS_SEND_BATCH_SIZE - 1
        batch = wrapped_messages[start_pos:end_pos]
        sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)


def read_messages_from_queue(queue_name, max_count=1):
    """
    Read messages (up to max_count) from an SQS queue.

    Args:
        queue_name (str): The queue to read messages from
        max_count (int): Max number of messages to read

    Returns:
        list[object]: The de-queued messages.

    """
    queue_url = _get_sqs_queue_url(queue_name)
    sqs = boto3.client('sqs')
    sqs_messages = []
    max_batch_size = min(SQS_RECEIVE_BATCH_SIZE, max_count)
    for __ in range(max_count):
        # Because receive_message does *not* actually reliably return
        # MaxNumberOfMessages number of messages especially (read the docs),
        # our iteration count is actually max_count and we have some
        # conditions at the end that break us out when we reach the true end.
        new_messages = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_batch_size
        ).get('Messages', [])
        if len(new_messages) == 0:
            break
        sqs_messages.extend(new_messages)
        if len(sqs_messages) >= max_count:
            break
    messages = []
    for sqs_message in sqs_messages:
        try:
            unwrapped = _sqs_unwrap_message(sqs_message)
            sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=sqs_message['ReceiptHandle'],
            )
            messages.append(unwrapped)
        except ClientError as e:
            # I'm not sure exactly what exceptions could land here, but we
            # probably should log them, stop attempting further deletes, and
            # return what we have received (and thus deleted!) so far.
            log_message = _(
                'Unexpected error when attempting to read from {0}: {1}'
            ).format(queue_url, getattr(e, 'response', {}).get('Error'))
            logger.error(log_message)
            logger.exception(e)
            break
    return messages


def convert_param_to_int(name, value):
    """Check if a value is convertable to int.

    Args:
        name (str): The field name being validated
        value: The value to convert to int

    Returns:
        int: The int value
    Raises:
        ValidationError if value not convertable to an int

    """
    try:
        return int(value)
    except ValueError:
        error = {
            name: [_('{} must be an integer.'.format(name))]
        }
        raise ValidationError(error)
