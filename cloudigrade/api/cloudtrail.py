"""Functions for parsing relevant data from CloudTrail messages."""
import itertools
import logging

from django.utils.translation import gettext as _

from api.models import InstanceEvent
from util import aws

logger = logging.getLogger(__name__)


ec2_instance_event_map = {
    "RunInstances": InstanceEvent.TYPE.power_on,
    "StartInstance": InstanceEvent.TYPE.power_on,
    "StartInstances": InstanceEvent.TYPE.power_on,
    "StopInstances": InstanceEvent.TYPE.power_off,
    "TerminateInstances": InstanceEvent.TYPE.power_off,
    "TerminateInstanceInAutoScalingGroup": InstanceEvent.TYPE.power_off,
    "ModifyInstanceAttribute": InstanceEvent.TYPE.attribute_change,
}
OPENSHIFT_MODEL_TAG = "openshift"
CREATE_TAG = "CreateTags"
DELETE_TAG = "DeleteTags"
ec2_ami_tag_event_list = [CREATE_TAG, DELETE_TAG]


class CloudTrailInstanceEvent(object):
    """Data structure for holding a Cloud Trail instance-related event."""

    __slots__ = (
        "occurred_at",
        "aws_account_id",
        "region",
        "ec2_instance_id",
        "event_type",
        "instance_type",
        "ec2_ami_id",
        "subnet_id",
    )

    def __init__(self, **kwargs):
        """Initialize a CloudTrailInstanceEvent with arguments."""
        for key, value in kwargs.items():
            setattr(self, key, value)


class CloudTrailImageTagEvent(object):
    """Data structure for holding a Cloud Trail image tag-related event."""

    __slots__ = (
        "occurred_at",
        "aws_account_id",
        "region",
        "ec2_ami_id",
        "tag",
        "exists",
    )

    def __init__(self, **kwargs):
        """Initialize a CloudTrailImageTagEvent with arguments."""
        for key, value in kwargs.items():
            setattr(self, key, value)


def extract_time_account_region(record):
    """
    Extract the CloudTrail Record's eventTime, accountId, and awsRegion.

    Args:
        record (Dict): a single element from a CloudTrail log file Records list

    Returns:
        tuple(str, str, str)

    """
    occurred_at = record["eventTime"]
    account_id = record["userIdentity"]["accountId"]
    region = record["awsRegion"]
    return occurred_at, account_id, region


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

    occurred_at, aws_account_id, region = extract_time_account_region(record)
    event_name = record["eventName"]
    event_type = ec2_instance_event_map[event_name]

    requestParameters = record.get("requestParameters", {})

    # Weird! 'instanceType' definition differs based on the event name...
    # This is how 'instanceType' appears for 'RunInstances':
    instance_type = requestParameters.get("instanceType")
    if instance_type is not None and not isinstance(instance_type, str):
        # This is how 'instanceType' appears for 'ModifyInstanceAttribute':
        instance_type = requestParameters.get("instanceType", {}).get("value")

    if (
        event_name in ["ModifyInstanceAttribute", "RunInstances"]
        and instance_type is None
    ):
        logger.info(
            _("Missing instanceType in %(event_name)s record: %(record)s"),
            {"event_name": event_name, "record": record},
        )
        return []

    ec2_instance_ami_ids = set(
        [
            (
                instance_item["instanceId"],
                instance_item.get("imageId"),
                instance_item.get("subnetId"),
            )
            for instance_item in record.get("responseElements", {})
            .get("instancesSet", {})
            .get("items", [])
            if "instanceId" in instance_item
        ]
    )

    request_instance_id = requestParameters.get("instanceId")
    if request_instance_id is not None and request_instance_id not in (
        instance_id for instance_id, __ in ec2_instance_ami_ids
    ):
        # We only see the instanceId in requestParameters for
        # ModifyInstanceAttribute, and that operation can't change the image.
        # Only if there are no other records for this instance, then we may add
        # it to the set with *no* image ID.
        ec2_instance_ami_ids.add((request_instance_id, None, None))

    return [
        CloudTrailInstanceEvent(
            occurred_at=occurred_at,
            aws_account_id=aws_account_id,
            region=region,
            ec2_instance_id=ec2_instance_id,
            event_type=event_type,
            instance_type=instance_type,
            ec2_ami_id=ec2_ami_id,
            subnet_id=subnet_id,
        )
        for ec2_instance_id, ec2_ami_id, subnet_id in ec2_instance_ami_ids
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

    occurred_at, aws_account_id, region = extract_time_account_region(record)
    exists = record.get("eventName") == CREATE_TAG
    ec2_ami_ids = set(
        [
            resource_item["resourceId"]
            for resource_item in record.get("requestParameters", {})
            .get("resourcesSet", {})
            .get("items", [])
            if resource_item.get("resourceId", "").startswith("ami-")
        ]
    )
    tags = [
        tag_item["key"]
        for tag_item in record.get("requestParameters", {})
        .get("tagSet", {})
        .get("items", [])
        if tag_item.get("key", "") == aws.OPENSHIFT_TAG
    ]

    return [
        CloudTrailImageTagEvent(
            occurred_at=occurred_at,
            aws_account_id=aws_account_id,
            region=region,
            ec2_ami_id=ec2_ami_id,
            tag=tag,
            exists=exists,
        )
        for ec2_ami_id, tag in itertools.product(ec2_ami_ids, tags)
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
    if record.get("eventSource") != "ec2.amazonaws.com":
        return False
    # Currently we do not store events that have an error
    elif record.get("errorCode"):
        return False
    elif record.get("eventName") not in valid_events:
        return False
    else:
        return True
