"""Celery tasks for use in the account app."""
from django.conf import settings

from account.models import AwsMachineImage
from util import aws
from util.aws import rewrap_aws_errors
from util.celery import retriable_shared_task
from util.exceptions import AwsSnapshotEncryptedError


@retriable_shared_task
@rewrap_aws_errors
def copy_ami_snapshot(arn, ami_id, source_region):
    """
    Copy an AWS Snapshot to the primary AWS account.

    Args:
        arn (str): The AWS Resource Number for the account with the snapshot
        ami_id (str): The AWS ID for the machine image
        source_region (str): The region the snapshot resides in

    Returns:
        None: Run as an asynchronous Celery task.

    """
    session = aws.get_session(arn)
    ami = aws.get_ami(session, ami_id, source_region)
    snapshot_id = aws.get_ami_snapshot_id(ami)
    snapshot = aws.get_snapshot(session, snapshot_id, source_region)

    if snapshot.encrypted:
        image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        image.is_encrypted = True
        image.save()
        raise AwsSnapshotEncryptedError

    aws.add_snapshot_ownership(
        session,
        snapshot,
        source_region
    )

    new_snapshot_id = aws.copy_snapshot(snapshot_id, source_region)
    create_volume(ami_id, new_snapshot_id)


@retriable_shared_task
@rewrap_aws_errors
def create_volume(ami_id, snapshot_id):
    """
    Create an AWS Volume in the primary AWS account.

    Args:
        ami_id (str): The AWS AMI id for which this request originated
        snapshot_id (str): The id of the snapshot to use for the volume

    Returns:
        None: Run as an asynchronous Celery task.

    """
    zone = settings.HOUNDIGRADE_AVAILABILITY_ZONE
    volume_id = aws.create_volume(snapshot_id, zone)
    # TODO Replace the next `print` call with a call to the next task.
    # Do something like: enqueue_ready_volume(ami_id, volume_id)
    print('Volume {} is being created for AMI {}'.format(volume_id, ami_id))
