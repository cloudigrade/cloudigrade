"""Functions for parsing relevant data from CloudTrail messages."""
import itertools
import logging

from dateutil.parser import parse
from django.utils.translation import gettext as _

from api.clouds.aws.models import AwsCloudAccount
from api.models import InstanceEvent
from util import OPENSHIFT_TAG, RHEL_TAG

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

    if not _is_relevant_event(occurred_at, aws_account_id, "EC2"):
        return []

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

    if not _is_relevant_event(occurred_at, aws_account_id, "AMI"):
        return []

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
        if tag_item.get("key", "") in (OPENSHIFT_TAG, RHEL_TAG)
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
    Determine if a log event is valid for our analysis.

    Args:
        record (dict): The log record record.
        valid_events (list): Event types we may analyze.

    Returns:
        bool: Whether the record is valid for our analysis.

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


def _is_relevant_event(occurred_at, aws_account_id, event_type):
    """
    Determine if a log event is relevant for our analysis.

    Args:
        occurred_at (str): the time the event occurred, ISO-8601 formatted
        aws_account_id (str): the AWS account ID from the event
        event_type (str): general description of event type for logging purposes

    Returns:
        bool: Whether the record is relevant for our analysis.

    """
    cloud_account = _get_cloud_account_for_aws_account_id(aws_account_id)
    if not cloud_account:
        logger.info(
            _(
                "Skipping CloudTrail record %(event_type)s event extraction for AWS "
                "account ID %(aws_account_id)s because a matching CloudAccount does "
                "not exist."
            ),
            {"event_type": event_type, "aws_account_id": aws_account_id},
        )
        return False
    if not cloud_account.is_enabled:
        logger.info(
            _(
                "Skipping CloudTrail record %(event_type)s event extraction for AWS "
                "account ID %(aws_account_id)s because CloudAccount "
                "%(cloud_account_id)s is not enabled."
            ),
            {
                "event_type": event_type,
                "aws_account_id": aws_account_id,
                "cloud_account_id": cloud_account.id,
            },
        )
        return False
    if cloud_account.platform_application_is_paused:
        logger.info(
            _(
                "Skipping CloudTrail record %(event_type)s event extraction for AWS "
                "account ID %(aws_account_id)s because CloudAccount "
                "%(cloud_account_id)s is paused."
            ),
            {
                "event_type": event_type,
                "aws_account_id": aws_account_id,
                "cloud_account_id": cloud_account.id,
            },
        )
        return False
    if cloud_account.enabled_at and cloud_account.enabled_at > parse(occurred_at):
        logger.info(
            _(
                "Skipping CloudTrail record %(event_type)s event extraction for AWS "
                "account ID %(aws_account_id)s because the event occurred "
                "(%(occurred_at)s) before the CloudAccount was enabled %(enabled_at)s)."
            ),
            {
                "event_type": event_type,
                "aws_account_id": aws_account_id,
                "occurred_at": occurred_at,
                "enabled_at": cloud_account.enabled_at,
            },
        )
        return False
    return True


def _get_cloud_account_for_aws_account_id(aws_account_id):
    """
    Get the CloudAccount for the given AWS account ID.

    Note:
        If we ever support tracking multiple ARNs for the same AWS account ID,
        this helper function will need to change how it queries for objects.

    Args:
        aws_account_id (str): the AWS account ID

    Returns:
        CloudAccount if a match is found, else None.

    """
    aws_cloud_account = AwsCloudAccount.objects.filter(
        aws_account_id=aws_account_id
    ).first()
    if not aws_cloud_account:
        return None
    cloud_account = aws_cloud_account.cloud_account.get()
    return cloud_account
