"""Helper utility module to wrap up common AWS CloudTrail operations."""
import logging

from botocore.exceptions import ClientError
from django.conf import settings
from django.utils.translation import gettext as _


logger = logging.getLogger(__name__)


def configure_cloudtrail(session, aws_account_id):
    """
    Configure a CloudTrail in the customer account.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        aws_account_id (string): The aws account id to include in the name
        include_global_service_events (bool): Specifies whether trail is
            publishing events from global services to log files
        is_multi_region_trail (bool): Specifies whether the trail is created in
            all regions or current region

    Returns:
        The response code of creating cloudtrail.

    """
    cloudtrail = session.client('cloudtrail')
    name = 'cloudigrade-{0}'.format(aws_account_id)

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
    return trails.get('trailList', []) != []


def put_event_selectors(cloudtrail, name):
    """
    Specify that the trail collect data on write-only events.

    Args:
        cloudtrail (boto3.Session): A temp
        name (string): The name of the cloudtrail to configure
    """
    event_selector = [{'ReadWriteType': 'WriteOnly'}]
    try:
        response = cloudtrail.put_event_selectors(
            TrailName=name,
            EventSelectors=event_selector
        )
        return response
    except ClientError as e:
        raise e


def create_cloudtrail(cloudtrail, name):
    """Create a CloudTrail in the customer account.

    Args:
        cloudtrail (botocore client): The cloudtrail client
        name (string): The name of the cloudtrail to configure
        include_global_service_events (bool): Specifies whether trail is
            publishing events from global services to log files
        is_multi_region_trail (bool): Specifies whether the trail is created in
            all regions or current region
    """
    logger.debug(_('Creating the cloudtrail {0}').format(name))
    try:
        response = cloudtrail.create_trail(
            Name=name,
            S3BucketName='{0}cloudigrade-s3'.format(
                settings.AWS_NAME_PREFIX),
            IncludeGlobalServiceEvents=True,
            IsMultiRegionTrail=True,
        )
        return response
    except ClientError as e:
        raise e


def update_cloudtrail(cloudtrail, name):
    """
    Update the existing CloudTrail in the customer account.

    Args:
        cloudtrail (botocore client): The cloudtrail client
        name (string): The name of the cloudtrail to configure
        include_global_service_events (bool): Specifies whether trail is
            publishing events from global services to log files
        is_multi_region_trail (bool): Specifies whether the trail is created in
            all regions or current region
    """
    logger.debug(_('Updating the cloudtrail {0}').format(name))
    try:
        response = cloudtrail.update_trail(
            Name=name,
            S3BucketName='{0}cloudigrade-s3'.format(
                settings.AWS_NAME_PREFIX),
            IncludeGlobalServiceEvents=True,
            IsMultiRegionTrail=True
        )
        return response
    except ClientError as e:
        raise e
