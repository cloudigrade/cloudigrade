"""Celery tasks for analyzing incoming logs."""
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from account.models import AwsAccount, AwsMachineImage, InstanceEvent
from account.util import (save_instance_events,
                          save_new_aws_machine_image,
                          start_image_inspection)
from util import aws
from util.aws import is_instance_windows, rewrap_aws_errors
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)

ec2_instance_event_map = {
    'RunInstances': InstanceEvent.TYPE.power_on,
    'StartInstance': InstanceEvent.TYPE.power_on,
    'StartInstances': InstanceEvent.TYPE.power_on,
    'StopInstances': InstanceEvent.TYPE.power_off,
    'TerminateInstances': InstanceEvent.TYPE.power_off,
    'TerminateInstanceInAutoScalingGroup': InstanceEvent.TYPE.power_off
}

OPENSHIFT_MODEL_TAG = 'openshift'
CREATE_TAG = 'CreateTags'
DELETE_TAG = 'DeleteTags'

ec2_ami_tag_event_list = [
    CREATE_TAG,
    DELETE_TAG
]


@retriable_shared_task
@rewrap_aws_errors
def analyze_log():
    """Read SQS Queue for log location, and parse log for events."""
    queue_url = settings.CLOUDTRAIL_EVENT_URL

    logs = []
    extracted_messages = []
    instances = {}

    # Get messages off of an SQS queue
    messages = aws.receive_messages_from_queue(queue_url)

    # Parse the SQS messages to get S3 object locations
    for message in messages:
        extracted_messages.extend(aws.extract_sqs_message(message))

    # Grab the object contents from S3
    for extracted_message in extracted_messages:
        bucket = extracted_message['bucket']['name']
        key = extracted_message['object']['key']
        logs.append((aws.get_object_content_from_s3(bucket, key), bucket, key))

    # Parse logs for on/off events
    for log, bucket, key in logs:
        if log:
            # FIXME: When it comes time to fix up logging for production,
            # this should get revisted.
            logger.info(
                _('Parsing log from s3 bucket {0} with path {1}.').format(
                    bucket, key))
            instances, described_images = \
                _parse_log_for_ec2_instance_events(log)
            _parse_log_for_ami_tag_events(log)

    if instances:
        _save_results(instances, described_images)
        logger.debug(_('Saved instances and/or events to the DB.'))
    else:
        logger.debug(_('No instances or events to save to the DB.'))

    aws.delete_messages_from_queue(queue_url, messages)


def _parse_log_for_ec2_instance_events(log):
    """
    Parse S3 log for EC2 on/off events.

    Args:
        log (str): The string contents of the log file.

    Returns:
        list(tuple): Dict of instance data seen in log and list of images data

    """
    instances = {}
    described_images = {}
    log = json.loads(log)

    # Each record is a single API call, but each call can
    # be made against multiple EC2 instances
    for record in log.get('Records', []):
        if not _is_valid_event(record, ec2_instance_event_map.keys()):
            continue

        account_id = record.get('userIdentity', {}).get('accountId')
        account = AwsAccount.objects.get(aws_account_id=account_id)
        region = record.get('awsRegion')
        event_type = ec2_instance_event_map[record.get('eventName')]
        occurred_at = record.get('eventTime')
        ec2_info = record.get('responseElements', {})\
            .get('instancesSet', {})\
            .get('items', [])

        # Collect the EC2 instances the API was called on
        session = aws.get_session(account.account_arn, region)
        new_instance_ids = set([item['instanceId'] for item in ec2_info])
        new_instance_ids -= set(instances.keys())
        for instance_id in new_instance_ids:
            instance = aws.get_ec2_instance(session, instance_id)
            instances[instance_id] = {
                'account_id': account_id,
                'instance_details': instance,
                'region': region,
                'events': []
            }
            # Describe each found image only once.
            if instance.image_id not in described_images:
                described_images[instance.image_id] = aws.describe_image(
                    session, instance.image_id, region
                )

        # Build the list of events for each instance
        for item in ec2_info:
            instance_id = item['instanceId']
            instance_details = instances[instance_id]['instance_details']
            event = {
                'subnet': instance_details.subnet_id,
                'ec2_ami_id': instance_details.image_id,
                'instance_type': instance_details.instance_type,
                'event_type': event_type,
                'occurred_at': occurred_at
            }
            instances[instance_id]['events'].append(event)

    return instances, described_images


def _parse_log_for_ami_tag_events(log):
    """
    Parse S3 log for AMI tag create/delete events.

    Args:
        log (str): The JSON string contents of the log file.

    Returns:
        None: Images are updated if needed

    """
    log = json.loads(log)

    for record in log.get('Records', []):
        if not _is_valid_event(record, ec2_ami_tag_event_list):
            continue

        add_openshift_tag = record.get('eventName') == CREATE_TAG
        ami_list = [ami.get('resourceId') for ami in record.get(
            'requestParameters', {})
            .get('resourcesSet', {})
            .get('items', []) if ami.get('resourceId', '').startswith('ami-')]

        tag_list = [tag for tag in record.get(
            'requestParameters', {})
            .get('tagSet', {})
            .get('items', []) if tag.get('key', '') == aws.OPENSHIFT_TAG]

        if ami_list and tag_list:
            for ami_id in ami_list:
                try:
                    ami = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
                except AwsMachineImage.DoesNotExist:
                    logger.warning(_(
                        'Tag create/delete event referenced AMI {0}, '
                        'but no AMI with this ID is known to cloudigrade.'
                    ).format(ami_id))
                    continue

                logger.info(_('Setting "openshift_detected" property with'
                              'value "{0}".').format(add_openshift_tag))
                ami.openshift_detected = add_openshift_tag
                ami.save()


def _is_valid_event(record, valid_events):
    """
    Determine if a log event is an EC2 on/off event.

    Args:
        record (dict): The log record record.
        valid_events (list): Events considered to be on/off.

    Returns:
        bool: Whether the record contains an on/off event

    """
    if record.get('eventSource') != 'ec2.amazonaws.com':
        return False
    # Currently we do not store events that have an error
    elif record.get('errorCode'):
        return False
    # Currently we only want power on/power off EC2 events
    elif record.get('eventName') not in valid_events:
        return False
    else:
        return True


@transaction.atomic
def _save_results(instances, described_images):
    """
    Save instances and events to the DB.

    Args:
        instances (list[dict]): instance and event information to be persisted.
        described_images (list[dict]): image information to be persisted.

    """
    # Step 0: Log some basic information about what we're saving.
    log_prefix = 'analyzer'
    instance_ids = set(instances.keys())
    logger.info(_('{prefix}: all EC2 Instance IDs found: {instance_ids}')
                .format(prefix=log_prefix, instance_ids=instance_ids))
    ami_ids = set(described_images.keys())
    logger.info(_('{prefix}: all AMI IDs found: {ami_ids}')
                .format(prefix=log_prefix, ami_ids=ami_ids))

    # Step 1: Which images have Windows based on the instance platform?
    windows_ami_ids = {
        instance['instance_details'].image_id
        for instance in instances.values()
        if is_instance_windows(instance['instance_details'])
    }
    logger.info(_('{prefix}: Windows AMI IDs found: {windows_ami_ids}')
                .format(prefix=log_prefix, windows_ami_ids=windows_ami_ids))

    # Step 2: Determine which images we actually need to save.
    known_ami_ids = {
        image.ec2_ami_id for image in
        AwsMachineImage.objects.filter(
            ec2_ami_id__in=list(described_images.keys())
        )
    }

    # Step 3: Save only the new images.
    new_images = {}
    for ami_id, described_image in described_images.items():
        if ami_id in known_ami_ids:
            logger.info(_('{prefix}: Skipping known AMI ID: {ami_id}')
                        .format(prefix=log_prefix, ami_id=ami_id))
            continue

        owner_id = Decimal(described_image['OwnerId'])
        name = described_image['Name']
        windows = ami_id in windows_ami_ids
        openshift = len([
            tag for tag in described_image.get('Tags', [])
            if tag.get('Key') == aws.OPENSHIFT_TAG
        ]) > 0

        logger.info(_('{prefix}: Saving new AMI ID: {ami_id}')
                    .format(prefix=log_prefix, ami_id=ami_id))
        image, new = save_new_aws_machine_image(
            ami_id, name, owner_id, openshift, windows)
        if new and image.status is not image.INSPECTED:
            new_images[ami_id] = image

    # Step 4: Save instances and their events.
    accounts = {}
    for instance_id, data in instances.items():
        account_id = data['account_id']
        if account_id not in accounts:
            accounts[account_id] = \
                AwsAccount.objects.get(aws_account_id=account_id)
        account = accounts[account_id]

        ami_id = data['instance_details'].image_id
        save_instance_events(
            account,
            data['instance_details'],
            data['region'],
            data['events']
        )
        if ami_id in new_images:
            start_image_inspection(account.account_arn, ami_id, data['region'])
