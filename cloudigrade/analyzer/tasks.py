"""
Celery tasks for analyzing incoming logs.

Note for developers:
If you find yourself adding a new Celery task, please be aware of how Celery
determines which queue to read and write to work on that task. By default,
Celery tasks will go to a queue named "celery". If you wish to separate a task
onto a different queue (which may make it easier to see the volume of specific
waiting tasks), please be sure to update all the relevant configurations to
use that custom queue. This includes CELERY_TASK_ROUTES in config and the
Celery worker's --queues argument (see deployment-configs.yaml in shiftigrade).
"""
import itertools
import json
import logging
from decimal import Decimal

import boto3
from celery import shared_task
from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from account.models import (
    AwsAccount,
    AwsEC2InstanceDefinitions,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    InstanceEvent,
    MachineImage,
    Run)
from account.reports import normalize_runs
from account.util import (recalculate_runs, save_instance,
                          save_instance_events, save_new_aws_machine_image,
                          start_image_inspection)
from analyzer.cloudtrail import (extract_ami_tag_events,
                                 extract_ec2_instance_events)
from util import aws
from util.aws import is_windows, rewrap_aws_errors
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@shared_task
@rewrap_aws_errors
def analyze_log():
    """Read SQS Queue for log location, and parse log for events."""
    queue_url = settings.CLOUDTRAIL_EVENT_URL
    successes, failures = [], []
    for message in aws.yield_messages_from_queue(queue_url):
        success = False
        try:
            success = _process_cloudtrail_message(message)
        except AwsAccount.DoesNotExist:
            logger.warning(
                _(
                    'Encountered message %s for nonexistent account; '
                    'deleting message from queue.'
                ), message.message_id
            )
            logger.info(
                _('Deleted message body: %s'), message.body
            )
            aws.delete_messages_from_queue(queue_url, [message])
            continue
        except Exception as e:
            logger.exception(_(
                'Unexpected error in log processing: %s'
            ), e)
        if success:
            logger.info(_(
                'Successfully processed message id %s; deleting from queue.'
            ), message.message_id)
            aws.delete_messages_from_queue(queue_url, [message])
            successes.append(message)
        else:
            logger.error(_(
                'Failed to process message id %s; leaving on queue.'
            ), message.message_id)
            logger.debug(_(
                'Failed message body is: %s'
            ), message.body)
            failures.append(message)
    return successes, failures


@shared_task
def process_instance_event(event):
    """Process instance events that have been saved during log analysis."""
    after_run = Q(start_time__gt=event.occurred_at)
    during_run = Q(start_time__lte=event.occurred_at,
                   end_time__gt=event.occurred_at)
    during_run_no_end = Q(start_time__lte=event.occurred_at,
                          end_time=None)

    filters = after_run | during_run | during_run_no_end
    instance = AwsInstance.objects.get(id=event.instance_id)

    if Run.objects.filter(filters, instance=instance).exists():
        recalculate_runs(event)
    elif event.event_type == InstanceEvent.TYPE.power_on:
        normalized_runs = normalize_runs([event])
        for index, normalized_run in enumerate(normalized_runs):
            logger.info('Processing run {} of {}'.format(
                index + 1, len(normalized_runs)))
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


def _process_cloudtrail_message(message):
    """
    Process a single CloudTrail log update's SQS message.

    Args:
        message (Message): the SQS Message object to process

    Returns:
        bool: True only if message processing completed without error.

    """
    logs = []
    extracted_messages = aws.extract_sqs_message(message)

    # Get the S3 objects referenced by the SQS messages
    for extracted_message in extracted_messages:
        bucket = extracted_message['bucket']['name']
        key = extracted_message['object']['key']
        raw_content = aws.get_object_content_from_s3(bucket, key)
        content = json.loads(raw_content)
        logs.append((content, bucket, key))
        logger.debug(
            _('Read CloudTrail log file from bucket %(bucket)s object key '
              '%(key)s'),
            {'bucket': bucket, 'key': key}
        )

    # Extract actionable details from each of the S3 log files
    instance_events = []
    ami_tag_events = []
    for content, bucket, key in logs:
        for record in content.get('Records', []):
            instance_events.extend(extract_ec2_instance_events(record))
            ami_tag_events.extend(extract_ami_tag_events(record))

    # Get supporting details from AWS so we can save our models.
    # Note: It's important that we do all AWS API loading calls here before
    # saving anything to the database. We don't want to leave database write
    # transactions open while waiting on external APIs.
    described_instances = _load_missing_instance_data(instance_events)
    described_amis = _load_missing_ami_data(instance_events, ami_tag_events)

    try:
        # Save the results
        new_images = _save_cloudtrail_activity(
            instance_events,
            ami_tag_events,
            described_instances,
            described_amis,
        )
        # Starting image inspection MUST come after all other database writes
        # so that we are confident the atomic transaction will complete.
        for ami_id, image in new_images.items():
            # Is it even possible to get here when status is *not* PENDING?
            # I don't think so, but just in case, we only want inspection to
            # start if status == PENDING.
            if image.status == image.PENDING:
                start_image_inspection(
                    described_amis[ami_id]['found_by_account_arn'],
                    ami_id,
                    described_amis[ami_id]['found_in_region'],
                )

        logger.debug(_('Saved instances and/or events to the DB.'))
        return True
    except:  # noqa: E722 because we don't know what could go wrong yet.
        logger.exception(
            _('Failed to save instances and/or events to the DB. '
              'Instance events: %(instance_events)s AMI tag events: '
              '%(ami_tag_events)s'),
            {
                'instance_events': instance_events,
                'ami_tag_events': ami_tag_events
            }
        )
        return False


def _instance_event_is_complete(instance_event):
    """Check if the instance_event is populated enough for its instance."""
    return (
        instance_event.instance_type is not None and
        instance_event.ec2_ami_id is not None
    )


def _load_missing_instance_data(instance_events):  # noqa: C901
    """
    Load additional data so we can create instances from Cloud Trail events.

    We only get the necessary instance type and AMI ID from AWS Cloud Trail for
    the "RunInstances" event upon first creation of an instance. If we didn't
    get that (for example, if an instance already existed but was stopped when
    we got the cloud account), that means we may not know about the instance
    and need to describe it before we create our record of it.

    However, there is an edge-case possibility when AWS gives us events out of
    order. If we receive an instance event *before* its "RunInstances" that
    would fully describe it, we have to describe it now even though the later
    event should eventually give us that same information. There's a super edge
    case here that means the AWS user could have also changed the type before
    we receive that initial "RunInstances" event, but we are not explicitly
    handling that scenario as of this writing.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events

    Side-effect:
        instance_events input argument may have been updated with missing
            image_id values from AWS.

    Returns:
         dict: dict of dicts from AWS describing EC2 instances that are
            referenced by the input arguments but are not present in our
            database, with the outer key being each EC2 instance's ID.

    """
    all_ec2_instance_ids = set([
        instance_event.ec2_instance_id for instance_event in instance_events
    ])
    described_instances = dict()
    defined_ec2_instance_ids = set()
    # First identify which instances DON'T need to be described because we
    # either already have them stored or at least one of instance_events has
    # enough information for it.
    for instance_event in instance_events:
        ec2_instance_id = instance_event.ec2_instance_id
        if (
            _instance_event_is_complete(instance_event) or
            ec2_instance_id in defined_ec2_instance_ids
        ):
            # This means the incoming data is sufficiently populated so we
            # should know the instance's image and type.
            defined_ec2_instance_ids.add(ec2_instance_id)
        elif AwsInstance.objects.filter(
            ec2_instance_id=instance_event.ec2_instance_id,
            machineimage__isnull=False,
        ).exists() and AwsInstanceEvent.objects.filter(
            instance__awsinstance__ec2_instance_id=ec2_instance_id,
            instance_type__isnull=False,
        ).exists():
            # This means we already know the instance's image and at least once
            # we have known the instance's type from an event.
            defined_ec2_instance_ids.add(ec2_instance_id)

    # Iterate through the instance events grouped by account and region in
    # order to minimize the number of sessions and AWS API calls.
    for (aws_account_id, region), grouped_instance_events in itertools.groupby(
        instance_events, key=lambda e: (e.aws_account_id, e.region)
    ):
        grouped_instance_events = list(grouped_instance_events)
        # Find the set of EC2 instance IDs that belong to this account+region.
        ec2_instance_ids = set(
            [e.ec2_instance_id for e in grouped_instance_events]
        ).difference(defined_ec2_instance_ids)

        if not ec2_instance_ids:
            # Early continue if there are no instances we need to describe!
            continue

        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        session = aws.get_session(account.account_arn, region)

        # Get all relevant instances in one API call for this account+region.
        new_described_instances = aws.describe_instances(
            session, ec2_instance_ids, region
        )

        # How we found these instances will be important to save *later*.
        # This wouldn't be necessary if we could save these here, but we don't
        # want to mix DB transactions with external AWS API calls.
        for (
            ec2_instance_id, described_instance
        ) in new_described_instances.items():
            logger.info(
                _(
                    'Loading data for EC2 Instance %(ec2_instance_id)s for '
                    'ARN %(account_arn)s in region %(region)s'
                ),
                {
                    'ec2_instance_id': ec2_instance_id,
                    'account_arn': account.account_arn,
                    'region': region,
                },
            )
            described_instance['found_by_account_arn'] = account.account_arn
            described_instance['found_in_region'] = region
            described_instances[ec2_instance_id] = described_instance

    # Add any missing image IDs to the instance_events from the describes.
    for instance_event in instance_events:
        ec2_instance_id = instance_event.ec2_instance_id
        if (
            instance_event.ec2_ami_id is None and
            ec2_instance_id in described_instances
        ):
            described_instance = described_instances[ec2_instance_id]
            instance_event.ec2_ami_id = described_instance['ImageId']

    # We really *should* have what we need, but just in case...
    for ec2_instance_id in all_ec2_instance_ids:
        if (
            ec2_instance_id not in defined_ec2_instance_ids and
            ec2_instance_id not in described_instances
        ):
            logger.info(
                _(
                    'EC2 Instance %(ec2_instance_id)s could not be loaded '
                    'from database or AWS. It may have been terminated before '
                    'we processed it.'
                ),
                {'ec2_instance_id': ec2_instance_id},
            )

    return described_instances


def _load_missing_ami_data(instance_events, ami_tag_events):
    """
    Load additional data so we can create the AMIs for the given events.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found AMI tag events

    Returns:
         dict: Dict of dicts from AWS describing AMIs that are referenced
            by the input arguments but are not present in our database, with
            the outer key being each AMI's ID.

    """
    seen_ami_ids = set(
        [
            event.ec2_ami_id
            for event in instance_events + ami_tag_events
            if event.ec2_ami_id is not None
        ]
    )
    known_images = AwsMachineImage.objects.filter(ec2_ami_id__in=seen_ami_ids)
    known_ami_ids = set([image.ec2_ami_id for image in known_images])
    new_ami_ids = seen_ami_ids.difference(known_ami_ids)

    new_amis_keyed = set(
        [
            (event.aws_account_id, event.region, event.ec2_ami_id)
            for event in instance_events + ami_tag_events
            if event.ec2_ami_id in new_ami_ids
        ]
    )

    described_amis = dict()

    # Look up only the new AMIs that belong to each account+region group.
    for (aws_account_id, region), amis_keyed in itertools.groupby(
        new_amis_keyed, key=lambda a: (a[0], a[1])
    ):
        amis_keyed = list(amis_keyed)
        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        session = aws.get_session(account.account_arn, region)

        ami_ids = [k[2] for k in amis_keyed]

        # Get all relevant images in one API call for this account+region.
        new_described_amis = aws.describe_images(session, ami_ids, region)
        for described_ami in new_described_amis:
            ami_id = described_ami['ImageId']
            logger.info(
                _(
                    'Loading data for AMI %(ami_id)s for '
                    'ARN %(account_arn)s in region %(region)s'
                ),
                {
                    'ami_id': ami_id,
                    'account_arn': account.account_arn,
                    'region': region,
                },
            )
            described_ami['found_in_region'] = region
            described_ami['found_by_account_arn'] = account.account_arn
            described_amis[ami_id] = described_ami

    for aws_account_id, region, ec2_ami_id in new_amis_keyed:
        if ec2_ami_id not in described_amis:
            logger.info(
                _(
                    'AMI %(ec2_ami_id)s could not be found in region '
                    '%(region)s for AWS account %(aws_account_id)s.'
                ),
                {
                    'ec2_ami_id': ec2_ami_id,
                    'region': region,
                    'aws_account_id': aws_account_id,
                },
            )

    return described_amis


@transaction.atomic
def _save_cloudtrail_activity(
    instance_events, ami_tag_events, described_instances, described_images
):
    """
    Save new images and instances events found via CloudTrail to the DB.

    The order of operations here generally looks like:

        1. Save new images.
        2. Save tag changes for images.
        3. Save new instances.
        4. Save events for instances.

    Note:
        Nothing should be reaching out to AWS APIs in this function! We should
        have all the necessary information already, and this function saves all
        of it atomically in a single transaction.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found ami tag events
        described_instances (dict): described new-to-us AWS instances keyed by
            EC2 instance ID
        described_images (dict): described new-to-us AMIs keyed by AMI ID

    Returns:
        dict: Only the new images that were created in the process.

    """
    # Log some basic information about what we're saving.
    log_prefix = 'analyzer'
    all_ec2_instance_ids = set(
        [
            instance_event.ec2_instance_id
            for instance_event in instance_events
            if instance_event.ec2_instance_id is not None
        ]
    )
    logger.info(
        _(
            '%(prefix)s: EC2 Instance IDs found: %(all_ec2_instance_ids)s'
        ),
        {'prefix': log_prefix, 'all_ec2_instance_ids': all_ec2_instance_ids},
    )

    all_ami_ids = set(
        [
            instance_event.ec2_ami_id
            for instance_event in instance_events
            if instance_event.ec2_ami_id is not None
        ] + [
            ami_tag_event.ec2_ami_id
            for ami_tag_event in ami_tag_events
            if ami_tag_event.ec2_ami_id is not None
        ] + [
            ec2_ami_id
            for ec2_ami_id in described_images.keys()
        ]
    )
    logger.info(
        _(
            '%(prefix)s: EC2 AMI IDs found: %(all_ami_ids)s'
        ),
        {'prefix': log_prefix, 'all_ami_ids': all_ami_ids},
    )

    # Which images have the Windows platform?
    windows_ami_ids = {
        ami_id
        for ami_id, described_ami in described_images.items()
        if is_windows(described_ami)
    }
    logger.info(
        _(
            '%(prefix)s: Windows AMI IDs found: %(windows_ami_ids)s'
        ),
        {'prefix': log_prefix, 'windows_ami_ids': windows_ami_ids},
    )

    # Which images need tag state changes?
    ocp_tagged_ami_ids = set()
    ocp_untagged_ami_ids = set()
    for ec2_ami_id, events_info in itertools.groupby(
        ami_tag_events, key=lambda e: e.ec2_ami_id
    ):
        # Get only the most recent event for each image
        latest_event = sorted(events_info, key=lambda e: e.occurred_at)[-1]
        # IMPORTANT NOTE: This assumes all tags are the OCP tag!
        # This will need to change if we ever support other ami tags.
        if latest_event.exists:
            ocp_tagged_ami_ids.add(ec2_ami_id)
        else:
            ocp_untagged_ami_ids.add(ec2_ami_id)

    logger.info(
        _('%(prefix)s: AMIs found tagged for OCP: %(ocp_tagged_ami_ids)s'),
        {'prefix': log_prefix, 'ocp_tagged_ami_ids': ocp_tagged_ami_ids},
    )

    logger.info(
        _('%(prefix)s: AMIs found untagged for OCP: %(ocp_untagged_ami_ids)s'),
        {'prefix': log_prefix, 'ocp_untagged_ami_ids': ocp_untagged_ami_ids},
    )

    # Create only the new images.
    new_images = {}
    for ami_id, described_image in described_images.items():
        owner_id = Decimal(described_image['OwnerId'])
        name = described_image['Name']
        windows = ami_id in windows_ami_ids
        openshift = ami_id in ocp_tagged_ami_ids
        region = described_image['found_in_region']

        logger.info(
            _(
                '%(prefix)s: Saving new AMI ID %(ami_id)s in region %(region)s'
            ),
            {'prefix': log_prefix, 'ami_id': ami_id, 'region': region},
        )
        image, new = save_new_aws_machine_image(
            ami_id, name, owner_id, openshift, windows, region)
        if new and image.status is not image.INSPECTED:
            new_images[ami_id] = image

    # Create "unavailable" images for AMIs we saw referenced but that we either
    # don't have in our models or could not describe from AWS.
    seen_ami_ids = set(
        [
            described_instance['ImageId']
            for described_instance in described_instances.values()
            if described_instance.get('ImageId') is not None
        ] + [
            ami_tag_event.ec2_ami_id
            for ami_tag_event in ami_tag_events
            if ami_tag_event.ec2_ami_id is not None
        ] + [
            instance_event.ec2_ami_id
            for instance_event in instance_events
            if instance_event.ec2_ami_id is not None
        ]
    )
    described_ami_ids = set(described_images.keys())
    known_ami_ids = set(
        image.ec2_ami_id for image in AwsMachineImage.objects.filter(
            ec2_ami_id__in=list(seen_ami_ids - described_ami_ids)
        )
    )
    unavailable_ami_ids = seen_ami_ids - described_ami_ids - known_ami_ids
    for ami_id in unavailable_ami_ids:
        logger.info(_(
            'Missing image data for %s; creating UNAVAILABLE stub image.'
        ), ami_id)
        AwsMachineImage.objects.create(
            ec2_ami_id=ami_id, status=MachineImage.UNAVAILABLE
        )

    # Update images with openshift tag changes.
    if ocp_tagged_ami_ids:
        AwsMachineImage.objects.filter(
            ec2_ami_id__in=ocp_tagged_ami_ids
        ).update(openshift_detected=True)
    if ocp_untagged_ami_ids:
        AwsMachineImage.objects.filter(
            ec2_ami_id__in=ocp_untagged_ami_ids
        ).update(openshift_detected=False)

    # Save instances and their events.
    for (
        (ec2_instance_id, region, aws_account_id), events
    ) in itertools.groupby(
        instance_events,
        key=lambda e: (e.ec2_instance_id, e.region, e.aws_account_id),
    ):
        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        events = list(events)

        if ec2_instance_id in described_instances:
            instance_data = described_instances[ec2_instance_id]
        else:
            instance_data = {
                'InstanceId': ec2_instance_id,
                'ImageId': events[0].ec2_ami_id,
                'SubnetId': events[0].subnet_id,
            }
        logger.info(
            _(
                '%(prefix)s: Saving new EC2 instance ID %(ec2_instance_id)s '
                'for AWS account ID %(aws_account_id)s in region %(region)s'
            ),
            {
                'prefix': log_prefix,
                'ec2_instance_id': ec2_instance_id,
                'aws_account_id': aws_account_id,
                'region': region,
            },
        )
        instance = save_instance(
            account, instance_data, region
        )

        # Build a list of event data
        events_info = _build_events_info_for_saving(account, instance, events)
        save_instance_events(instance, instance_data, events_info)

    return new_images


def _build_events_info_for_saving(account, instance, events):
    """
    Build a list of enough information to save the relevant events.

    Of particular note here is the "if" that filters away events that seem to
    have occurred before their account was created. This can happen in some
    edge-case circumstances when the user is deleting and recreating their
    account in cloudigrade while powering off and on events in AWS. The AWS
    CloudTrail from *before* deleting the account may continue to accumulate
    events for some time since it is delayed, and when the account is recreated
    in cloudigrade, those old events may arrive, but we *should not* know about
    them. If we were to keep those events, bad things could happen because we
    may not have enough information about them (instance type, relevant image)
    to process them for reporting.

    Args:
        account (AwsAccount): the account that owns the instance
        instance (AwsInstance): the instance that generated the events
        events (list[AwsInstanceEvent]): the incoming events

    Returns:
        list[dict]: enough information to save a list of events

    """
    events_info = [
        {
            'subnet': getattr(instance, 'subnet_id', None),
            'ec2_ami_id': getattr(instance, 'image_id', None),
            'instance_type': instance_event.instance_type
            if instance_event.instance_type is not None
            else getattr(instance, 'instance_type', None),
            'event_type': instance_event.event_type,
            'occurred_at': instance_event.occurred_at,
        }
        for instance_event in events
        if parse(instance_event.occurred_at) >= account.created_at
    ]
    return events_info


@retriable_shared_task
def repopulate_ec2_instance_mapping():
    """
    Use the Boto3 pricing client to update the EC2 instancetype lookup table.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    client = boto3.client('pricing')
    paginator = client.get_paginator('get_products')
    page_iterator = paginator.paginate(
        ServiceCode='AmazonEC2',
        Filters=[
            {
                'Type': 'TERM_MATCH',
                'Field': 'productFamily',
                'Value': 'Compute Instance'
            },
        ]
    )
    logger.info(_('Getting AWS EC2 instance type information.'))
    instances = {}
    for page in page_iterator:
        for instance in page['PriceList']:
            try:
                instance_attr = json.loads(instance)['product']['attributes']

                # memory comes in formatted like: 1,952.00 GiB
                memory = float(
                    instance_attr.get('memory', 0)[:-4].replace(',', '')
                )
                vcpu = int(instance_attr.get('vcpu', 0))

                instances[instance_attr['instanceType']] = {
                    'memory': memory,
                    'vcpu': vcpu
                }
            except ValueError:
                logger.error(
                    _('Could not save instance definition for instance-type '
                      '%(instance_type)s, memory %(memory)s, vcpu %(vcpu)s.'),
                    {
                        'instance_type': instance_attr['instanceType'],
                        'memory': instance_attr.get('memory', 0),
                        'vcpu': instance_attr.get('vcpu', 0)
                    }
                )

    for instance_name, attributes in instances.items():
        AwsEC2InstanceDefinitions.objects.update_or_create(
            instance_type=instance_name,
            memory=attributes['memory'],
            vcpu=attributes['vcpu']
        )
        logger.info(_('Saved instance type %s'), instance_name)

    logger.info('Finished saving AWS EC2 instance type information.')
