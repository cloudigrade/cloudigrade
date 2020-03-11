"""Helper utility module to wrap up common AWS CloudTrail operations."""
import logging

from botocore.exceptions import ClientError
from django.conf import settings
from django.utils.translation import gettext as _

from util.exceptions import MaximumNumberOfTrailsExceededException

logger = logging.getLogger(__name__)


def get_cloudtrail_name(aws_account_id):
    """
    Get the standard cloudigrade-formatted CloudTrail name.

    Args:
        aws_account_id (str): The AWS account ID.

    Returns:
        str the standard cloudigrade-formatted CloudTrail name for the given account ID.
    """
    return "{0}{1}".format(settings.CLOUDTRAIL_NAME_PREFIX, aws_account_id)


def configure_cloudtrail(session, aws_account_id):
    """
    Configure a CloudTrail in the customer account.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        aws_account_id (string): The aws account id to include in the name

    Returns:
        The response code of creating cloudtrail.

    """
    cloudtrail = session.client("cloudtrail")
    name = get_cloudtrail_name(aws_account_id)

    if trail_exists(cloudtrail, name):
        response = update_cloudtrail(cloudtrail, name)
    else:
        response = create_cloudtrail(cloudtrail, name)

    # limit to write only events & turn on logging
    put_event_selectors(cloudtrail, name)
    cloudtrail.start_logging(Name=name)
    return response


def trail_exists(cloudtrail, name):
    """
    Check to see if a cloudigrade CloudTrail exists for the account.

    Args:
        cloudtrail (botocore client): The cloudtrail client
        name (string): The name of the cloudtrail to lookup
    Returns:
        A bool stating whether or not the trail exists.

    """
    trails = cloudtrail.describe_trails(trailNameList=[name])
    # the trailList will not be empty if a trail with the specified name exists
    return trails.get("trailList", []) != []


def put_event_selectors(cloudtrail, name):
    """
    Specify that the trail collect data on write-only events.

    Args:
        cloudtrail (boto3.Session): A temp
        name (string): The name of the cloudtrail to configure
    """
    event_selector = [{"ReadWriteType": "WriteOnly"}]
    try:
        response = cloudtrail.put_event_selectors(
            TrailName=name, EventSelectors=event_selector
        )
        return response
    except ClientError as e:
        raise e


def create_cloudtrail(cloudtrail, name):
    """Create a CloudTrail in the customer account.

    Args:
        cloudtrail (botocore client): The cloudtrail client
        name (string): The name of the cloudtrail to configure
    """
    logger.debug(_("Creating the cloudtrail %s"), name)
    try:
        response = cloudtrail.create_trail(
            Name=name,
            S3BucketName=settings.S3_BUCKET_NAME,
            IncludeGlobalServiceEvents=True,
            IsMultiRegionTrail=True,
        )
        return response
    except ClientError as e:
        if "MaximumNumberOfTrailsExceededException" == e.response["Error"]["Code"]:
            raise MaximumNumberOfTrailsExceededException(e.response["Error"]["Message"])
        raise e


def update_cloudtrail(cloudtrail, name):
    """
    Update the existing CloudTrail in the customer account.

    Args:
        cloudtrail (botocore client): The cloudtrail client
        name (string): The name of the cloudtrail to configure
    """
    logger.debug(_("Updating the cloudtrail %s"), name)
    try:
        response = cloudtrail.update_trail(
            Name=name,
            S3BucketName=settings.S3_BUCKET_NAME,
            IncludeGlobalServiceEvents=True,
            IsMultiRegionTrail=True,
        )
        return response
    except ClientError as e:
        raise e


def disable_cloudtrail(cloudtrail, name):
    """Disable logging in the existing customer CloudTrail.

    Args:
        cloudtrail (botocore client): The cloudtrail client
        name (string): The name of the cloudtrail to disable logging
    """
    logger.debug(_("Disabling logging in the cloudtrail %s"), name)

    try:
        response = cloudtrail.stop_logging(Name=name,)
        return response
    except ClientError as e:
        raise e
