"""Helper utility module to wrap up common AWS EC2 operations."""
import enum
import logging

import boto3
from botocore.exceptions import ClientError
from django.utils.translation import gettext as _

from util.aws.helper import get_regions
from util.aws.sts import _get_primary_account_id
from util.exceptions import (AwsSnapshotCopyLimitError,
                             AwsSnapshotNotOwnedError, AwsVolumeError,
                             AwsVolumeNotReadyError)
from util.exceptions import SnapshotNotReadyException

logger = logging.getLogger(__name__)


class InstanceState(enum.Enum):
    """
    Enumeration of EC2 instance state codes.

    See also:
        https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceState.html

    """

    pending = 0
    running = 16
    shutting_down = 32
    terminated = 48
    stopping = 64
    stopped = 80

    @classmethod
    def is_running(cls, code):
        """
        Check if the given code is effectively a running state.

        Args:
            code (int): The code from an EC2 AwsInstance state.

        Returns:
            bool: True if we consider the instance to be running else False.

        """
        return code == cls.running.value


def get_running_instances(session):
    """
    Find all running EC2 instances visible to the given ARN.

    Args:
        session (boto3.Session): A temporary session tied to a customer account

    Returns:
        dict: Lists of instance IDs keyed by region where they were found.

    """
    running_instances = {}

    for region_name in get_regions(session):

        ec2 = session.client('ec2', region_name=region_name)
        logger.debug(_('Describing instances in {0}').format(region_name))
        instances = ec2.describe_instances()
        for reservation in instances.get('Reservations', []):
            running_instances[region_name] = [
                instance for instance in reservation.get('Instances', [])
                if InstanceState.is_running(instance['State']['Code'])
            ]

    return running_instances


def get_ec2_instance(session, instance_id):
    """
    Return an EC2 AwsInstance object from the customer account.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        instance_id (str): An EC2 instance ID

    Returns:
        AwsInstance: A boto3 AwsInstance object.

    """
    return session.resource('ec2').Instance(instance_id)


def get_ami(session, image_id, region):
    """
    Return an Amazon Machine Image running on an EC2 instance.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        image_id (str): An AMI ID

    Returns:
        Image: A boto3 EC2 Image object.

    """
    return session.resource('ec2', region_name=region).Image(image_id)


def get_ami_snapshot_id(ami):
    """
    Return the snapshot id from an Image object.

    Args:
        ami (boto3.resources.factory.ec2.Image): A machine image object

    Returns:
        string: The snapshot id for the machine image's root volume

    """
    for mapping in ami.block_device_mappings:
        # For now we are focusing exclusively on the root device
        if mapping['DeviceName'] != ami.root_device_name:
            continue
        return mapping.get('Ebs', {}).get('SnapshotId', '')


def get_snapshot(session, snapshot_id, region):
    """
    Return an AMI Snapshot for an EC2 instance.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        snapshot_id (str): A snapshot ID

    Returns:
        Snapshot: A boto3 EC2 Snapshot object.

    """
    return session.resource('ec2', region_name=region).Snapshot(snapshot_id)


def add_snapshot_ownership(snapshot):
    """
    Add permissions to a snapshot.

    Args:
        snapshot: A boto3 EC2 Snapshot object.

    Returns:
        None

    Raises:
        AwsSnapshotNotOwnedError: Ownership was not verified.

    """
    attribute = 'createVolumePermission'
    user_id = _get_primary_account_id()

    permission = {
        'Add': [
            {'UserId': user_id},
        ]
    }

    snapshot.modify_attribute(
        Attribute=attribute,
        CreateVolumePermission=permission,
        OperationType='add',
        UserIds=[user_id]
    )

    # The modify call returns None. This is a check to make sure
    # permissions are added successfully.
    response = snapshot.describe_attribute(Attribute='createVolumePermission')

    for user in response['CreateVolumePermissions']:
        if user['UserId'] == user_id:
            return

    message = _('No CreateVolumePermissions on Snapshot {0} for UserId {1}').\
        format(snapshot.snapshot_id, user_id)
    raise AwsSnapshotNotOwnedError(message)


def copy_snapshot(snapshot_id, source_region):
    """
    Copy a machine image snapshot to a primary AWS account.

    Note: This operation is done from the primarmy account.

    Args:
        snapshot_id (str): The id of the snapshot to modify
        source_region (str): The region the source snapshot resides in

    Returns:
        str: The id of the newly copied snapshot

    """
    snapshot = boto3.resource('ec2').Snapshot(snapshot_id)
    try:
        response = snapshot.copy(SourceRegion=source_region)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceLimitExceeded':
            raise AwsSnapshotCopyLimitError(e.response['Error']['Message'])
        else:
            raise e
    else:
        return response.get('SnapshotId')


def create_volume(snapshot_id, zone):
    """
    Create a volume on the primary AWS account for the given snapshot.

    Args:
        snapshot_id (str): The id of the snapshot to use for the volume
        zone (str): The availability zone in which to create the volume

    Returns:
        str: The id of the newly created volume

    """
    ec2 = boto3.resource('ec2')
    snapshot = ec2.Snapshot(snapshot_id)
    if snapshot.state != 'completed':
        message = '{0} {1} {2}'.format(snapshot_id,
                                       snapshot.state,
                                       snapshot.progress)
        raise SnapshotNotReadyException(message)
    volume = ec2.create_volume(SnapshotId=snapshot_id, AvailabilityZone=zone)
    return volume.id


def get_volume(volume_id, region):
    """
    Return a Volume for an EC2 instance.

    Args:
        volume_id (str): A volume ID
        region (str): The AWS region the volume exists in

    Returns:
        Volume: A boto3 EC2 Volume object.

    """
    return boto3.resource('ec2', region_name=region).Volume(volume_id)


def check_volume_state(volume):
    """Raise an error if volume is not available."""
    if volume.state == 'creating':
        raise AwsVolumeNotReadyError
    elif volume.state in ('in-use', 'deleting', 'deleted', 'error'):
        err = _('Volume {vol_id} has state: {state}').format(
            vol_id=volume.id, state=volume.state
        )
        raise AwsVolumeError(err)
    return
