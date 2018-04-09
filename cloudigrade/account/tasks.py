"""Celery tasks for use in the account app."""
from celery import shared_task

from account.models import AwsMachineImage
from util import aws
from util.exceptions import (AwsSnapshotCopyLimitError,
                             AwsSnapshotEncryptedError,
                             AwsSnapshotNotOwnedError)


@shared_task(autoretry_for=(AwsSnapshotCopyLimitError,
                            AwsSnapshotNotOwnedError),
             retry_backoff=True,
             max_retries=10)
def copy_ami_snapshot(arn, ami_id, source_region):
    """
    Copy an AWS Snapshot to the primary AWS accout.

    Args:
        arn (str): The AWS Resource Number for the account with the snapshot
        ami_id (str): The AWS ID for the machine image
        source_region (str): The region the snapshot resides in

    Returns:
        None: Run as an asyncronous Celery task.

    """
    session = aws.get_session(arn)
    ami = aws.get_ami(session, ami_id, source_region)

    try:
        snapshot_id = aws.get_ami_snapshot_id(ami)
    except AwsSnapshotEncryptedError as e:
        image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        image.is_encrypted = True
        image.save()
        raise e

    aws.change_snapshot_ownership(
        session,
        snapshot_id,
        source_region,
        operation='Add'
    )

    aws.copy_snapshot(snapshot_id, source_region)
