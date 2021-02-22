"""Celery tasks related to interactions with AWS CloudTrail."""
import itertools
import json
import logging
from decimal import Decimal

from celery import shared_task
from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from api.clouds.aws.cloudtrail import (
    extract_ami_tag_events,
    extract_ec2_instance_events,
)
from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsMachineImage,
)
from api.clouds.aws.util import (
    save_instance,
    save_instance_events,
    save_new_aws_machine_image,
    start_image_inspection,
)
from api.models import (
    InstanceEvent,
    MachineImage,
)
from util import aws
from util.aws import OPENSHIFT_TAG, RHEL_TAG, is_windows, rewrap_aws_errors
from util.misc import lock_task_for_user_ids

logger = logging.getLogger(__name__)


@shared_task(name="api.clouds.aws.tasks.analyze_log")
@rewrap_aws_errors
def analyze_log():
    """Read SQS Queue for log location, and parse log for events."""
    queue_url = settings.AWS_CLOUDTRAIL_EVENT_URL
    successes, failures = [], []
    for message in aws.yield_messages_from_queue(queue_url):
        success = False
        try:
            success = _process_cloudtrail_message(message)
        except Exception as e:
            logger.exception(_("Unexpected error in log processing: %s"), e)
        if success:
            logger.info(
                _("Successfully processed message id %s; deleting from queue."),
                message.message_id,
            )
            aws.delete_messages_from_queue(queue_url, [message])
            successes.append(message)
        else:
            logger.error(
                _("Failed to process message id %s; leaving on queue."),
                message.message_id,
            )
            logger.debug(_("Failed message body is: %s"), message.body)
            failures.append(message)
    return successes, failures


def _process_cloudtrail_message(message):
    """
    Process a single CloudTrail log update's SQS message.

    This may have the side-effect of starting the inspection process for newly
    discovered images.

    Args:
        message (Message): the SQS Message object to process

    Returns:
        bool: True only if message processing completed without error.

    """
    logs = []
    extracted_messages = aws.extract_sqs_message(message)

    # Get the S3 objects referenced by the SQS messages
    for extracted_message in extracted_messages:
        bucket = extracted_message["bucket"]["name"]
        key = extracted_message["object"]["key"]
        raw_content = aws.get_object_content_from_s3(bucket, key)
        content = json.loads(raw_content)
        logs.append((content, bucket, key))
        logger.info(
            _("Read CloudTrail log file from bucket %(bucket)s object key %(key)s"),
            {"bucket": bucket, "key": key},
        )

    # Extract actionable details from each of the S3 log files
    instance_events = []
    ami_tag_events = []
    for content, bucket, key in logs:
        for record in content.get("Records", []):
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
        for ami_id, awsimage in new_images.items():
            # Is it even possible to get here when status is *not* PENDING?
            # I don't think so, but just in case, we only want inspection to
            # start if status == PENDING.
            image = awsimage.machine_image.get()
            if image.status == image.PENDING:
                start_image_inspection(
                    described_amis[ami_id]["found_by_account_arn"],
                    ami_id,
                    described_amis[ami_id]["found_in_region"],
                )

        logger.debug(_("Saved instances and/or events to the DB."))
        return True
    except:  # noqa: E722 because we don't know what could go wrong yet.
        logger.exception(
            _(
                "Failed to save instances and/or events to the DB. "
                "Instance events: %(instance_events)s AMI tag events: "
                "%(ami_tag_events)s"
            ),
            {"instance_events": instance_events, "ami_tag_events": ami_tag_events},
        )
        return False


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
    all_ec2_instance_ids = set(
        [instance_event.ec2_instance_id for instance_event in instance_events]
    )
    described_instances = dict()
    defined_ec2_instance_ids = set()
    # First identify which instances DON'T need to be described because we
    # either already have them stored or at least one of instance_events has
    # enough information for it.
    for instance_event in instance_events:
        ec2_instance_id = instance_event.ec2_instance_id
        if (
            _instance_event_is_complete(instance_event)
            or ec2_instance_id in defined_ec2_instance_ids
        ):
            # This means the incoming data is sufficiently populated so we
            # should know the instance's image and type.
            defined_ec2_instance_ids.add(ec2_instance_id)
        elif (
            AwsInstance.objects.filter(
                ec2_instance_id=instance_event.ec2_instance_id,
                instance__machine_image__isnull=False,
            ).exists()
            and InstanceEvent.objects.filter(
                instance__aws_instance__ec2_instance_id=ec2_instance_id,
                aws_instance_event__instance_type__isnull=False,
            ).exists()
        ):
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

        awsaccount = AwsCloudAccount.objects.get(aws_account_id=aws_account_id)
        session = aws.get_session(awsaccount.account_arn, region)

        # Get all relevant instances in one API call for this account+region.
        new_described_instances = aws.describe_instances(
            session, ec2_instance_ids, region
        )

        # How we found these instances will be important to save *later*.
        # This wouldn't be necessary if we could save these here, but we don't
        # want to mix DB transactions with external AWS API calls.
        for (ec2_instance_id, described_instance) in new_described_instances.items():
            logger.info(
                _(
                    "Loading data for EC2 Instance %(ec2_instance_id)s for "
                    "ARN %(account_arn)s in region %(region)s"
                ),
                {
                    "ec2_instance_id": ec2_instance_id,
                    "account_arn": awsaccount.account_arn,
                    "region": region,
                },
            )
            described_instance["found_by_account_arn"] = awsaccount.account_arn
            described_instance["found_in_region"] = region
            described_instances[ec2_instance_id] = described_instance

    # Add any missing image IDs to the instance_events from the describes.
    for instance_event in instance_events:
        ec2_instance_id = instance_event.ec2_instance_id
        if instance_event.ec2_ami_id is None and ec2_instance_id in described_instances:
            described_instance = described_instances[ec2_instance_id]
            instance_event.ec2_ami_id = described_instance["ImageId"]

    # We really *should* have what we need, but just in case...
    for ec2_instance_id in all_ec2_instance_ids:
        if (
            ec2_instance_id not in defined_ec2_instance_ids
            and ec2_instance_id not in described_instances
        ):
            logger.info(
                _(
                    "EC2 Instance %(ec2_instance_id)s could not be loaded "
                    "from database or AWS. It may have been terminated before "
                    "we processed it."
                ),
                {"ec2_instance_id": ec2_instance_id},
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
        awsaccount = AwsCloudAccount.objects.get(aws_account_id=aws_account_id)
        session = aws.get_session(awsaccount.account_arn, region)

        ami_ids = [k[2] for k in amis_keyed]

        # Get all relevant images in one API call for this account+region.
        new_described_amis = aws.describe_images(session, ami_ids, region)
        for described_ami in new_described_amis:
            ami_id = described_ami["ImageId"]
            logger.info(
                _(
                    "Loading data for AMI %(ami_id)s for "
                    "ARN %(account_arn)s in region %(region)s"
                ),
                {
                    "ami_id": ami_id,
                    "account_arn": awsaccount.account_arn,
                    "region": region,
                },
            )
            described_ami["found_in_region"] = region
            described_ami["found_by_account_arn"] = awsaccount.account_arn
            described_amis[ami_id] = described_ami

    for aws_account_id, region, ec2_ami_id in new_amis_keyed:
        if ec2_ami_id not in described_amis:
            logger.info(
                _(
                    "AMI %(ec2_ami_id)s could not be found in region "
                    "%(region)s for AWS account %(aws_account_id)s."
                ),
                {
                    "ec2_ami_id": ec2_ami_id,
                    "region": region,
                    "aws_account_id": aws_account_id,
                },
            )

    return described_amis


@transaction.atomic  # noqa: C901
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
    log_prefix = "analyzer"

    # Lock all user accounts related to the instance events being processed.
    # A user can only run one task at a time.
    all_user_ids = set(
        [
            AwsCloudAccount.objects.get(aws_account_id=instance_event.aws_account_id)
            .cloud_account.get()
            .user.id
            for instance_event in instance_events
        ]
        + [
            AwsCloudAccount.objects.get(aws_account_id=ami_tag_event.aws_account_id)
            .cloud_account.get()
            .user.id
            for ami_tag_event in ami_tag_events
        ]
    )
    with lock_task_for_user_ids(all_user_ids):

        # Save instances and their events.
        all_ec2_instance_ids = set(
            [
                instance_event.ec2_instance_id
                for instance_event in instance_events
                if instance_event.ec2_instance_id is not None
            ]
        )
        logger.info(
            _("%(prefix)s: EC2 Instance IDs found: %(all_ec2_instance_ids)s"),
            {"prefix": log_prefix, "all_ec2_instance_ids": all_ec2_instance_ids},
        )

        all_ami_ids = set(
            [
                instance_event.ec2_ami_id
                for instance_event in instance_events
                if instance_event.ec2_ami_id is not None
            ]
            + [
                ami_tag_event.ec2_ami_id
                for ami_tag_event in ami_tag_events
                if ami_tag_event.ec2_ami_id is not None
            ]
            + [ec2_ami_id for ec2_ami_id in described_images.keys()]
        )
        logger.info(
            _("%(prefix)s: EC2 AMI IDs found: %(all_ami_ids)s"),
            {"prefix": log_prefix, "all_ami_ids": all_ami_ids},
        )

        # Which images have the Windows platform?
        windows_ami_ids = {
            ami_id
            for ami_id, described_ami in described_images.items()
            if is_windows(described_ami)
        }
        logger.info(
            _("%(prefix)s: Windows AMI IDs found: %(windows_ami_ids)s"),
            {"prefix": log_prefix, "windows_ami_ids": windows_ami_ids},
        )

        # Which images need tag state changes?
        ocp_tagged_ami_ids, ocp_untagged_ami_ids = _extract_ami_ids_by_tag_change(
            ami_tag_events, OPENSHIFT_TAG
        )
        logger.info(
            _("%(prefix)s: AMIs found tagged for OCP: %(ocp_tagged_ami_ids)s"),
            {"prefix": log_prefix, "ocp_tagged_ami_ids": ocp_tagged_ami_ids},
        )
        logger.info(
            _("%(prefix)s: AMIs found untagged for OCP: %(ocp_untagged_ami_ids)s"),
            {"prefix": log_prefix, "ocp_untagged_ami_ids": ocp_untagged_ami_ids},
        )

        rhel_tagged_ami_ids, rhel_untagged_ami_ids = _extract_ami_ids_by_tag_change(
            ami_tag_events, RHEL_TAG
        )
        logger.info(
            _("%(prefix)s: AMIs found tagged for RHEL: %(rhel_tagged_ami_ids)s"),
            {"prefix": log_prefix, "rhel_tagged_ami_ids": rhel_tagged_ami_ids},
        )
        logger.info(
            _("%(prefix)s: AMIs found untagged for RHEL: %(rhel_untagged_ami_ids)s"),
            {"prefix": log_prefix, "rhel_untagged_ami_ids": rhel_untagged_ami_ids},
        )

        # Create only the new images.
        new_images = {}
        for ami_id, described_image in described_images.items():
            owner_id = Decimal(described_image["OwnerId"])
            name = described_image["Name"]
            architecture = described_image.get("Architecture")
            windows = ami_id in windows_ami_ids
            rhel_detected_by_tag = ami_id in rhel_tagged_ami_ids
            openshift_detected = ami_id in ocp_tagged_ami_ids
            region = described_image["found_in_region"]

            logger.info(
                _("%(prefix)s: Saving new AMI ID %(ami_id)s in region %(region)s"),
                {"prefix": log_prefix, "ami_id": ami_id, "region": region},
            )
            awsimage, new = save_new_aws_machine_image(
                ami_id,
                name,
                owner_id,
                rhel_detected_by_tag,
                openshift_detected,
                windows,
                region,
                architecture,
            )

            image = awsimage.machine_image.get()
            if new and image.status is not image.INSPECTED:
                new_images[ami_id] = awsimage

        # Create "unavailable" images for AMIs we saw referenced but that we either
        # don't have in our models or could not describe from AWS.
        seen_ami_ids = set(
            [
                described_instance["ImageId"]
                for described_instance in described_instances.values()
                if described_instance.get("ImageId") is not None
            ]
            + [
                ami_tag_event.ec2_ami_id
                for ami_tag_event in ami_tag_events
                if ami_tag_event.ec2_ami_id is not None
            ]
            + [
                instance_event.ec2_ami_id
                for instance_event in instance_events
                if instance_event.ec2_ami_id is not None
            ]
        )
        described_ami_ids = set(described_images.keys())
        known_ami_ids = set(
            image.ec2_ami_id
            for image in AwsMachineImage.objects.filter(
                ec2_ami_id__in=list(seen_ami_ids - described_ami_ids)
            )
        )
        unavailable_ami_ids = seen_ami_ids - described_ami_ids - known_ami_ids
        for ami_id in unavailable_ami_ids:
            logger.info(
                _("Missing image data for %s; creating UNAVAILABLE stub image."), ami_id
            )
            with transaction.atomic():
                awsmachineimage = AwsMachineImage.objects.create(ec2_ami_id=ami_id)
                MachineImage.objects.create(
                    status=MachineImage.UNAVAILABLE, content_object=awsmachineimage
                )
                awsmachineimage.machine_image.get()

        # Update images with openshift tag changes.
        if ocp_tagged_ami_ids:
            MachineImage.objects.filter(
                aws_machine_image__ec2_ami_id__in=ocp_tagged_ami_ids
            ).update(openshift_detected=True)
        if ocp_untagged_ami_ids:
            MachineImage.objects.filter(
                aws_machine_image__ec2_ami_id__in=ocp_untagged_ami_ids
            ).update(openshift_detected=False)

        # Update images with RHEL tag changes.
        if rhel_tagged_ami_ids:
            MachineImage.objects.filter(
                aws_machine_image__ec2_ami_id__in=rhel_tagged_ami_ids
            ).update(rhel_detected_by_tag=True)
        if rhel_untagged_ami_ids:
            MachineImage.objects.filter(
                aws_machine_image__ec2_ami_id__in=rhel_untagged_ami_ids
            ).update(rhel_detected_by_tag=False)

        # Save instances and their events.
        for ((ec2_instance_id, region, aws_account_id), events) in itertools.groupby(
            instance_events,
            key=lambda e: (e.ec2_instance_id, e.region, e.aws_account_id),
        ):
            events = list(events)

            if ec2_instance_id in described_instances:
                instance_data = described_instances[ec2_instance_id]
            else:
                instance_data = {
                    "InstanceId": ec2_instance_id,
                    "ImageId": events[0].ec2_ami_id,
                    "SubnetId": events[0].subnet_id,
                }
            logger.info(
                _(
                    "%(prefix)s: Saving new EC2 instance ID %(ec2_instance_id)s "
                    "for AWS account ID %(aws_account_id)s in region %(region)s"
                ),
                {
                    "prefix": log_prefix,
                    "ec2_instance_id": ec2_instance_id,
                    "aws_account_id": aws_account_id,
                    "region": region,
                },
            )

            awsaccount = AwsCloudAccount.objects.get(aws_account_id=aws_account_id)
            account = awsaccount.cloud_account.get()
            instance = save_instance(account, instance_data, region)

            # Build a list of event data
            events_info = _build_events_info_for_saving(account, instance, events)
            save_instance_events(instance, instance_data, events_info)

    return new_images


def _extract_ami_ids_by_tag_change(ami_tag_events, tag):
    """
    Extract the AMI IDs from a list of events that have tag-related changes.

    If the same AMI has changed multiple times for the same tag, we only care about
    the most recent change. For example, if an AMI creates and then deletes the tag, the
    net effect is that the tag was deleted, and the AMI ID should only be included in
    the set of "untagged AMI IDs".

    Args:
        ami_tag_events list(CloudTrailImageTagEvent): list of CloudTrailImageTagEvents
        tag (str): the tag for filtering

    Returns:
        tuple (set, set). First value is the set of AMI IDs where the tag was created,
        and the second is the set of AMI IDs where the tag was deleted.

    """
    tagged_ami_ids = set()
    untagged_ami_ids = set()
    for ec2_ami_id, events_info in itertools.groupby(
        ami_tag_events, key=lambda e: e.ec2_ami_id
    ):
        ordered_events = sorted(
            itertools.filterfalse(lambda e: e.tag != tag, events_info),
            key=lambda e: e.occurred_at,
        )
        for event in ordered_events[::-1]:
            # stop looking for tag changes after we find one.
            if ec2_ami_id not in tagged_ami_ids and ec2_ami_id not in untagged_ami_ids:
                if event.exists:
                    tagged_ami_ids.add(ec2_ami_id)
                else:
                    untagged_ami_ids.add(ec2_ami_id)
    return tagged_ami_ids, untagged_ami_ids


def _instance_event_is_complete(instance_event):
    """Check if the instance_event is populated enough for its instance."""
    return (
        instance_event.instance_type is not None
        and instance_event.ec2_ami_id is not None
    )


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
        account (CloudAccount): the account that owns the instance
        instance (Instance): the instance that generated the events
        events (list[CloudTrailInstanceEvent]): the incoming events

    Returns:
        list[dict]: enough information to save a list of events

    """
    events_info = [
        {
            "subnet": getattr(instance, "subnet_id", None),
            "ec2_ami_id": getattr(instance, "image_id", None),
            "instance_type": instance_event.instance_type
            if instance_event.instance_type is not None
            else getattr(instance, "instance_type", None),
            "event_type": instance_event.event_type,
            "occurred_at": instance_event.occurred_at,
        }
        for instance_event in events
        if parse(instance_event.occurred_at) >= account.created_at
    ]
    return events_info
