"""Helper utility module to wrap up common AWS operations."""
import logging
import uuid
from functools import wraps

import boto3
from botocore.exceptions import ClientError
from django.utils.translation import gettext as _

from util.aws.sts import cloudigrade_policy

logger = logging.getLogger(__name__)

# AWS has undocumented validation on the Snapshot and Image Ids
# when executing some "dryrun" commands.
# We are uncertain what the pattern is. Manual testing revealed
# that some codes pass and some fail, so for the time being
# the values are hard-coded.
DRYRUN_SNAPSHOT_ID = 'snap-0f423c31dd96866b2'
DRYRUN_IMAGE_ID = 'ami-0f94fa2a144c74cf1'
DRYRUN_IMAGE_REGION = 'us-east-1'


def get_regions(session, service_name='ec2'):
    """
    Get the full list of available AWS regions for the given service.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        service_name (str): Name of AWS service. Default is 'ec2'.

    Returns:
        list: The available AWS region names.

    """
    return session.get_available_regions(service_name)


def verify_account_access(session):
    """
    Check role for proper access to AWS APIs.

    Args:
        session (boto3.Session): A temporary session tied to a customer account

    Returns:
        tuple[bool, list]: First element of the tuple indicates if role was
        verified, and the second element is a list of actions that failed.

    """
    success = True
    failed_actions = []
    for action in cloudigrade_policy['Statement'][0]['Action']:
        if not _verify_policy_action(session, action):
            # Mark as failure, but keep looping so we can see each specific
            # failure in logs
            failed_actions.append(action)
            success = False
    return success, failed_actions


def _handle_dry_run_response_exception(action, e):
    """
    Handle the normal exception that is raised from a dry-run operation.

    This may look weird, but when a boto3 operation is executed with the
    ``DryRun=True`` argument, the typical behavior is for it to raise a
    ``ClientError`` exception with an error code buried within to indicate if
    the operation would have succeeded.

    See also:
        https://botocore.readthedocs.io/en/latest/client_upgrades.html#error-handling

    Args:
        action (str): The action that was attempted
        e (botocore.exceptions.ClientError): The raised exception

    Returns:
        bool: Whether the operation had access verified, or not.

    """
    dry_run_operation = 'DryRunOperation'
    unauthorized_operation = 'UnauthorizedOperation'

    if e.response['Error']['Code'] == dry_run_operation:
        logger.debug(_('Verified access to "{0}"').format(action))
        return True
    elif e.response['Error']['Code'] == unauthorized_operation:
        logger.warning(_('No access to "{0}"').format(action))
        return False
    raise e


def _verify_policy_action(session, action):
    """
    Check to see if we have access to a specific action.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        action (str): The policy action to check

    Returns:
        bool: Whether the action is allowed, or not.

    """
    ec2 = session.client('ec2')
    try:
        if action == 'ec2:DescribeImages':
            ec2.describe_images(DryRun=True)
        elif action == 'ec2:DescribeInstances':
            ec2.describe_instances(DryRun=True)
        elif action == 'ec2:DescribeSnapshotAttribute':
            ec2.describe_snapshot_attribute(
                DryRun=True,
                SnapshotId=DRYRUN_SNAPSHOT_ID,
                Attribute='productCodes'
            )
        elif action == 'ec2:DescribeSnapshots':
            ec2.describe_snapshots(DryRun=True)
        elif action == 'ec2:ModifySnapshotAttribute':
            ec2.modify_snapshot_attribute(
                SnapshotId=DRYRUN_SNAPSHOT_ID,
                DryRun=True,
                Attribute='createVolumePermission',
                OperationType='add',
            )
        elif action == 'ec2:CopyImage':
            ec2.copy_image(
                Name=f'{uuid.uuid4()}',
                DryRun=True,
                SourceImageId=DRYRUN_IMAGE_ID,
                SourceRegion=DRYRUN_IMAGE_REGION,
            )
        elif action.startswith('cloudtrail:'):
            # unfortunately, CloudTrail does not have a DryRun option like ec2
            # so we cannot verify whether or not our policy gives us the
            # correct permissions without carrying out the action
            logger.warning(_('Unable to verify the policy action "{0}" '
                             'due to CloudTrail not providing a DryRun '
                             'option.')
                           .format(action))
            return True
        else:
            logger.warning(_('No test case exists for action "{0}"')
                           .format(action))
            return False
    except ClientError as e:
        return _handle_dry_run_response_exception(action, e)


def rewrap_aws_errors(original_function):
    """
    Decorate function to except boto AWS ClientError and raise as RuntimeError.

    This is useful when we have boto calls inside of Celery tasks but Celery
    cannot serialize boto AWS ClientError using JSON. If we encounter other
    boto/AWS-specific exceptions that are not serializable, we should add
    support for them here.

    Args:
        original_function: The function to decorate.

    Returns:
        function: The decorated function.

    """
    @wraps(original_function)
    def wrapped(*args, **kwargs):
        try:
            result = original_function(*args, **kwargs)
        except ClientError as e:
            message = _('Unexpected AWS error {0}: {1}').format(type(e), e)
            raise RuntimeError(message)
        return result
    return wrapped


def get_region_from_availability_zone(zone):
    """
    Get the underlying region for an availability zone.

    Args:
        zone (str): The availability zone to check

    Returns:
        str: The region associated with the zone

    """
    response = boto3.client('ec2').describe_availability_zones(
        ZoneNames=[zone]
    )
    return response['AvailabilityZones'][0]['RegionName']
