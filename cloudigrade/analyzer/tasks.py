"""Celery tasks for analyzing incoming logs."""
import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from account.models import (AwsAccount,
                            AwsMachineImage,
                            ImageTag,
                            InstanceEvent)
from account.util import save_instance_events, save_machine_images, \
    start_image_inspection, tag_windows
from util import aws
from util.aws import is_instance_windows, rewrap_aws_errors
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)

ec2_instance_event_map = {
    'RunInstances': InstanceEvent.TYPE.power_on,
    'StartInstances': InstanceEvent.TYPE.power_on,
    'StopInstances': InstanceEvent.TYPE.power_off,
    'TerminateInstances': InstanceEvent.TYPE.power_off
}

AWS_OPENSHIFT_TAG = 'cloudigrade-ocp-present'
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
    messages = aws.receive_message_from_queue(queue_url)

    # Parse the SQS messages to get S3 object locations
    for message in messages:
        extracted_messages.extend(aws.extract_sqs_message(message))

    # Grab the object contents from S3
    for extracted_message in extracted_messages:
        bucket = extracted_message['bucket']['name']
        key = extracted_message['object']['key']
        logs.append(aws.get_object_content_from_s3(bucket, key))

    # Parse logs for on/off events
    for log in logs:
        if log:
            instances = _parse_log_for_ec2_instance_events(log)
            _parse_log_for_ami_tag_events(log)

    if instances:
        _save_results(instances)
        logger.debug(_('Saved instances and/or events to the DB.'))
    else:
        logger.debug(_('No instances or events to save to the DB.'))

    aws.delete_message_from_queue(queue_url, messages)


def _parse_log_for_ec2_instance_events(log):
    """
    Parse S3 log for EC2 on/off events.

    Args:
        log (str): The string contents of the log file.

    Returns:
        list(tuple): List of instance data seen in log.
        list(tuple): List of instance_event data seen in log.

    """
    instances = {}
    log = json.loads(log)

    # Each record is a single API call, but each call can
    # be made against multiple EC2 instances
    for record in log.get('Records', []):
        if not _is_valid_event(record, ec2_instance_event_map.keys()):
            continue

        account_id = record.get('userIdentity', {}).get('accountId')
        account = AwsAccount.objects.get(aws_account_id=account_id)
        region = record.get('awsRegion')
        session = aws.get_session(account.account_arn, region)
        event_type = ec2_instance_event_map[record.get('eventName')]
        occurred_at = record.get('eventTime')
        ec2_info = record.get('responseElements', {})\
            .get('instancesSet', {})\
            .get('items', [])

        # Collect the EC2 instances the API was called on
        for item in ec2_info:
            instance_id = item.get('instanceId')
            instance = aws.get_ec2_instance(session, instance_id)
            instances[instance_id] = {
                'account_id': account_id,
                'instance_details': instance,
                'region': region
            }

        for __, data in instances.items():
            event = {
                'subnet': data['instance_details'].subnet_id,
                'ec2_ami_id': data['instance_details'].image_id,
                'instance_type': data['instance_details'].instance_type,
                'event_type': event_type,
                'occurred_at': occurred_at
            }

            if data.get('events'):
                data['events'].append(event)
            else:
                data['events'] = [event]

    return dict(instances)


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
            .get('items', []) if tag.get('key', '') == AWS_OPENSHIFT_TAG]

        if ami_list and tag_list:
            openshift_tag = ImageTag.objects.filter(
                description=OPENSHIFT_MODEL_TAG).first()
            for ami_id in ami_list:
                ami = AwsMachineImage.objects.filter(ec2_ami_id=ami_id).first()
                if ami:
                    if add_openshift_tag:
                        logger.info(
                            _('Adding openshift tag to AMI {}').format(
                                ami_id))
                        ami.tags.add(openshift_tag)
                    else:
                        logger.info(_(
                            'Removing openshift tag from AMI {}').format(
                                ami_id))
                        ami.tags.remove(openshift_tag)
                    ami.save()
                else:
                    logger.info(
                        'Tag create/delete event referenced AMI {}, '
                        'but no AMI with this ID is known to cloudigrade.')


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
def _save_results(instances):
    """
    Save instances and events to the DB.

    Args:
        instances (dict): Of instance and event information to be persisted.

    """
    accounts = {}
    for instance_id, data in instances.items():
        account_id = data['account_id']
        if account_id not in accounts:
            accounts[account_id] = \
                AwsAccount.objects.get(aws_account_id=account_id)
        account = accounts[account_id]

        image, created = save_machine_images(
            account, data['instance_details'].image_id)
        save_instance_events(
            account,
            data['instance_details'],
            data['region'],
            data['events']
        )
        if is_instance_windows(data['instance_details']):
            image = tag_windows(image)
        if image.status is not image.INSPECTED and created:
            start_image_inspection(
                account.account_arn, image.ec2_ami_id, data['region'])
