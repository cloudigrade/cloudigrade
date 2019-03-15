"""Functions for parsing relevant data from CloudTrail messages."""
import collections
import itertools
import logging

from django.utils.translation import gettext as _

from account.models import InstanceEvent
from util import aws

logger = logging.getLogger(__name__)


ec2_instance_event_map = {
    'RunInstances': InstanceEvent.TYPE.power_on,
    'StartInstance': InstanceEvent.TYPE.power_on,
    'StartInstances': InstanceEvent.TYPE.power_on,
    'StopInstances': InstanceEvent.TYPE.power_off,
    'TerminateInstances': InstanceEvent.TYPE.power_off,
    'TerminateInstanceInAutoScalingGroup': InstanceEvent.TYPE.power_off,
    'ModifyInstanceAttribute': InstanceEvent.TYPE.attribute_change,
}
OPENSHIFT_MODEL_TAG = 'openshift'
CREATE_TAG = 'CreateTags'
DELETE_TAG = 'DeleteTags'
ec2_ami_tag_event_list = [CREATE_TAG, DELETE_TAG]
CloudTrailInstanceEvent = collections.namedtuple(
    'CloudTrailInstanceEvent',
    [
        'occurred_at',
        'account_id',
        'region',
        'instance_id',
        'event_type',
        'instance_type',
    ],
)
CloudTrailImageTagEvent = collections.namedtuple(
    'CloudTrailImageTagEvent',
    ['occurred_at', 'account_id', 'region', 'image_id', 'tag', 'exists'],
)


def extract_ec2_instance_events(record):
    """
    Parse CloudTrail Record and extract EC2 instance on/off/change events.

    Args:
        record (Dict): a single element from a CloudTrail log file Records list

    Returns:
        list(CloudTrailInstanceEvent): Information about the found events

    """
    if not _is_valid_event(record, ec2_instance_event_map.keys()):
        return []

    occurred_at = record['eventTime']
    account_id = record['userIdentity']['accountId']
    region = record['awsRegion']

    event_type = ec2_instance_event_map[record.get('eventName')]

    instance_type = None
    if 'attribute_change' in event_type:
        try:
            instance_type = \
                record['requestParameters']['instanceType']['value']
            instance_ids = [record['requestParameters']['instanceId']]
        except KeyError:
            logger.debug(_('Did not find instanceType in record: %s'), record)
            return []
    else:
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
            instance_type=instance_type,
        )
        for instance_id in instance_ids
    ]


def extract_ami_tag_events(record):
    """
    Parse CloudTrail Record and extract AMI tag create/delete events.

    Args:
        record (Dict): a single element from a CloudTrail log file Records list

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
            occurred_at, account_id, region, image_id, tag, exists
        )
        for image_id, tag in itertools.product(image_ids, tags)
    ]


def _is_valid_event(record, valid_events):
    """
    Determine if a log event is valid and relevant for our analysis.

    Args:
        record (dict): The log record record.
        valid_events (list): Event types we may analyze.

    Returns:
        bool: Whether the record is valid and relevant for our analysis.

    """
    if record.get('eventSource') != 'ec2.amazonaws.com':
        return False
    # Currently we do not store events that have an error
    elif record.get('errorCode'):
        return False
    elif record.get('eventName') not in valid_events:
        return False
    else:
        return True
