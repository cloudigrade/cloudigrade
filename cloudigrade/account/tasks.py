"""Celery tasks for use in the account app."""
from botocore.exceptions import ClientError
from celery import shared_task
from django.conf import settings

from account.models import AwsMachineImage
from account.util import add_messages_to_queue, read_messages_from_queue
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
    create_volume.delay(ami_id, new_snapshot_id)


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
    zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
    volume_id = aws.create_volume(snapshot_id, zone)
    region = aws.get_region_from_availability_zone(zone)

    enqueue_ready_volume.delay(ami_id, volume_id, region)


@retriable_shared_task
@rewrap_aws_errors
def enqueue_ready_volume(ami_id, volume_id, region):
    """
    Enqueues information about an AMI and volume for later use.

    Args:
        ami_id (str): The AWS AMI id for which this request originated
        volume_id (str): The id of the volume to mount
        region (str): The region the volume is being created in

    Returns:
        None: Run as an asynchronous Celery task.

    """
    volume = aws.get_volume(volume_id, region)
    aws.check_volume_state(volume)
    messages = [{'ami_id': ami_id, 'volume_id': volume_id}]

    add_messages_to_queue('ready_volumes', messages)


@shared_task
@rewrap_aws_errors
def scale_up_inspection_cluster():
    """
    Scale up the "houndigrade" inspection cluster.

    Returns:
        None: Run as a scheduled Celery task.

    """
    if not aws.is_scaled_down(settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME):
        # Quietly exit and let a future run check the scaling.
        return

    messages = read_messages_from_queue(
        'ready_volumes',
        settings.HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE
    )

    if len(messages) == 0:
        # Quietly exit and let a future run check for messages.
        return

    try:
        aws.scale_up(settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME)
    except ClientError:
        # If scale_up fails unexpectedly, requeue messages so they aren't lost.
        add_messages_to_queue('ready_volumes', messages)
        raise

    run_inspection_cluster.delay(messages)


@retriable_shared_task
@rewrap_aws_errors
def run_inspection_cluster(ami_volume_list):
    """
    Run task definition for "houndigrade" on the cluster.

    Todo:
        - Implement this!

    Returns:
        None: Run as an asynchronous Celery task.

    """
