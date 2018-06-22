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
    customer_snapshot_id = aws.get_ami_snapshot_id(ami)
    customer_snapshot = aws.get_snapshot(
        session, customer_snapshot_id, source_region)

    if customer_snapshot.encrypted:
        image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        image.is_encrypted = True
        image.save()
        raise AwsSnapshotEncryptedError

    aws.add_snapshot_ownership(customer_snapshot)

    snapshot_copy_id = aws.copy_snapshot(customer_snapshot_id, source_region)
    volume_information = {
        'arn': arn,
        'source_region': source_region,
        'ami_id': ami_id,
        'customer_snapshot_id': customer_snapshot_id,
        'snapshot_copy_id': snapshot_copy_id
    }
    logger.info(_(
        '{0}: customer_snapshot_id={1}, snapshot_copy_id={2}').format(
        'copy_ami_snapshot',
        volume_information['customer_snapshot_id'],
        volume_information['snapshot_copy_id']))
    create_volume.delay(volume_information)


@retriable_shared_task
@rewrap_aws_errors
def create_volume(volume_information):
    """
    Create an AWS Volume in the primary AWS account.

    Args:
        volume_information (dict): Meta-data about scanned instances (arn,
            source_region, ami_id, customer_snapshot_id, snapshot_copy_id)

    Returns:
        None: Run as an asynchronous Celery task.

    """
    zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
    volume_id = aws.create_volume(volume_information['snapshot_copy_id'], zone)
    region = aws.get_region_from_availability_zone(zone)
    volume_information['volume_id'] = volume_id
    volume_information['volume_region'] = region

    logger.info(_('{0}: volume_id={1}, volume_region={2}').format(
        'create_volume',
        volume_information['volume_id'],
        volume_information['volume_region']))
    enqueue_ready_volume.delay(volume_information)


@retriable_shared_task
@rewrap_aws_errors
def enqueue_ready_volume(volume_information):
    """
    Enqueues information about an AMI and volume for later use.

    Args:
        volume_information (dict): Meta-data about scanned instances (arn,
            source_region, ami_id, customer_snapshot_id, snapshot_copy_id,
            volume_id, volume_region)

    Returns:
        None: Run as an asynchronous Celery task.

    """
    volume = aws.get_volume(
        volume_information['volume_id'],
        volume_information['volume_region'])
    aws.check_volume_state(volume)
    messages = [
        volume_information
    ]

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
        messages (list): A list of dictionary items containing meta-data (arn,
            source_region, ami_id, customer_snapshot_id, snapshot_copy_id,
            volume_id, volume_region)
        cloud (str): String key representing what cloud we're inspecting.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    for message in messages:
        image = AwsMachineImage.objects.get(ec2_ami_id=message['ami_id'])
        image.status = image.INSPECTING
        image.save()

    task_command = ['-c', cloud]
    if settings.HOUNDIGRADE_DEBUG:
        task_command.extend(['--debug'])

    ecs = boto3.client('ecs')
    # get ecs container instance id
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
    ec2_instance_id = result['containerInstances'][0]['ec2InstanceId']

    # Obtain boto EC2 Instance
    ec2 = boto3.resource('ec2')
    ec2_instance = ec2.Instance(ec2_instance_id)

    logger.info(_('{0} attaching volumes').format(
        'run_inspection_cluster'))
    # attach volumes
    for index, message in enumerate(messages):
        mount_point = generate_device_name(index)
        volume = ec2.Volume(message['volume_id'])
        logger.info(_('{0} attaching volume {1} to instance {2}').format(
            'run_inspection_cluster',
            message['volume_id'],
            ec2_instance_id))

        volume.attach_to_instance(
            Device=mount_point, InstanceId=ec2_instance_id)

        logger.info(_('{0} modify volume {1} to auto-delete').format(
            'run_inspection_cluster',
            message['volume_id']))
        # Configure volumes to delete when instance is scaled down
        ec2_instance.modify_attribute(BlockDeviceMappings=[
            {
                'DeviceName': mount_point,
                'Ebs': {
                    'DeleteOnTermination': True
                }
            }
        ])

        # Remove permissions from customer_snapshot
        logger.info(_(
            '{0} remove ownership from customer snapshot {1}').format(
            'run_inspection_cluster',
            message['customer_snapshot_id']))
        session = aws.get_session(message['arn'])
        customer_snapshot = aws.get_snapshot(
            session,
            message['customer_snapshot_id'],
            message['source_region'])
        aws.remove_snapshot_ownership(customer_snapshot)

        # Delete snapshot_copy
        logger.info(_('{0} delete cloudigrade snapshot copy {1}').format(
            'run_inspection_cluster',
            message['snapshot_copy_id']))
        snapshot_copy = ec2.Snapshot(message['snapshot_copy_id'])
        snapshot_copy.delete(DryRun=False)

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
                        'name': 'AWS_DEFAULT_REGION',
                        'value': settings.AWS_SQS_REGION
                    },
                    {
                        'name': 'AWS_ACCESS_KEY_ID',
                        'value': settings.AWS_SQS_ACCESS_KEY_ID
                    },
                    {
                        'name': 'AWS_SECRET_ACCESS_KEY',
                        'value': settings.AWS_SQS_SECRET_ACCESS_KEY
                    },
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


@retriable_shared_task
@rewrap_aws_errors
def scale_down_cluster():
    """
    Scale down cluster after houndigrade scan.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    logger.info(_('Scaling down ECS cluster.'))
    aws.scale_down(settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME)


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
            ami.status = ami.INSPECTED
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
        scale_down_cluster.delay()
