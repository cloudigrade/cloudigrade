"""Various utility functions for the account app."""
import logging
import math
import uuid
from decimal import Decimal

import boto3
import jsonpickle
from botocore.exceptions import ClientError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from account import AWS_PROVIDER_STRING
from account.models import (AwsInstance, AwsInstanceEvent, AwsMachineImage,
                            AwsMachineImageCopy, InstanceEvent, MachineImage,
                            Run)
from account.reports import normalize_runs
from util import aws

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
    """
    for region, instances in instances_data.items():
        for instance_data in instances:
            instance = save_instance(account, instance_data, region)
            save_instance_events(instance, instance_data)


def save_instance(account, instance_data, region):
    """
    Create or Update the instance object.

    Note: This function assumes the images related to the instance have
    already been created and saved.

    Args:
        account (AwsAccount): The account that owns the instance that spawned
            the data for this Instance.
        instance_data (dict): Dictionary containing instance information.
        region (str): AWS Region.
        events (list[dict]): List of dicts representing Events to be saved.

    Returns:
        AwsInstance: Object representing the saved instance.

    """
    instance, created = AwsInstance.objects.get_or_create(
        account=account,
        ec2_instance_id=instance_data['InstanceId'] if isinstance(
            instance_data, dict) else instance_data.instance_id,
        region=region,
    )
    image_id = (
        instance_data.get('ImageId', None)
        if isinstance(instance_data, dict)
        else getattr(instance_data, 'image_id', None)
    )

    # If for some reason we don't get the image_id, we cannot look up
    # the associated image.
    if image_id is None:
        machineimage = None
    else:
        machineimage, created = AwsMachineImage.objects.get_or_create(
            ec2_ami_id=image_id,
            defaults={
                'status': MachineImage.UNAVAILABLE,
                'region': region
            }
        )
        if created:
            logger.info(_(
                'Missing image data for %s; creating UNAVAILABLE stub image.'
            ), instance_data)

    if machineimage is not None:
        instance.machineimage = machineimage
        instance.save()
    return instance


def save_instance_events(instance, instance_data, events=None):
    """
    Save provided events, and create the instance object if it does not exist.

    Note: This function assumes the images related to the instance events have
    already been created and saved.

    Args:
        instance (AwsInstance): The Instance is associated with
            these InstanceEvents.
        instance_data (dict): Dictionary containing instance information.
        region (str): AWS Region.
        events (list[dict]): List of dicts representing Events to be saved.

    Returns:
        AwsInstance: Object representing the saved instance.

    """
    # When processing events, it's possible that we get information
    # about an instance but we don't know what image was under it
    # because the instance may have been terminated and cleaned up
    # before we could look at it. In that case, we (correctly) have to
    # save the event with no known image.
    if instance is None:
        machineimage = None
    else:
        machineimage = (
            instance.machineimage
            if hasattr(instance, 'machineimage')
            else None
        )
    from analyzer import tasks as analyzer_tasks
    if events is None:
        # As of issue #512 we do not use the stored machineimage on the
        # instanceevent. But we keep storing it here anyways in order
        # to remain backwards compatible
        event = AwsInstanceEvent(
            instance=instance,
            machineimage=machineimage,
            event_type=InstanceEvent.TYPE.power_on,
            occurred_at=timezone.now(),
            subnet=instance_data['SubnetId'],
            instance_type=instance_data['InstanceType'],
        )
        event.save()
        analyzer_tasks.process_instance_event(event)
    else:
        logger.info(_('saving %(count)s new event(s) for %(instance)s'),
                    {'count': len(events), 'instance': instance})
        for event in events:
            event = AwsInstanceEvent(
                instance=instance,
                machineimage=machineimage,
                event_type=event['event_type'],
                occurred_at=event['occurred_at'],
                subnet=event['subnet'],
                instance_type=event['instance_type'],
            )
            event.save()
            analyzer_tasks.process_instance_event(event)

    return instance


def create_new_machine_images(session, instances_data):
    """
    Create AwsMachineImage objects that have not been seen before.

    Note:
        During processing, this makes AWS API calls to describe all images
        for the instances found for each region, and we bundle bits of those
        responses with the actual AwsMachineImage creation. We do this all at
        once here to minimize the number of AWS API calls.

    Args:
        session (boto3.Session): The session that found the machine image
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance

    Returns:
        list: A list of image ids that were added to the database

    """
    log_prefix = 'create_new_machine_images'
    seen_ami_ids = {
        instance['ImageId']
        for instances in instances_data.values()
        for instance in instances
    }
    logger.info(_('%(prefix)s: all AMI IDs found: %(seen_ami_ids)s'),
                {'prefix': log_prefix, 'seen_ami_ids': seen_ami_ids})
    known_images = AwsMachineImage.objects.filter(
        ec2_ami_id__in=list(seen_ami_ids)
    )
    known_ami_ids = {
        image.ec2_ami_id for image in known_images
    }
    logger.info(_('%(prefix)s: Skipping known AMI IDs: %(known_ami_ids)s'),
                {'prefix': log_prefix, 'known_ami_ids': known_ami_ids})

    new_described_images = {}
    windows_ami_ids = []

    for region_id, instances in instances_data.items():
        ami_ids = set([instance['ImageId'] for instance in instances])
        new_ami_ids = ami_ids - known_ami_ids
        if new_ami_ids:
            new_described_images[region_id] = (
                aws.describe_images(session, new_ami_ids, region_id)
            )
        windows_ami_ids.extend({
            instance['ImageId']
            for instance in instances
            if aws.is_instance_windows(instance)
        })
    logger.info(_('%(prefix)s: Windows AMI IDs found: %(windows_ami_ids)s'),
                {'prefix': log_prefix, 'windows_ami_ids': windows_ami_ids})

    new_image_ids = []
    for region_id, described_images in new_described_images.items():
        for described_image in described_images:
            ami_id = described_image['ImageId']
            owner_id = Decimal(described_image['OwnerId'])
            name = described_image['Name']
            windows = ami_id in windows_ami_ids
            region = region_id
            openshift = len([
                tag for tag in described_image.get('Tags', [])
                if tag.get('Key') == aws.OPENSHIFT_TAG
            ]) > 0

            logger.info(_('%(prefix)s: Saving new AMI ID: %(ami_id)s'),
                        {'prefix': log_prefix, 'ami_id': ami_id})
            image, new = save_new_aws_machine_image(
                ami_id, name, owner_id, openshift, windows, region)
            if new:
                new_image_ids.append(ami_id)

    return new_image_ids


def save_new_aws_machine_image(ami_id, name, owner_aws_account_id,
                               openshift_detected, windows_detected, region):
    """
    Save a new AwsMachineImage image object.

    Note:
        If an AwsMachineImage already exists with the provided ami_id, we do
        not create a new image nor do we modify the existing one. In that case,
        we simply fetch and return the image with the matching ami_id.

    Args:
        ami_id (str): The AWS AMI ID.
        name (str): the name of the image
        owner_aws_account_id (Decimal): the AWS account ID that owns this image
        openshift_detected (bool): was openshift detected for this image
        windows_detected (bool): was windows detected for this image
        region (str): Region where the image was found

    Returns (AwsMachineImage, bool): The object representing the saved model
        and a boolean of whether it was new or not.

    """
    platform = AwsMachineImage.NONE
    status = AwsMachineImage.PENDING
    if windows_detected:
        platform = AwsMachineImage.WINDOWS
        status = AwsMachineImage.INSPECTED

    ami, new = AwsMachineImage.objects.get_or_create(
        ec2_ami_id=ami_id,
        defaults={
            'platform': platform,
            'owner_aws_account_id': owner_aws_account_id,
            'name': name,
            'status': status,
            'openshift_detected': openshift_detected,
            'region': region,
        }
    )

    return ami, new


def start_image_inspection(arn, ami_id, region):
    """
    Start image inspection of the provided image.

    Args:
        arn (str):  The AWS Resource Number for the account with the snapshot
        ami_id (str): The AWS ID for the machine image
        region (str): The region the snapshot resides in

    Returns:
        AwsMachineImage: Image being inspected

    """
    logger.info(
        _('Starting inspection for ami %(ami_id)s in region %(region)s '
          'through arn %(arn)s'),
        {'ami_id': ami_id, 'region': region, 'arn': arn}
    )
    ami = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
    ami.status = ami.PREPARING
    ami.save()

    if ami.is_marketplace or ami.is_cloud_access:
        ami.status = ami.INSPECTED
        ami.save()
    else:
        # Local import to get around a circular import issue
        from account.tasks import copy_ami_snapshot
        copy_ami_snapshot.delay(arn, ami_id, region)

    return ami


def create_aws_machine_image_copy(copy_ami_id, reference_ami_id):
    """
    Create an AwsMachineImageCopy given the copy and reference AMI IDs.

    Args:
        copy_ami_id (str): the AMI IS of the copied image
        reference_ami_id (str): the AMI ID of the original reference image
    """
    reference = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
    AwsMachineImageCopy.objects.create(
        ec2_ami_id=copy_ami_id,
        owner_aws_account_id=reference.owner_aws_account_id,
        reference_awsmachineimage=reference)


def generate_aws_ami_messages(instances_data, ami_id_list):
    """
    Format information about the machine image for messaging.

    This is a pre-step to sending messages to a message queue.

    Args:
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance
        ami_id_list (list): A list of machine image IDs that need
            messages generated.

    Returns:
        list[dict]: A list of message dictionaries

    """
    messages = []
    for region, instances in instances_data.items():
        for instance in instances:
            if (instance['ImageId'] in ami_id_list and
                    not aws.is_instance_windows(instance)):
                messages.append(
                    {
                        'cloud_provider': AWS_PROVIDER_STRING,
                        'region': region,
                        'image_id': instance['ImageId']
                    }
                )
    return messages


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
    queue_url = aws.get_sqs_queue_url(queue_name)
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
    queue_url = aws.get_sqs_queue_url(queue_name)
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
            logger.error(
                _('Unexpected error when attempting to read from %(queue)s: '
                  '%(error)s'),
                {
                    'queue': queue_url,
                    'error': getattr(e, 'response', {}).get('Error')
                }
            )
            logger.exception(e)
            break
    return messages


def convert_param_to_int(name, value):
    """Check if a value is convertible to int.

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


def recalculate_runs(events):
    """Take in events and calculate runs based on them."""
    for event in events:
        # check if event occurred before any runs
        if Run.objects.filter(
                instance_id=event.instance_id,
                start_time__gt=event.occurred_at
        ).exists():
            # need to torch these runs
            runs = Run.objects.filter(
                instance_id=event.instance_id,
                start_time__gt=event.occurred_at)
            events = InstanceEvent.objects.filter(
                instance_id=event.instance_id,
                occurred_at__gte=event.occurred_at) \
                .select_related('instance') \
                .prefetch_related('machineimage') \
                .order_by('instance__id')
            normalized_runs = normalize_runs(events)

            with transaction.atomic():
                runs.delete()
                for index, normalized_run in enumerate(normalized_runs):
                    logger.info('Processing run {} of {}'.format(
                        index + 1, len(normalized_runs)))
                    run = Run(
                        start_time=normalized_run.start_time,
                        end_time=normalized_run.end_time,
                        machineimage_id=normalized_run.image_id,
                        instance_id=normalized_run.instance_id,
                        instance_type=normalized_run.instance_type,
                        memory=normalized_run.instance_memory,
                        vcpu=normalized_run.instance_vcpu,
                    )
                    run.save()

        # check to see if even occurred within a run
        elif Run.objects.filter(
                instance_id=event.instance_id,
                start_time__lt=event.occurred_at,
                end_time__gt=event.occurred_at).exists():
            runs = Run.objects.filter(
                instance_id=event.instance_id,
                start_time__lt=event.occurred_at,
                end_time__gt=event.occurred_at)
            events = InstanceEvent.objects.filter(
                instance_id=event.instance_id,
                occurred_at__gte=event.occurred_at) \
                .select_related('instance') \
                .prefetch_related('machineimage') \
                .order_by('instance__id')
            normalized_runs = normalize_runs(events)

            with transaction.atomic():
                runs.delete()
                for index, normalized_run in enumerate(normalized_runs):
                    logger.info('Processing run {} of {}'.format(
                        index + 1, len(normalized_runs)))
                    run = Run(
                        start_time=normalized_run.start_time,
                        end_time=normalized_run.end_time,
                        machineimage_id=normalized_run.image_id,
                        instance_id=normalized_run.instance_id,
                        instance_type=normalized_run.instance_type,
                        memory=normalized_run.instance_memory,
                        vcpu=normalized_run.instance_vcpu,
                    )
                    run.save()

        # if this is a power off event, and we have a run with no end_time.
        # complete it
        elif event.event_type == event.TYPE.power_off and Run.objects.filter(
                instance_id=event.instance_id,
                start_time__lt=event.occurred_at,
                end_time=None
        ).exists():
            run = Run.objects.filter(
                instance_id=event.instance_id,
                start_time__lt=event.occurred_at,
                end_time=None
            ).earliest('start_time')
            run.end_time = event.occurred_at
            run.save()

        # if event is a power on event, and we didn't hit previous checks,
        # create a new run
        elif event.event_type == event.TYPE.power_on and not \
                Run.objects.filter(
                    instance_id=event.instance_id,
                    end_time=None,
                ).exists():
            normalized_runs = normalize_runs([event])
            for index, normalized_run in enumerate(normalized_runs):
                logger.info('Processing run {} of {}'.format(
                    index + 1, len(normalized_runs)))
                run = Run(
                    start_time=normalized_run.start_time,
                    end_time=normalized_run.end_time,
                    machineimage_id=normalized_run.image_id,
                    instance_id=normalized_run.instance_id,
                    instance_type=normalized_run.instance_type,
                    memory=normalized_run.instance_memory,
                    vcpu=normalized_run.instance_vcpu,
                )
                run.save()


def validate_event(event, start):
    """
    Ensure that the event is relevant to our time frame.

    Args:
        event: (InstanceEvent): The event object to evaluate
        start (datetime.datetime): Start time (inclusive)

    Returns:
        bool: A boolean regarding whether or not we should inspect the event
            further.

    """
    valid_event = True
    # if the event occurred outside of our specified period (ie. before start)
    # we should only inspect it if it was a power on event
    if event.occurred_at < start:
        if event.event_type == InstanceEvent.TYPE.power_off:
            valid_event = False
    return valid_event
