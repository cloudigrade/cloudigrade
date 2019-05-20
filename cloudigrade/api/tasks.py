"""
Celery tasks for use in the api v2 app.

Note for developers:
If you find yourself adding a new Celery task, please be aware of how Celery
determines which queue to read and write to work on that task. By default,
Celery tasks will go to a queue named "celery". If you wish to separate a task
onto a different queue (which may make it easier to see the volume of specific
waiting tasks), please be sure to update all the relevant configurations to
use that custom queue. This includes CELERY_TASK_ROUTES in config and the
Celery worker's --queues argument (see deployment-configs.yaml in shiftigrade).
"""
import json
import logging
from datetime import timedelta

import boto3
from botocore.exceptions import ClientError
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from api.models import (AwsCloudAccount,
                        AwsMachineImage,
                        Instance,
                        InstanceEvent,
                        MachineImage,
                        Run)
from api.util import (
    add_messages_to_queue,
    create_aws_machine_image_copy,
    create_initial_aws_instance_events,
    create_new_machine_images,
    generate_aws_ami_messages,
    normalize_runs,
    read_messages_from_queue,
    recalculate_runs,
    start_image_inspection,
)
from util import aws
from util.aws import rewrap_aws_errors
from util.celery import retriable_shared_task
from util.exceptions import (AwsECSInstanceNotReady,
                             AwsSnapshotEncryptedError,
                             AwsTooManyECSInstances,
                             InvalidHoundigradeJsonFormat)
from util.misc import generate_device_name

logger = logging.getLogger(__name__)

# Constants
CLOUD_KEY = 'cloud'
CLOUD_TYPE_AWS = 'aws'
HOUNDIGRADE_MESSAGE_READ_LEN = 10


@retriable_shared_task
@rewrap_aws_errors
def initial_aws_describe_instances(account_id):
    """
    Fetch and save instances data found upon AWS cloud account creation.

    Args:
        account_id (int): the AwsAccount id
    """
    aws_account = AwsCloudAccount.objects.get(pk=account_id)
    account = aws_account.cloud_account.get()
    arn = aws_account.account_arn

    session = aws.get_session(arn)
    instances_data = aws.describe_instances_everywhere(session)
    with transaction.atomic():
        new_ami_ids = create_new_machine_images(session, instances_data)
        create_initial_aws_instance_events(account, instances_data)
    messages = generate_aws_ami_messages(instances_data, new_ami_ids)
    for message in messages:
        start_image_inspection(str(arn), message['image_id'],
                               message['region'])


@shared_task
def process_instance_event(event):
    """Process instance events that have been saved during log analysis."""
    after_run = Q(start_time__gt=event.occurred_at)
    during_run = Q(start_time__lte=event.occurred_at,
                   end_time__gt=event.occurred_at)
    during_run_no_end = Q(start_time__lte=event.occurred_at, end_time=None)

    filters = after_run | during_run | during_run_no_end
    instance = Instance.objects.get(id=event.instance_id)

    if Run.objects.filter(filters, instance=instance).exists():
        recalculate_runs(event)
    elif event.event_type == InstanceEvent.TYPE.power_on:
        normalized_runs = normalize_runs([event])
        for index, normalized_run in enumerate(normalized_runs):
            logger.info(
                'Processing run {} of {}'.format(index + 1,
                                                 len(normalized_runs))
            )
            run = Run(
                start_time=normalized_run.start_time,
                end_time=normalized_run.end_time,
                machineimage_id=normalized_run.image_id,
                instance_id=normalized_run.instance_id,
                instance_type=normalized_run.instance_type,
                memory=normalized_run.instance_memory,
                vcpu=normalized_run.instance_vcpu,
            )
            run.save()


@retriable_shared_task
@rewrap_aws_errors
def copy_ami_snapshot(arn, ami_id, snapshot_region, reference_ami_id=None):
    """
    Copy an AWS Snapshot to the primary AWS account.

    Args:
        arn (str): The AWS Resource Number for the account with the snapshot
        ami_id (str): The AWS ID for the machine image
        snapshot_region (str): The region the snapshot resides in
        reference_ami_id (str): Optional. The id of the original image from
            which this image was copied. We need to know this in some cases
            where we create a copy of the image in the customer's account
            before we can copy its snapshot, and we must pass this information
            forward for appropriate reference and cleanup.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    session = aws.get_session(arn)
    session_account_id = aws.get_session_account_id(session)
    ami = aws.get_ami(session, ami_id, snapshot_region)
    if not ami:
        logger.info(
            _(
                'Cannot copy AMI %(image_id)s snapshot from '
                '%(source_region)s. Saving ERROR status.'
            ),
            {'image_id': ami_id, 'source_region': snapshot_region},
        )
        awsimage = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        image = awsimage.machine_image.get()
        image.status = image.ERROR
        image.save()
        return

    customer_snapshot_id = aws.get_ami_snapshot_id(ami)
    try:
        customer_snapshot = aws.get_snapshot(
            session, customer_snapshot_id, snapshot_region
        )

        if customer_snapshot.encrypted:
            awsimage = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
            image = awsimage.machine_image.get()
            image.is_encrypted = True
            image.save()
            raise AwsSnapshotEncryptedError

        logger.info(
            _(
                'AWS snapshot "%(snapshot_id)s" for image "%(image_id)s" has '
                'owner "%(owner_id)s"; current session is account '
                '"%(account_id)s"'
            ),
            {
                'snapshot_id': customer_snapshot.snapshot_id,
                'image_id': ami.id,
                'owner_id': customer_snapshot.owner_id,
                'account_id': session_account_id,
            },
        )

        if (
            customer_snapshot.owner_id != session_account_id and
                reference_ami_id is None
        ):
            copy_ami_to_customer_account.delay(arn, ami_id, snapshot_region)
            # Early return because we need to stop processing the current AMI.
            # A future call will process this new copy of the
            # current AMI instead.
            return
    except ClientError as e:
        if e.response.get('Error').get('Code') == 'InvalidSnapshot.NotFound':
            # Possibly a marketplace AMI, try to handle it by copying.
            copy_ami_to_customer_account.delay(arn, ami_id, snapshot_region)
            return
        raise e

    aws.add_snapshot_ownership(customer_snapshot)

    snapshot_copy_id = aws.copy_snapshot(customer_snapshot_id, snapshot_region)
    logger.info(
        _(
            '%(label)s: customer_snapshot_id=%(snapshot_id)s, '
            'snapshot_copy_id=%(copy_id)s'
        ),
        {
            'label': 'copy_ami_snapshot',
            'snapshot_id': customer_snapshot_id,
            'copy_id': snapshot_copy_id,
        },
    )

    # Schedule removal of ownership on customer snapshot
    remove_snapshot_ownership.delay(
        arn, customer_snapshot_id, snapshot_region, snapshot_copy_id
    )

    if reference_ami_id is not None:
        # If a reference ami exists, that means we have been working with a
        # copy in here. That means we need to remove that copy and pass the
        # original reference AMI ID through the rest of the task chain so the
        # results get reported for that original reference AMI, not our copy.
        # TODO FIXME Do we or don't we clean up?
        # If we do, we need permissions to include `ec2:DeregisterImage` and
        # `ec2:DeleteSnapshot` but those are both somewhat scary...
        #
        # For now, since we are not deleting the copy image from AWS, we need
        # to record a reference to our database that we can look at later to
        # indicate the relationship between the original AMI and the copy.
        create_aws_machine_image_copy(ami_id, reference_ami_id)
        ami_id = reference_ami_id

    # Create volume from snapshot copy
    create_volume.delay(ami_id, snapshot_copy_id)


@retriable_shared_task
@rewrap_aws_errors
def copy_ami_to_customer_account(arn, reference_ami_id, snapshot_region):
    """
    Copy an AWS Image to the customer's AWS account.

    This is an intermediate step that we occasionally need to use when the
    customer has an instance based on a image that has been privately shared
    by a third party, and that means we cannot directly copy its snapshot. We
    can, however, create a copy of the image in the customer's account and use
    that copy for the remainder of the inspection process.

    Args:
        arn (str): The AWS Resource Number for the account with the snapshot
        reference_ami_id (str): The AWS ID for the original image to copy
        snapshot_region (str): The region the snapshot resides in

    Returns:
        None: Run as an asynchronous Celery task.

    """
    session = aws.get_session(arn)
    reference_ami = aws.get_ami(session, reference_ami_id, snapshot_region)
    if not reference_ami:
        logger.info(
            _(
                'Cannot copy reference AMI %(image_id)s from '
                '%(source_region)s. Saving ERROR status.'
            ),
            {'image_id': reference_ami_id, 'source_region': snapshot_region},
        )
        awsimage = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
        image = awsimage.machine_image.get()
        image.status = image.ERROR
        image.save()
        return

    try:
        new_ami_id = aws.copy_ami(session, reference_ami.id, snapshot_region)
    except ClientError as e:
        public_errors = (
            'Images from AWS Marketplace cannot be copied to another AWS '
            'account',
            'Images with EC2 BillingProduct codes cannot be copied '
            'to another AWS account',
            'You do not have permission to access the storage of this ami',
        )
        private_errors = (
            'You do not have permission to access the storage of this ami'
        )
        if e.response.get('Error').get('Code') == 'InvalidRequest':
            error = (
                e.response.get('Error').get('Message')[:-1]
                if e.response.get('Error').get('Message').endswith('.')
                else e.response.get('Error').get('Message')
            )

            if not reference_ami.public and error in private_errors:
                # This appears to be a private AMI, shared with our customer,
                # but not given access to the storage.
                logger.warning(
                    _(
                        'Found a private image "%s" with inaccessible storage,'
                        ' marking as erred'
                    ),
                    reference_ami_id,
                )
                ami = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
                ami.status = ami.ERROR
                ami.save()
                return
            elif error in public_errors:
                # This appears to be a marketplace AMI, mark it as inspected.
                logger.info(
                    _(
                        'Found a marketplace/community image "%s", '
                        'marking as inspected'
                    ),
                    reference_ami_id,
                )
                ami = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
                ami.status = ami.INSPECTED
                ami.aws_marketplace_image = True
                ami.save()
                return

        raise e

    copy_ami_snapshot.delay(arn, new_ami_id, snapshot_region, reference_ami_id)


@retriable_shared_task
@rewrap_aws_errors
def remove_snapshot_ownership(
    arn, customer_snapshot_id, customer_snapshot_region, snapshot_copy_id
):
    """
    Remove cloudigrade ownership from customer snapshot.

    Args:
        arn (str): The AWS Resource Number for the account with the snapshot
        customer_snapshot_id (str): The id of the snapshot to remove ownership
        customer_snapshot_region (str): The region where
            customer_snapshot_id resides
        snapshot_copy_id (str): The id of the snapshot that must
            be ready to continue
    Returns:
        None: Run as an asynchronous Celery task.
    """
    ec2 = boto3.resource('ec2')

    # Wait for snapshot to be ready
    try:
        snapshot_copy = ec2.Snapshot(snapshot_copy_id)
        aws.check_snapshot_state(snapshot_copy)
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') == \
                'InvalidSnapshot.NotFound':
            logger.info(
                _(
                    '%(label)s detected snapshot_copy_id %(copy_id)s '
                    'already deleted.'
                ),
                {'label': 'remove_snapshot_ownership',
                 'copy_id': snapshot_copy_id},
            )
        else:
            raise

    # Remove permissions from customer_snapshot
    logger.info(
        _('%(label)s remove ownership from customer snapshot %(snapshot_id)s'),
        {'label': 'remove_snapshot_ownership',
         'snapshot_id': customer_snapshot_id},
    )
    session = aws.get_session(arn)
    customer_snapshot = aws.get_snapshot(
        session, customer_snapshot_id, customer_snapshot_region
    )
    aws.remove_snapshot_ownership(customer_snapshot)


@retriable_shared_task
@rewrap_aws_errors
def create_volume(ami_id, snapshot_copy_id):
    """
    Create an AWS Volume in the primary AWS account.

    Args:
        ami_id (str): The AWS AMI id for which this request originated
        snapshot_copy_id (str): The id of the snapshot to use for the volume
    Returns:
        None: Run as an asynchronous Celery task.
    """
    zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
    volume_id = aws.create_volume(snapshot_copy_id, zone)
    region = aws.get_region_from_availability_zone(zone)

    logger.info(
        _('%(label)s: volume_id=%(volume_id)s, volume_region=%(region)s'),
        {'label': 'create_volume', 'volume_id': volume_id, 'region': region},
    )

    delete_snapshot.delay(snapshot_copy_id, volume_id, region)
    enqueue_ready_volume.delay(ami_id, volume_id, region)


@retriable_shared_task
@rewrap_aws_errors
def delete_snapshot(snapshot_copy_id, volume_id, volume_region):
    """
    Delete snapshot after volume is ready.

    Args:
        snapshot_copy_id (str): The id of the snapshot to delete
        volume_id (str): The id of the volume that must be ready
        volume_region (str): The region of the volume
    Returns:
        None: Run as an asynchronous Celery task.
    """
    ec2 = boto3.resource('ec2')

    # Wait for volume to be ready
    volume = aws.get_volume(volume_id, volume_region)
    aws.check_volume_state(volume)

    # Delete snapshot_copy
    logger.info(
        _('%(label)s delete cloudigrade snapshot copy %(copy_id)s'),
        {'label': 'delete_snapshot', 'copy_id': snapshot_copy_id},
    )
    snapshot_copy = ec2.Snapshot(snapshot_copy_id)
    snapshot_copy.delete(DryRun=False)


@retriable_shared_task
@rewrap_aws_errors
def enqueue_ready_volume(ami_id, volume_id, volume_region):
    """
    Enqueues information about an AMI and volume for later use.

    Args:
        ami_id (str): The AWS AMI id for which this request originated
        volume_id (str): The id of the volume that must be ready
        volume_region (str): The region of the volume
    Returns:
        None: Run as an asynchronous Celery task.
    """
    volume = aws.get_volume(volume_id, volume_region)
    aws.check_volume_state(volume)
    messages = [{'ami_id': ami_id, 'volume_id': volume_id}]

    queue_name = '{0}ready_volumes'.format(settings.AWS_NAME_PREFIX)
    add_messages_to_queue(queue_name, messages)


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


@shared_task
@rewrap_aws_errors
def scale_up_inspection_cluster():
    """
    Scale up the "houndigrade" inspection cluster.

    Returns:
        None: Run as a scheduled Celery task.

    """
    queue_name = '{0}ready_volumes'.format(settings.AWS_NAME_PREFIX)
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
            meta-data (ami_id, volume_id)
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

    logger.info(_('%s attaching volumes'), 'run_inspection_cluster')
    # attach volumes
    for index, message in enumerate(messages):
        mount_point = generate_device_name(index)
        volume = ec2.Volume(message['volume_id'])
        logger.info(
            _('%(label)s attaching volume %(volume_id)s from AMI'
              ' %(ami_id)s to instance %(instance)s at %(mount_point)s'),
            {
                'label': 'run_inspection_cluster',
                'volume_id': message['volume_id'],
                'ami_id': message['ami_id'],
                'instance': ec2_instance_id,
                'mount_point': mount_point,
            }
        )
        try:
            volume.attach_to_instance(
                Device=mount_point, InstanceId=ec2_instance_id)
        except ClientError as e:
            error_code = e.response.get('Error').get('Code')
            error_message = e.response.get('Error').get('Message')

            ami = AwsMachineImage.objects.get(ec2_ami_id=message['ami_id'])

            if error_code in ('OptInRequired', 'IncorrectInstanceState',) \
                    and 'marketplace' in error_message.lower():
                logger.info(_('Found a marketplace AMI "%s" when trying to '
                              'copy volume, this should not happen, '
                              'but here we are.'), message['ami_id'])
                ami.aws_marketplace_image = True
                ami.status = MachineImage.INSPECTED
            else:
                logger.error(
                    _('Encountered an issue when trying to attach volume '
                      '"%(volume_id)s" from AMI "%(ami_id)s" to inspection '
                      'instance. Error code: "%(error_code)s". Error '
                      'message: "%(error_message)s". Setting image state to '
                      'ERROR.'), {
                        'volume_id': message['volume_id'],
                        'ami_id': message['ami_id'],
                        'error_code': error_code,
                        'error_message': error_message,
                    }
                )
                ami.status = MachineImage.ERROR

            ami.save()
            volume.delete()

            continue

        logger.info(_('%(label)s modify volume %(volume_id)s to auto-delete'),
                    {'label': 'run_inspection_cluster',
                     'volume_id': message['volume_id']}
                    )
        # Configure volumes to delete when instance is scaled down
        ec2_instance.modify_attribute(BlockDeviceMappings=[
            {
                'DeviceName': mount_point,
                'Ebs': {
                    'DeleteOnTermination': True
                }
            }
        ])

        task_command.extend(['-t', message['ami_id'], mount_point])

    if '-t' not in task_command:
        logger.warning(_('No targets left to inspect, exiting early.'))
        return

    result = ecs.register_task_definition(
        family=f'{settings.HOUNDIGRADE_ECS_FAMILY_NAME}',
        containerDefinitions=[_build_container_definition(task_command)],
        requiresCompatibilities=['EC2']
    )

    # release the hounds
    ecs.run_task(
        cluster=settings.HOUNDIGRADE_ECS_CLUSTER_NAME,
        taskDefinition=result['taskDefinition']['taskDefinitionArn'],
    )


def _build_container_definition(task_command):
    """
    Build a container definition to be used by an ecs task.

    Args:
        task_command (list): Command to insert into the definition.

    Returns (dict): Complete container definition.

    """
    container_definition = {
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
            },
        ],
        'privileged': True,
        'logConfiguration': {
            'logDriver': 'awslogs',
            'options': {
                'awslogs-create-group': 'true',
                'awslogs-group': f'{settings.AWS_NAME_PREFIX}cloudigrade-ecs',
                'awslogs-region': settings.AWS_SQS_REGION,
            }
        }
    }
    if settings.HOUNDIGRADE_ENABLE_SENTRY:
        container_definition['environment'].extend([
            {
                'name': 'HOUNDIGRADE_SENTRY_DSN',
                'value': settings.HOUNDIGRADE_SENTRY_DSN
            },
            {
                'name': 'HOUNDIGRADE_SENTRY_RELEASE',
                'value': settings.HOUNDIGRADE_SENTRY_RELEASE
            },
            {
                'name': 'HOUNDIGRADE_SENTRY_ENVIRONMENT',
                'value': settings.HOUNDIGRADE_SENTRY_ENVIRONMENT
            },
        ])

    return container_definition


@transaction.atomic
def persist_aws_inspection_cluster_results(inspection_results):
    """
    Persist the aws houndigrade inspection result.

    Args:
        inspection_results (dict): A dict containing houndigrade results
    Returns:
        None
    """
    images = inspection_results.get('images')
    if images is None:
        raise InvalidHoundigradeJsonFormat(_(
            'Inspection results json missing images: {}').format(
            inspection_results))

    for image_id, image_json in images.items():
        ami = AwsMachineImage.objects.get(ec2_ami_id=image_id)
        image = ami.machine_image.get()
        image.inspection_json = json.dumps(image_json)
        image.status = image.INSPECTED
        image.save()


@shared_task
@rewrap_aws_errors
def persist_inspection_cluster_results_task():
    """
    Task to run periodically and read houndigrade messages.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    queue_url = aws.get_sqs_queue_url(settings.HOUNDIGRADE_RESULTS_QUEUE_NAME)
    successes, failures = [], []
    for message in aws.yield_messages_from_queue(
            queue_url, HOUNDIGRADE_MESSAGE_READ_LEN):
        logger.info(_('Processing inspection results with id "%s"'),
                    message.message_id
                    )

        inspection_results = json.loads(message.body)
        if inspection_results.get(CLOUD_KEY) == CLOUD_TYPE_AWS:
            try:
                persist_aws_inspection_cluster_results(
                    inspection_results)
            except Exception as e:
                logger.exception(_(
                    'Unexpected error in result processing: %s'
                ), e)
                logger.debug(_(
                    'Failed message body is: %s'
                ), message.body)
                failures.append(message)
                continue

            logger.info(_(
                'Successfully processed message id %s; deleting from queue.'
            ), message.message_id)
            aws.delete_messages_from_queue(queue_url, [message])
            successes.append(message)
        else:
            logger.error(_('Unsupported cloud type: "%s"'),
                         inspection_results.get(CLOUD_KEY))
            failures.append(message)

    if successes or failures:
        scale_down_cluster.delay()

    return successes, failures


@shared_task
@transaction.atomic
def inspect_pending_images():
    """
    (Re)start inspection of images in PENDING, PREPARING, or INSPECTING status.

    This generally should not be necessary for most images, but if an image
    inspection fails to proceed normally, this function will attempt to run it
    through inspection again.

    This function runs atomically in a transaction to protect against the risk
    of it being called multiple times simultaneously which could result in the
    same image being found and getting multiple inspection tasks.
    """
    updated_since = (
        timezone.now() - timedelta(
            seconds=settings.INSPECT_PENDING_IMAGES_MIN_AGE
        )
    )
    restartable_statuses = [
        MachineImage.PENDING,
        MachineImage.PREPARING,
        MachineImage.INSPECTING,
    ]
    images = MachineImage.objects.filter(
        status__in=restartable_statuses,
        instance__aws_instance__region__isnull=False,
        updated_at__lt=updated_since,
    ).distinct()
    logger.info(
        _('Found %(number)s images for inspection that have not updated '
          'since %(updated_time)s'),
        {'number': images.count(), 'updated_time': updated_since}
    )

    for image in images:
        instance = image.instance_set.filter(
            aws_instance__region__isnull=False
        ).first()
        arn = instance.cloud_account.content_object.account_arn
        ami_id = image.content_object.ec2_ami_id
        region = instance.content_object.region
        start_image_inspection(arn, ami_id, region)
