"""Helper utility module to wrap up common AWS CloudTrail operations."""
import logging

from django.conf import settings
from django.utils.translation import gettext as _

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


def delete_cloudtrail(cloudtrail, name):
    """Delete the customer CloudTrail.

    Args:
        cloudtrail (botocore client): The cloudtrail client
        name (string): The name of the cloudtrail to delete
    """
    logger.debug(_("Deleting the cloudtrail %s"), name)
    response = cloudtrail.delete_trail(Name=name)
    return response
