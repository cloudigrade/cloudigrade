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
from util.aws import is_instance_windows, rewrap_aws_errors
from util.celery import retriable_shared_task
from util.exceptions import CloudTrailLogAnalysisMissingData

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
    aws_instances, described_images = _get_aws_data_for_trail_events(
        instance_events, ami_tag_events
    )

    try:
        # Save the results
        new_images = _save_results(instance_events,
                                   ami_tag_events,
                                   aws_instances,
                                   described_images)
        # Starting image inspection MUST come after all other database writes
        # so that we are confident the atomic transaction will complete.
        for image_id, image_data in described_images.items():
            if image_id in new_images:
                start_image_inspection(
                    image_data['found_in_account_arn'],
                    image_id,
                    image_data['found_in_region']
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


def _get_aws_data_for_trail_events(instance_events, ami_tag_events):  # noqa: C901, E501
    """
    Get additional AWS data so we can process the given event data.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found ami tag events

    Returns:
        tuple(dict, dict): Dict of AWS Instance objects keyed by instance ID
            and dict of AWS describe_image dicts keyed by image ID. These
            should provide enough information to save appropriate DB updates.

    """
    seen_aws_instances = {}
    new_described_images = {}

    known_ec2_ami_ids = set()  # growing set of IDs so we don't repeat lookups

    # Iterate through the instance events grouped by account and region in
    # order to minimize the number of sessions and AWS API calls.
    for (aws_account_id, region), _instance_events in itertools.groupby(
            instance_events, key=lambda e: (e.aws_account_id, e.region)):
        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        session = aws.get_session(account.account_arn, region)
        seen_ec2_ami_ids = set()  # set of image IDs seen in this iteration

        # Fetch each instance's latest information from AWS.
        for ec2_instance_id in set(
                [e.ec2_instance_id for e in _instance_events]
        ):
            # We only want to look up instances that are new to us
            if not AwsInstance.objects.filter(
                    ec2_instance_id=ec2_instance_id).exists():
                instance = aws.get_ec2_instance(session, ec2_instance_id)
                seen_aws_instances[ec2_instance_id] = instance

                try:
                    if instance.image_id not in known_ec2_ami_ids:
                        seen_ec2_ami_ids.add(instance.image_id)
                except AttributeError as e:
                    relevant_events = [
                        event for event in _instance_events
                        if e.ec2_instance_id == ec2_instance_id
                    ]
                    logger.info(
                        _('Instance %(instance_id)s has no image_id from AWS. '
                          'It may have been terminated before we processed it.'
                          ' Found in events: %(events)s.'
                          ),
                        {
                            'instance_id': ec2_instance_id,
                            'events': relevant_events
                        }
                    )
            else:
                seen_aws_instances[ec2_instance_id] = {
                    'InstanceId': ec2_instance_id
                }

        if not seen_ec2_ami_ids:
            continue

        # Do we already have the image in our database?
        known_ec2_ami_ids = known_ec2_ami_ids.union([
            image.ec2_ami_id for image in
            AwsMachineImage.objects.filter(ec2_ami_id__in=seen_ec2_ami_ids)
        ])
        new_ec2_ami_ids = seen_ec2_ami_ids - known_ec2_ami_ids

        if not new_ec2_ami_ids:
            continue

        # TODO What happens if an image has been deregistered by now?
        described_images = aws.describe_images(
            session, new_ec2_ami_ids, region
        )
        for image_data in described_images:
            # These bits of data will be useful in post-processing:
            image_data['found_in_account_arn'] = account.account_arn
            image_data['found_in_region'] = region
            ec2_ami_id = image_data['ImageId']
            new_described_images[ec2_ami_id] = image_data
            known_ec2_ami_ids.add(ec2_ami_id)

    # Iterate through the AMI tag events grouped by account and region in
    # order to minimize the number of sessions and AWS API calls.
    for (aws_account_id, region), _ami_tag_events in itertools.groupby(
            ami_tag_events, key=lambda e: (e.aws_account_id, e.region)):
        tag_ec2_ami_ids = set([
            ami_tag_event.ec2_ami_id
            for ami_tag_event in _ami_tag_events
        ])
        tag_ec2_ami_ids -= known_ec2_ami_ids

        # Do we already have the image in our database?
        known_ec2_ami_ids = known_ec2_ami_ids.union([
            image.ec2_ami_id for image in
            AwsMachineImage.objects.filter(ec2_ami_id__in=tag_ec2_ami_ids)
        ])
        tag_ec2_ami_ids -= known_ec2_ami_ids

        if not tag_ec2_ami_ids:
            continue

        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        session = aws.get_session(account.account_arn, region)

        # TODO What happens if an image has been deregistered by now?
        described_images = aws.describe_images(
            session, tag_ec2_ami_ids, region
        )
        for image_data in described_images:
            # These bits of data will be useful in post-processing:
            image_data['found_in_account_arn'] = account.account_arn
            image_data['found_in_region'] = region
            ec2_ami_id = image_data['ImageId']
            new_described_images[ec2_ami_id] = image_data
            known_ec2_ami_ids.add(ec2_ami_id)

    return seen_aws_instances, new_described_images


def _sanity_check_cloudtrail_findings(
    instance_events, ami_tag_events, aws_instances, described_images
):
    """
    Sanity check the CloudTrail findings before attempting to save them.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found ami tag events
        aws_instances (dict): AWS Instance objects keyed by instance ID
        described_images (dict): AWS describe_image dicts keyed by image ID
    """
    for instance_event in instance_events:
        if instance_event.ec2_instance_id not in aws_instances:
            raise CloudTrailLogAnalysisMissingData(_(
                'Missing instance data for %s'
            ), instance_event)
        try:
            ec2_ami_id = aws_instances[
                instance_event.ec2_instance_id
            ].image_id
        except AttributeError:
            logger.info(_(
                'Instance event %s has no image_id from AWS. It may have '
                'been terminated before we processed it.'
            ), instance_event)
            continue
        if (
            ec2_ami_id not in described_images and
            not AwsMachineImage.objects.filter(ec2_ami_id=ec2_ami_id).exists()
        ):
            logger.info(_(
                'Missing image data for %s; creating UNAVAILABLE stub image.'
            ), instance_event)
            AwsMachineImage.objects.create(
                ec2_ami_id=ec2_ami_id, status=MachineImage.UNAVAILABLE
            )
    for ami_tag_event in ami_tag_events:
        ec2_ami_id = ami_tag_event.ec2_ami_id
        if ec2_ami_id not in described_images and \
                not AwsMachineImage.objects.filter(
                    ec2_ami_id=ec2_ami_id).exists():
            logger.info(_(
                'Missing image data for %s; creating UNAVAILABLE stub image.'
            ), ami_tag_event)
            AwsMachineImage.objects.create(
                ec2_ami_id=ec2_ami_id, status=MachineImage.UNAVAILABLE
            )


@transaction.atomic
def _save_results(instance_events, ami_tag_events, aws_instances,
                  described_images):
    """
    Save new images and instances events found via CloudTrail to the DB.

    Note:
        Nothing should be reaching out to AWS APIs in this function! We should
        have all the necessary information already, and this function saves all
        of it atomically in a single transaction.

    Args:
        instance_events (list[CloudTrailInstanceEvent]): found instance events
        ami_tag_events (list[CloudTrailImageTagEvent]): found ami tag events
        aws_instances (dict): AWS Instance objects keyed by instance ID
        described_images (dict): AWS describe_image dicts keyed by image ID

    Returns:
        dict: Only the new images that were created in the process.

    """
    _sanity_check_cloudtrail_findings(instance_events,
                                      ami_tag_events,
                                      aws_instances,
                                      described_images)

    # Log some basic information about what we're saving.
    log_prefix = 'analyzer'
    ec2_instance_ids = set(aws_instances.keys())
    logger.info(_('%(prefix)s: all EC2 Instance IDs found: %(instance_ids)s'),
                {'prefix': log_prefix, 'instance_ids': ec2_instance_ids})
    ami_ids = set(described_images.keys())
    logger.info(_('%(prefix)s: new AMI IDs found: %(ami_ids)s'),
                {'prefix': log_prefix, 'ami_ids': ami_ids})

    # Which images have Windows based on the instance platform?
    windows_ami_ids = {
        instance.image_id
        for instance in aws_instances.values()
        if is_instance_windows(instance)
    }
    logger.info(_('%(prefix)s: Windows AMI IDs found: %(windows_ami_ids)s'),
                {'prefix': log_prefix, 'windows_ami_ids': windows_ami_ids})

    # Which images need tag state changes?
    ocp_tagged_ami_ids = set()
    ocp_untagged_ami_ids = set()
    for ec2_ami_id, events_info in itertools.groupby(
            ami_tag_events, key=lambda e: e.ec2_ami_id):
        # Get only the most recent event for each image
        latest_event = sorted(events_info, key=lambda e: e.occurred_at)[-1]
        # IMPORTANT NOTE: This assumes all tags are the OCP tag!
        # This will need to change if we ever support other ami tags.
        if latest_event.exists:
            ocp_tagged_ami_ids.add(ec2_ami_id)
        else:
            ocp_untagged_ami_ids.add(ec2_ami_id)

    # Which images do we actually need to create?
    known_ami_ids = {
        image.ec2_ami_id for image in
        AwsMachineImage.objects.filter(
            ec2_ami_id__in=list(described_images.keys())
        )
    }

    # Create only the new images.
    new_images = {}
    for ami_id, described_image in described_images.items():
        if ami_id in known_ami_ids:
            logger.info(_('%(prefix)s: Skipping known AMI ID: %(ami_id)s'),
                        {'prefix': log_prefix, 'ami_id': ami_id})
            continue

        owner_id = Decimal(described_image['OwnerId'])
        name = described_image['Name']
        windows = ami_id in windows_ami_ids
        openshift = ami_id in ocp_tagged_ami_ids
        region = described_image['found_in_region']

        logger.info(_('%(prefix)s: Saving new AMI ID: %(ami_id)s'),
                    {'prefix': log_prefix, 'ami_id': ami_id})
        image, new = save_new_aws_machine_image(
            ami_id, name, owner_id, openshift, windows, region)
        if new and image.status is not image.INSPECTED:
            new_images[ami_id] = image

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
        (ec2_instance_id, region, aws_account_id), _events
    ) in itertools.groupby(
        instance_events,
        key=lambda e: (e.ec2_instance_id, e.region, e.aws_account_id),
    ):
        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        aws_instance = aws_instances[ec2_instance_id]

        # Build a list of event data
        events_info = _build_events_info_for_saving(
            account, aws_instance, _events
        )
        instance = save_instance(account, aws_instance, region)
        save_instance_events(
            instance,
            aws_instance,
            events_info
        )

    return new_images


def _build_events_info_for_saving(account, instance, events):
    """
    Build a list of enough information to save the relevant events.

    If particular note here is the "if" that filters away events that seem to
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
