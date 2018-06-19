"""Celery tasks for use in the account app."""
import json
import logging

import boto3
from botocore.exceptions import ClientError
from celery import shared_task
from django.conf import settings
from django.utils.translation import gettext as _

from account.models import (AwsMachineImage,
                            ImageTag)
from account.util import add_messages_to_queue, read_messages_from_queue
from util import aws
from util.aws import rewrap_aws_errors
from util.celery import retriable_shared_task
from util.exceptions import (AwsECSInstanceNotReady,
                             AwsSnapshotEncryptedError,
                             AwsTooManyECSInstances)
from util.misc import generate_device_name

logger = logging.getLogger(__name__)

# Constants
CLOUD_KEY = 'cloud'
CLOUD_TYPE_AWS = 'aws'
HOUNDIGRADE_MESSAGE_READ_LEN = 10


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

    aws.add_snapshot_ownership(snapshot)

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

    queue_name = '{0}ready_volumes'.format(settings.AWS_SQS_QUEUE_NAME_PREFIX)
    add_messages_to_queue(queue_name, messages)


@shared_task
@rewrap_aws_errors
def scale_up_inspection_cluster():
    """
    Scale up the "houndigrade" inspection cluster.

    Returns:
        None: Run as a scheduled Celery task.

    """
    queue_name = '{0}ready_volumes'.format(settings.AWS_SQS_QUEUE_NAME_PREFIX)
    scaled_down, auto_scaling_group = aws.is_scaled_down(
        settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
    )
    if not scaled_down:
        # Quietly exit and let a future run check the scaling.
        args = {
            'name': settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME,
            'min_size': auto_scaling_group.get('MinSize'),
            'max_size': auto_scaling_group.get('MinSize'),
            'desired_capacity': auto_scaling_group.get('DesiredCapacity'),
            'len_instances': len(auto_scaling_group.get('Instances', []))
        }
        logger.info(_('Auto Scaling group "%(name)s" is not scaled down. '
                      'MinSize=%(min_size)s MaxSize=%(max_size)s '
                      'DesiredCapacity=%(desired_capacity)s '
                      'len(Instances)=%(len_instances)s'), args)
        for instance in auto_scaling_group.get('Instances', []):
            logger.info(_('Instance exists: %s'), instance.get('InstanceId'))
        return

    messages = read_messages_from_queue(
        queue_name,
        settings.HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE
    )

    if len(messages) == 0:
        # Quietly exit and let a future run check for messages.
        logger.info(_('Not scaling up because no new volumes were found.'))
        return

    try:
        aws.scale_up(settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME)
    except ClientError:
        # If scale_up fails unexpectedly, requeue messages so they aren't lost.
        add_messages_to_queue(queue_name, messages)
        raise

    run_inspection_cluster.delay(messages)


@retriable_shared_task
@rewrap_aws_errors
def run_inspection_cluster(messages, cloud='aws'):
    """
    Run task definition for "houndigrade" on the cluster.

    Args:
        messages (list): A list of dictionary items containing
            the ami_id and volume_id to be inspected.
        cloud (str): String key representing what cloud we're inspecting.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    task_command = ['-c', cloud]
    if settings.HOUNDIGRADE_DEBUG:
        task_command.extend(['--debug'])

    # get ecs container instance id
    ecs = boto3.client('ecs')
    result = ecs.list_container_instances(
        cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME)

    # verify we have our single container instance
    num_instances = len(result['containerInstanceArns'])
    if num_instances == 0:
        raise AwsECSInstanceNotReady
    elif num_instances > 1:
        raise AwsTooManyECSInstances

    result = ecs.describe_container_instances(
        containerInstances=[result['containerInstanceArns'][0]],
        cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME
    )
    instance_id = result['containerInstances'][0]['ec2InstanceId']

    # attach volumes
    ec2 = boto3.resource('ec2')
    for index, message in enumerate(messages):
        mount_point = generate_device_name(index)
        volume = ec2.Volume(message['volume_id'])
        volume.attach_to_instance(Device=mount_point, InstanceId=instance_id)
        task_command.extend(['-t', message['ami_id'], mount_point])

    # create task definition
    result = ecs.register_task_definition(
        family=f'{settings.HOUNDIGRADE_ECS_FAMILY_NAME}',
        containerDefinitions=[
            {
                'name': 'Houndigrade',
                'image': f'{settings.HOUNDIGRADE_ECS_IMAGE_NAME}:'
                         f'{settings.HOUNDIGRADE_ECS_IMAGE_TAG}',
                'cpu': 0,
                'memoryReservation': 256,
                'essential': True,
                'command': task_command,
                'environment': [
                    {
                        'name': 'RESULTS_QUEUE_NAME',
                        'value': settings.HOUNDIGRADE_RESULTS_QUEUE_NAME
                    },
                    {
                        'name': 'EXCHANGE_NAME',
                        'value': settings.HOUNDIGRADE_EXCHANGE_NAME
                    },
                    {
                        'name': 'QUEUE_CONNECTION_URL',
                        'value': settings.CELERY_BROKER_URL
                    }
                ],
                'privileged': True,

            }
        ],
        requiresCompatibilities=['EC2']
    )

    # release the hounds
    ecs.run_task(
        cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        taskDefinition=result['taskDefinition']['taskDefinitionArn'],
    )


def persist_aws_inspection_cluster_results(inspection_result):
    """
    Persist the aws houndigrade inspection result.

    Args:
        inspection_result (dict): A dict containing houndigrade results
    Returns:
        None
    """
    rhel_tag = ImageTag.objects.filter(description='rhel').first()
    results = inspection_result.get('results', [])
    for image_id, image_json in results.items():
        ami = AwsMachineImage.objects.filter(ec2_ami_id=image_id).first()
        if ami is not None:
            ami.tags.clear()
            rhel_found = any([attribute.get('rhel_found')
                              for disk_json in list(image_json.values())
                              for attribute in disk_json.values()])
            if rhel_found:
                ami.tags.add(rhel_tag)
            # Add image inspection JSON
            ami.inspection_json = json.dumps(image_json)
            ami.save()
        else:
            logger.error(
                _('AwsMachineImage "{0}" is not found.').format(image_id))


@shared_task
def persist_inspection_cluster_results_task():
    """
    Task to run periodically and read houndigrade messages.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    messages = read_messages_from_queue(
        settings.HOUNDIGRADE_RESULTS_QUEUE_NAME,
        HOUNDIGRADE_MESSAGE_READ_LEN)
    logger.info(_('{0} read {1} message(s) for processing').format(
        'persist_inspection_cluster_results_task', len(messages)))
    if bool(messages):
        for message in messages:
            inspection_result = message
            if isinstance(message, str):
                inspection_result = json.loads(message)
            if inspection_result.get(CLOUD_KEY) == CLOUD_TYPE_AWS:
                persist_aws_inspection_cluster_results(inspection_result)
            else:
                logger.error(_('Unsupported cloud type: "{0}"').format(
                    message.get(CLOUD_KEY)))
