"""Celery tasks for analyzing incoming logs."""
import collections
import itertools
import json
import logging
import urllib.request
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from account.models import (AwsAccount, AwsEC2InstanceDefinitions,
                            AwsMachineImage, InstanceEvent)
from account.util import (save_instance_events,
                          save_new_aws_machine_image,
                          start_image_inspection)
from util import aws
from util.aws import is_instance_windows, rewrap_aws_errors
from util.celery import retriable_shared_task
from util.exceptions import (CloudTrailLogAnalysisMissingData,
                             EC2InstanceDefinitionNotFound)

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

CloudTrailInstanceEvent = collections.namedtuple(
    'CloudTrailInstanceEvent',
    ['occurred_at', 'account_id', 'region', 'instance_id', 'event_type']
)

CloudTrailImageTagEvent = collections.namedtuple(
    'CloudTrailImageTagEvent',
    ['occurred_at', 'account_id', 'region', 'image_id', 'tag', 'exists']
)


@shared_task
@rewrap_aws_errors
def analyze_log():
    """Read SQS Queue for log location, and parse log for events."""
    queue_url = settings.CLOUDTRAIL_EVENT_URL
    successes, failures = [], []
    for message in aws.yield_messages_from_queue(queue_url):
        success = False
        try:
            success = _process_cloudtrail_message(message)
        except AwsAccount.DoesNotExist:
            logger.warning(
                _(
                    'Encountered message {0} for nonexistent account; '
                    'deleting message from queue.'
                ).format(message.message_id)
            )
            logger.info(
                _('Deleted message body: {0}').format(message.body)
            )
            aws.delete_messages_from_queue(queue_url, [message])
            continue
        except Exception as e:
            logger.exception(_(
                'Unexpected error in log processing: {0}'
            ).format(e))
        if success:
            logger.info(_(
                'Successfully processed message id {0}; deleting from queue.'
            ).format(message.message_id))
            aws.delete_messages_from_queue(queue_url, [message])
            successes.append(message)
        else:
            logger.error(_(
                'Failed to process message id {0}; leaving on queue.'
            ).format(message.message_id))
            logger.debug(_(
                'Failed message body is: {0}'
            ).format(message.body))
            failures.append(message)
    return successes, failures


def _process_cloudtrail_message(message):
    """
    Process a single CloudTrail log update's SQS message.

    Args:
        message (Message): the SQS Message object to process

    Returns:
        bool: True only if message processing completed without error.

    """
    logs = []
    extracted_messages = aws.extract_sqs_message(message)

    # Get the S3 objects referenced by the SQS messages
    for extracted_message in extracted_messages:
        bucket = extracted_message['bucket']['name']
        key = extracted_message['object']['key']
        raw_content = aws.get_object_content_from_s3(bucket, key)
        content = json.loads(raw_content)
        logs.append((content, bucket, key))
        logger.debug(_(
            'Read CloudTrail log file from bucket {0} object key {1}'
        ).format(bucket, key))

    # Extract actionable details from each of the S3 log files
    instance_events = []
    ami_tag_events = []
    for content, bucket, key in logs:
        for record in content.get('Records', []):
            instance_events.extend(_parse_log_for_ec2_instance_events(record))
            ami_tag_events.extend(_parse_log_for_ami_tag_events(record))

    # Get supporting details from AWS so we can save our models.
    aws_instances, described_images = _get_aws_data_for_trail_events(
        instance_events, ami_tag_events
    )

    try:
        # Save the results
        new_images = _save_results(instance_events,
                                   ami_tag_events,
                                   aws_instances,
                                   described_images)
        # Starting image inspection MUST come after all other database writes
        # so that we are confident the atomic transaction will complete.
        for image_id, image_data in described_images.items():
            if image_id in new_images:
                start_image_inspection(
                    image_data['found_in_account_arn'],
                    image_id,
                    image_data['found_in_region']
                )

        logger.debug(_('Saved instances and/or events to the DB.'))
        return True
    except:  # noqa: E722 because we don't know what could go wrong yet.
        logger.exception(_(
            'Failed to save instances and/or events to the DB. '
            'Instance events: {0} AMI tag events: {1}'
        ).format(instance_events, ami_tag_events))
        return False


def _get_aws_data_for_trail_events(instance_events, ami_tag_events):  # noqa: C901, E501
    """
    Get additional AWS data so we can process the given event data.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found ami tag events

    Returns:
        tuple(dict, dict): Dict of AWS Instance objects keyed by instance ID
            and dict of AWS describe_image dicts keyed by image ID. These
            should provide enough information to save appropriate DB updates.

    """
    seen_aws_instances = {}
    new_described_images = {}

    known_image_ids = set()  # growing set of IDs so we don't repeat lookups

    # Iterate through the instance events grouped by account and region in
    # order to minimize the number of sessions and AWS API calls.
    for (account_id, region), _instance_events in itertools.groupby(
            instance_events, key=lambda e: (e.account_id, e.region)):
        account = AwsAccount.objects.get(aws_account_id=account_id)
        session = aws.get_session(account.account_arn, region)
        seen_image_ids = set()  # set of image IDs seen in this iteration

        # Fetch each instance's latest information from AWS.
        for instance_id in set([e.instance_id for e in _instance_events]):
            instance = aws.get_ec2_instance(session, instance_id)
            seen_aws_instances[instance_id] = instance
            try:
                if instance.image_id not in known_image_ids:
                    seen_image_ids.add(instance.image_id)
            except AttributeError as e:
                relevant_events = [
                    event for event in _instance_events
                    if e.instance_id == instance_id
                ]
                logger.info(_(
                    'Instance {0} has no image_id from AWS. It may have been '
                    'terminated before we processed it. Found in events: {1}.'
                ).format(instance_id, relevant_events))

        if not seen_image_ids:
            continue

        # Do we already have the image in our database?
        known_image_ids = known_image_ids.union([
            image.ec2_ami_id for image in
            AwsMachineImage.objects.filter(ec2_ami_id__in=seen_image_ids)
        ])
        new_image_ids = seen_image_ids - known_image_ids

        if not new_image_ids:
            continue

        # TODO What happens if an image has been deregistered by now?
        described_images = aws.describe_images(session, new_image_ids, region)
        for image_data in described_images:
            # These bits of data will be useful in post-processing:
            image_data['found_in_account_arn'] = account.account_arn
            image_data['found_in_region'] = region
            image_id = image_data['ImageId']
            new_described_images[image_id] = image_data
            known_image_ids.add(image_id)

    # Iterate through the AMI tag events grouped by account and region in
    # order to minimize the number of sessions and AWS API calls.
    for (account_id, region), _ami_tag_events in itertools.groupby(
            ami_tag_events, key=lambda e: (e.account_id, e.region)):
        tag_image_ids = set([
            ami_tag_event.image_id
            for ami_tag_event in _ami_tag_events
        ])
        tag_image_ids -= known_image_ids

        # Do we already have the image in our database?
        known_image_ids = known_image_ids.union([
            image.ec2_ami_id for image in
            AwsMachineImage.objects.filter(ec2_ami_id__in=tag_image_ids)
        ])
        tag_image_ids -= known_image_ids

        if not tag_image_ids:
            continue

        account = AwsAccount.objects.get(aws_account_id=account_id)
        session = aws.get_session(account.account_arn, region)

        # TODO What happens if an image has been deregistered by now?
        described_images = aws.describe_images(session, tag_image_ids, region)
        for image_data in described_images:
            # These bits of data will be useful in post-processing:
            image_data['found_in_account_arn'] = account.account_arn
            image_data['found_in_region'] = region
            image_id = image_data['ImageId']
            new_described_images[image_id] = image_data
            known_image_ids.add(image_id)

    return seen_aws_instances, new_described_images


def _parse_log_for_ec2_instance_events(record):
    """
    Parse S3 log for EC2 on/off events.

    Args:
        record (Dict): a single record from a CloudTrail log file Records list

    Returns:
        list(CloudTrailInstanceEvent): Information about the found events

    """
    if not _is_valid_event(record, ec2_instance_event_map.keys()):
        return []

    occurred_at = record['eventTime']
    account_id = record['userIdentity']['accountId']
    region = record['awsRegion']

    event_type = ec2_instance_event_map[record.get('eventName')]

    instance_ids = set([
        instance_item['instanceId']
        for instance_item in record.get('responseElements', {})
                                   .get('instancesSet', {})
                                   .get('items', [])
        if 'instanceId' in instance_item
    ])

    return [
        CloudTrailInstanceEvent(
            occurred_at=occurred_at,
            account_id=account_id,
            region=region,
            instance_id=instance_id,
            event_type=event_type,
        )
        for instance_id in instance_ids
    ]


def _parse_log_for_ami_tag_events(record):
    """
    Parse S3 log for AMI tag create/delete events.

    Args:
        record (Dict): a single record from a CloudTrail log file Records list

    Returns:
        list(CloudTrailImageTagEvent): Information about the found AMI tags

    """
    if not _is_valid_event(record, ec2_ami_tag_event_list):
        return []

    occurred_at = record['eventTime']
    account_id = record['userIdentity']['accountId']
    region = record['awsRegion']

    exists = record.get('eventName') == CREATE_TAG
    image_ids = set([
        resource_item['resourceId']
        for resource_item in record.get('requestParameters', {})
                                   .get('resourcesSet', {})
                                   .get('items', [])
        if resource_item.get('resourceId', '').startswith('ami-')
    ])
    tags = [
        tag_item['key']
        for tag_item in record.get('requestParameters', {})
                              .get('tagSet', {})
                              .get('items', [])
        if tag_item.get('key', '') == aws.OPENSHIFT_TAG
    ]

    return [
        CloudTrailImageTagEvent(
            occurred_at,
            account_id,
            region,
            image_id,
            tag,
            exists,
        )
        for image_id, tag in itertools.product(image_ids, tags)
    ]


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


def _sanity_check_cloudtrail_findings(instance_events, ami_tag_events,
                                      aws_instances, described_images):
    """
    Sanity check the CloudTrail findings before attempting to save them.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found ami tag events
        aws_instances (dict): AWS Instance objects keyed by instance ID
        described_images (dict): AWS describe_image dicts keyed by image ID
    """
    for instance_event in instance_events:
        if instance_event.instance_id not in aws_instances:
            raise CloudTrailLogAnalysisMissingData(_(
                'Missing instance data for {0}'
            ).format(instance_event))
        try:
            image_id = aws_instances[instance_event.instance_id].image_id
        except AttributeError:
            logger.info(_(
                'Instance event {0} has no image_id from AWS. It may have '
                'been terminated before we processed it.'
            ).format(instance_event))
            continue
        if image_id not in described_images and \
                not AwsMachineImage.objects.filter(
                    ec2_ami_id=image_id).exists():
            raise CloudTrailLogAnalysisMissingData(_(
                'Missing image data for {0}'
            ).format(instance_event))
    for ami_tag_event in ami_tag_events:
        image_id = ami_tag_event.image_id
        if image_id not in described_images and \
                not AwsMachineImage.objects.filter(
                    ec2_ami_id=image_id).exists():
            raise CloudTrailLogAnalysisMissingData(_(
                'Missing image data for {0}'
            ).format(ami_tag_event))


@transaction.atomic
def _save_results(instance_events, ami_tag_events, aws_instances,
                  described_images):
    """
    Save new images and instances events found via CloudTrail to the DB.

    Note:
        Nothing should be reaching out to AWS APIs in this function! We should
        have all the necessary information already, and this function saves all
        of it atomically in a single transaction.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found ami tag events
        aws_instances (dict): AWS Instance objects keyed by instance ID
        described_images (dict): AWS describe_image dicts keyed by image ID

    Returns:
        dict: Only the new images that were created in the process.

    """
    _sanity_check_cloudtrail_findings(instance_events,
                                      ami_tag_events,
                                      aws_instances,
                                      described_images)

    # Log some basic information about what we're saving.
    log_prefix = 'analyzer'
    instance_ids = set(aws_instances.keys())
    logger.info(_('{prefix}: all EC2 Instance IDs found: {instance_ids}')
                .format(prefix=log_prefix, instance_ids=instance_ids))
    ami_ids = set(described_images.keys())
    logger.info(_('{prefix}: new AMI IDs found: {ami_ids}')
                .format(prefix=log_prefix, ami_ids=ami_ids))

    # Which images have Windows based on the instance platform?
    windows_ami_ids = {
        instance.image_id
        for instance in aws_instances.values()
        if is_instance_windows(instance)
    }
    logger.info(_('{prefix}: Windows AMI IDs found: {windows_ami_ids}')
                .format(prefix=log_prefix, windows_ami_ids=windows_ami_ids))

    # Which images need tag state changes?
    ocp_tagged_ami_ids = set()
    ocp_untagged_ami_ids = set()
    for image_id, events in itertools.groupby(
            ami_tag_events, key=lambda e: e.image_id):
        # Get only the most recent event for each image
        latest_event = sorted(events, key=lambda e: e.occurred_at)[-1]
        # IMPORTANT NOTE: This assumes all tags are the OCP tag!
        # This will need to change if we ever support other ami tags.
        if latest_event.exists:
            ocp_tagged_ami_ids.add(image_id)
        else:
            ocp_untagged_ami_ids.add(image_id)

    # Which images do we actually need to create?
    known_ami_ids = {
        image.ec2_ami_id for image in
        AwsMachineImage.objects.filter(
            ec2_ami_id__in=list(described_images.keys())
        )
    }

    # Create only the new images.
    new_images = {}
    for ami_id, described_image in described_images.items():
        if ami_id in known_ami_ids:
            logger.info(_('{prefix}: Skipping known AMI ID: {ami_id}')
                        .format(prefix=log_prefix, ami_id=ami_id))
            continue

        owner_id = Decimal(described_image['OwnerId'])
        name = described_image['Name']
        windows = ami_id in windows_ami_ids
        openshift = ami_id in ocp_tagged_ami_ids

        logger.info(_('{prefix}: Saving new AMI ID: {ami_id}')
                    .format(prefix=log_prefix, ami_id=ami_id))
        image, new = save_new_aws_machine_image(
            ami_id, name, owner_id, openshift, windows)
        if new and image.status is not image.INSPECTED:
            new_images[ami_id] = image

    # Update images with openshift tag changes.
    if ocp_tagged_ami_ids:
        AwsMachineImage.objects.filter(
            ec2_ami_id__in=ocp_tagged_ami_ids
        ).update(openshift_detected=True)
    if ocp_untagged_ami_ids:
        AwsMachineImage.objects.filter(
            ec2_ami_id__in=ocp_untagged_ami_ids
        ).update(openshift_detected=False)

    # Save instances and their events.
    for (instance_id, region, account_id), _events in itertools.groupby(
            instance_events, key=lambda e: (e.instance_id, e.region,
                                            e.account_id)):
        account = AwsAccount.objects.get(aws_account_id=account_id)
        aws_instance = aws_instances[instance_id]

        # Build a list of event data
        events = [
            {
                'subnet': getattr(aws_instance, 'subnet_id', None),
                'ec2_ami_id': getattr(aws_instance, 'image_id', None),
                'instance_type': getattr(aws_instance, 'instance_type', None),
                'event_type': instance_event.event_type,
                'occurred_at': instance_event.occurred_at
            }
            for instance_event in _events
        ]

        save_instance_events(
            account,
            aws_instance,
            region,
            events
        )

    return new_images


@retriable_shared_task
def repopulate_ec2_instance_mapping():
    """
    Scan AWS pricing endpoint and update the EC2 instancetype lookup table.

    See: https://aws.amazon.com/blogs/aws/new-aws-price-list-api/

    Returns:
        None: Run as an asynchronous Celery task.

    """
    logger.info(_('Getting AWS EC2 instance type information.'))

    with urllib.request.urlopen(settings.AWS_PRICING_URL) as response:
        logger.info(_('Parsing JSON for AWS EC2 instance type information.'))
        ec2_offers = json.load(response)

    logger.info(_('Successfully read AWS EC2 instance type information.'))
    instances = {}
    for sku, data in ec2_offers['products'].items():
        if data['productFamily'] != 'Compute Instance':
            # skip anything that's not an EC2 Instance
            continue
        instances[data['attributes']['instanceType']] = data['attributes']

    logger.info(_('Found {} instance types').format(len(instances.items())))
    for instance_type, instance_metadata in instances.items():

        try:
            # memory comes in formatted like: 1,952.00 GiB
            memory = float(
                instance_metadata.get('memory', 0)[:-4].replace(',', '')
            )
            vcpu = int(instance_metadata.get('vcpu', 0))

            AwsEC2InstanceDefinitions.objects.update_or_create(
                instance_type=instance_type,
                memory=memory,
                vcpu=vcpu
            )
            logger.info(_('Saved instance type {}').format(instance_type))
        except ValueError:
            logger.error(
                _(
                    'Could not convert memory {} to float.'
                ).format(instance_metadata.get('memory', 0))
            )
    logger.info('Finished saving AWS EC2 instance type information.')


def _get_instance_definition(instance_type):
    """
    Get information about an AWS EC2 instance (e.g. memory, vcpu).

    If the instance_type does not exist in this table, kick off a
    new task to repopulate this table from an AWS pricing endpoint.

    Args:
        instance_type (str): Lookup the definition for this instance_type

    Returns:
        instance (django.models.AwsEC2InstanceDefinitions): model
        corresponding to the given instance_type.

    Raises:
        EC2InstanceDefinitionNotFound: If instance_type is not found

    """
    try:
        model = AwsEC2InstanceDefinitions.objects.get(
            instance_type=instance_type
        )
        return model

    except AwsEC2InstanceDefinitions.DoesNotExist:
        logger.info(
            _(
                'Could not find instance type {} in mapping table, '
                'repopulating table with latest amazon information.'
            ).format(instance_type)
        )
        repopulate_ec2_instance_mapping.delay()
        raise EC2InstanceDefinitionNotFound
