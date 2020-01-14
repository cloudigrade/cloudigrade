"""Utility functions."""
import collections
import itertools
import logging
import math
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
import jsonpickle
from botocore.exceptions import ClientError
from dateutil import tz
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import AWS_PROVIDER_STRING
from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsEC2InstanceDefinition,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    AwsMachineImageCopy,
)
from api.models import (
    CloudAccount,
    ConcurrentUsage,
    Instance,
    InstanceEvent,
    MachineImage,
    MachineImageInspectionStart,
    Run,
)
from util import aws
from util.misc import get_now, get_today

logger = logging.getLogger(__name__)

SQS_SEND_BATCH_SIZE = 10  # boto3 supports sending up to 10 items.
SQS_RECEIVE_BATCH_SIZE = 10  # boto3 supports receiving of up to 10 items.

cloud_account_name_pattern = "{cloud_name}-account-{external_cloud_account_id}"


def get_last_known_instance_type(instance, before_date):
    """
    Get the last known type for the given instance.

    Important note:
        This function assumes AWS is our only cloud, and this will require
        refactoring in order to determine the type from other cloud events.

    Args:
        instance (Instance): instance to check
        before_date (datetime.datetime): cutoff for checking events for type

    Returns:
        str: The last known instance type or None if no type is found.

    """
    # raise Exception
    event = (
        InstanceEvent.objects.filter(
            instance=instance,
            occurred_at__lte=before_date,
            aws_instance_event__instance_type__isnull=False,
        )
        .order_by("-occurred_at")
        .first()
    )
    if event is None:
        logger.error(
            _("Could not find any type for %(instance)s by %(before_date)s"),
            {"instance": instance, "before_date": before_date},
        )
        return None
    return event.content_object.instance_type


NormalizedRun = collections.namedtuple(
    "NormalizedRun",
    [
        "start_time",
        "end_time",
        "image_id",
        "instance_id",
        "instance_memory",
        "instance_type",
        "instance_vcpu",
        "is_cloud_access",
        "is_encrypted",
        "is_marketplace",
        "openshift",
        "openshift_challenged",
        "openshift_detected",
        "rhel",
        "rhel_challenged",
        "rhel_detected",
    ],
)


def get_instance_type_definition(instance_type):
    """Gracefully get the definition for the instance type."""
    try:
        type_definition = (
            AwsEC2InstanceDefinition.objects.get(instance_type=instance_type)
            if instance_type
            else None
        )
    except AwsEC2InstanceDefinition.DoesNotExist:
        type_definition = None
    return type_definition


def normalize_runs(events):  # noqa: C901
    """
    Create list of "runs" with normalized event information.

    These runs should have all the relevant reporting information about when
    an instance ran for a period of time so we don't have to keep going back
    and forth through events to collect bits of information we need.

    Args:
        events (list[InstanceEvent]): list of relevant events

    Returns:
        list(NormalizedRun).

    """
    sorted_events_by_instance = itertools.groupby(
        sorted(events, key=lambda e: f"{e.instance_id}_{e.occurred_at}"),
        key=lambda e: e.instance_id,
    )

    normalized_runs = []
    for instance_id, events in sorted_events_by_instance:
        events = list(events)  # events is not subscriptable from the groupby.
        instance_type = events[
            0
        ].content_object.instance_type or get_last_known_instance_type(
            events[0].instance, events[0].occurred_at
        )
        type_definition = get_instance_type_definition(instance_type)
        start_run = None
        end_run = None
        image = Instance.objects.get(id=instance_id).machine_image

        for event in events:
            if event.event_type == event.TYPE.power_on:
                if start_run is None:
                    # Only set if not already set. Why? This allows us to
                    # handle spurious start events, as if the event sequence we
                    # receive is: "start start stop"
                    start_run = event.occurred_at
                    end_run = None
            elif event.event_type == event.TYPE.power_off:
                end_run = event.occurred_at

            if start_run and image is None:
                logger.warning(
                    _("Instance %s does not have an associated " "machine image."),
                    instance_id,
                )

            if start_run and end_run:
                # The instance completed a start-stop cycle.
                run = NormalizedRun(
                    start_time=start_run,
                    end_time=end_run,
                    image_id=image.id if image else None,
                    instance_id=instance_id,
                    instance_type=instance_type,
                    instance_memory=type_definition.memory if type_definition else None,
                    instance_vcpu=type_definition.vcpu if type_definition else None,
                    is_cloud_access=image.is_cloud_access if image else False,
                    is_encrypted=image.is_encrypted if image else False,
                    is_marketplace=image.is_marketplace if image else False,
                    openshift=image.openshift if image else False,
                    openshift_challenged=image.openshift_challenged if image else False,
                    openshift_detected=image.openshift_detected if image else False,
                    rhel=image.rhel if image else False,
                    rhel_challenged=image.rhel_challenged if image else False,
                    rhel_detected=image.rhel_detected if image else False,
                )
                normalized_runs.append(run)
                start_run = None
                end_run = None

        if start_run and not end_run:
            # When the instance was started but never stopped.
            run = NormalizedRun(
                start_time=start_run,
                end_time=None,
                image_id=image.id if image else None,
                instance_id=instance_id,
                instance_type=instance_type,
                instance_memory=type_definition.memory if type_definition else None,
                instance_vcpu=type_definition.vcpu if type_definition else None,
                is_cloud_access=image.is_cloud_access if image else False,
                is_encrypted=image.is_encrypted if image else False,
                is_marketplace=image.is_marketplace if image else False,
                openshift=image.openshift if image else False,
                openshift_challenged=image.openshift_challenged if image else False,
                openshift_detected=image.openshift_detected if image else False,
                rhel=image.rhel if image else False,
                rhel_challenged=image.rhel_challenged if image else False,
                rhel_detected=image.rhel_detected if image else False,
            )
            normalized_runs.append(run)

    return normalized_runs


def get_max_concurrent_usage(date, user_id, cloud_account_id=None):
    """
    Get maximum concurrent usage of RHEL instances in given parameters.

    This gets a pre-calculated version of the results from ConcurrentUsage. If
    you only need to calculate new results, see calculate_max_concurrent_usage.

    Args:
        date (datetime.date): the day during which we are measuring usage
        user_id (int): required filter on user
        cloud_account_id (int): optional filter on cloud account

    Returns:
        dict containing the values of maximum concurrent number of instances,
        vcpu, and memory encountered at any point during the day.

    """
    today = get_today()
    if date > today:
        # Early return stub values; we never project future calculations.
        return ConcurrentUsage(
            date=date,
            user_id=user_id,
            cloud_account_id=cloud_account_id,
            instances=0,
            instances_list=[],
            vcpu=0,
            memory=0.0,
        )

    try:
        saved_usage = ConcurrentUsage.objects.get(
            date=date, user_id=user_id, cloud_account_id=cloud_account_id
        )
    except ConcurrentUsage.DoesNotExist:
        calculate_max_concurrent_usage(
            date=date, user_id=user_id, cloud_account_id=cloud_account_id
        )
        saved_usage = ConcurrentUsage.objects.get(
            date=date, user_id=user_id, cloud_account_id=cloud_account_id
        )

    return saved_usage


def calculate_max_concurrent_usage(date, user_id, cloud_account_id=None):
    """
    Calculate maximum concurrent usage of RHEL instances in given parameters.

    This always performs a new calculation of the results based on Runs. If you
    can use pre-calculated data, see get_max_concurrent_usage.

    Furthermore, we save the calculation results to the database, deleting any
    conflicting existing calculated result in the process.

    Args:
        date (datetime.date): the day during which we are measuring usage
        user_id (int): required filter on user
        cloud_account_id (int): optional filter on cloud account

    Returns:
        ConcurrentUsage instance containing calculated max concurrent values.

    """
    queryset = Run.objects.all()
    if user_id:
        if not User.objects.filter(id=user_id).exists():
            # Return empty stub object if user doesn't exist.
            usage = ConcurrentUsage(
                date=date,
                user_id=user_id,
                cloud_account_id=cloud_account_id,
                instances=0,
                vcpu=0,
                memory=0.0,
                instances_list=[],
            )
            return usage
        queryset = queryset.filter(instance__cloud_account__user__id=user_id)
    if cloud_account_id:
        if not CloudAccount.objects.filter(id=cloud_account_id).exists():
            # Return empty stub object if account doesn't exist.
            usage = ConcurrentUsage(
                date=date,
                user_id=user_id,
                cloud_account_id=cloud_account_id,
                instances=0,
                vcpu=0,
                memory=0.0,
                instances_list=[],
            )
            return usage
        queryset = queryset.filter(instance__cloud_account__id=cloud_account_id)
    start = datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=tz.tzutc())
    end = start + timedelta(days=1)

    # We want to filter to Runs that have:
    # - started before (not inclusive) our end time
    # - ended at or after our start time (inclusive) or have never stopped
    runs = queryset.filter(
        Q(end_time__isnull=True) | Q(end_time__gte=start), start_time__lt=end,
    ).prefetch_related("machineimage")

    # Now that we have the Runs, we need to extract the start and stop times
    # from each Run, put them in a list, and order them chronologically. If we
    # ever want to know about concurrency for things other than RHEL, we would
    # repeat the following pattern for each other filter/condition.
    rhel_on_offs = []
    for run in runs:
        if not run.machineimage.rhel:
            continue
        rhel_on_offs.append(
            (
                run.start_time,
                True,
                run.vcpu,
                run.memory,
                run.instance.cloud_type,
                run.instance.cloud_instance_id,
                run.instance.machine_image.rhel_version,
                run.instance.machine_image.syspurpose,
            )
        )

        if run.end_time:
            rhel_on_offs.append(
                (
                    run.end_time,
                    False,
                    run.vcpu,
                    run.memory,
                    run.instance.cloud_type,
                    run.instance.cloud_instance_id,
                    run.instance.machine_image.rhel_version,
                    run.instance.machine_image.syspurpose,
                )
            )

    rhel_on_offs = sorted(rhel_on_offs, key=lambda r: r[0])

    # Now that we have the start and stop times ordered, we can easily find the
    # maximum concurrency by walking forward in time and counting up.
    current_instances, max_instances = 0, 0
    current_vcpu, max_vcpu = 0, 0
    current_memory, max_memory = 0.0, 0.0
    instances_list = []
    for (
        __,
        is_start,
        vcpu,
        memory,
        cloud_type,
        instance_id,
        rhel_version,
        syspurpose,
    ) in rhel_on_offs:
        if is_start:
            current_instances += 1
            current_vcpu += vcpu if vcpu is not None else 0
            current_memory += memory if memory is not None else 0.0
        else:
            current_instances -= 1
            current_vcpu -= vcpu if vcpu is not None else 0
            current_memory -= memory if memory is not None else 0.0
        max_instances = max(current_instances, max_instances)
        max_vcpu = max(current_vcpu, max_vcpu)
        max_memory = max(current_memory, max_memory)
        instances_list.append(
            {
                "cloud_type": cloud_type,
                "cloud_instance_id": instance_id,
                "rhel_version": rhel_version,
                "syspurpose": syspurpose,
            }
        )

    # Make sure our instances list is unique
    instances_list = [
        i for n, i in enumerate(instances_list) if i not in instances_list[n + 1 :]
    ]

    ConcurrentUsage.objects.filter(
        date=date, user_id=user_id, cloud_account_id=cloud_account_id
    ).delete()
    usage = ConcurrentUsage.objects.create(
        date=date,
        user_id=user_id,
        cloud_account_id=cloud_account_id,
        instances=max_instances,
        vcpu=max_vcpu,
        memory=max_memory,
        instances_list=instances_list,
    )
    usage.potentially_related_runs.add(*runs)
    usage.save()
    return usage


def calculate_max_concurrent_usage_from_runs(runs):
    """
    Calculate maximum concurrent usage of RHEL instances from given Runs.

    We try to find the common intersection of the given runs across the dates,
    users, and cloud accounts referenced in the given Runs.
    """
    date_user_cloud_accounts = set()

    # This nested set of for loops should find the set of all days, user_ids,
    # and cloud_account_ids that may be affected by the given Runs. All of
    # those combinations need to have their max concurrent usage calculated.
    for run in runs:
        start_date = run.start_time.date()
        if run.end_time is not None:
            end_date = run.end_time.date()
        else:
            # No end time on the run? Act like the run ends "today".
            end_date = get_today()
        # But really the end is *tomorrow* since the end is exclusive.
        end_date = end_date + timedelta(days=1)
        cloud_acount_id = run.instance.cloud_account.id
        user_id = run.instance.cloud_account.user.id
        delta_days = (end_date - start_date).days
        for offset in range(delta_days):
            date = start_date + timedelta(days=offset)
            date_user_cloud_account = (date, user_id, cloud_acount_id)
            date_user_cloud_accounts.add(date_user_cloud_account)
            date_user_no_cloud_account = (date, user_id, None)
            date_user_cloud_accounts.add(date_user_no_cloud_account)

    for date, user_id, cloud_account_id in date_user_cloud_accounts:
        calculate_max_concurrent_usage(date, user_id, cloud_account_id)


def create_new_machine_images(session, instances_data):
    """
    Create AwsMachineImage objects that have not been seen before.

    Note:
        During processing, this makes AWS API calls to describe all images
        for the instances found for each region, and we bundle bits of those
        responses with the actual AwsMachineImage creation. We do this all at
        once here to minimize the number of AWS API calls.

    Args:
        session (boto3.Session): The session that found the machine image
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance

    Returns:
        list: A list of image ids that were added to the database

    """
    log_prefix = "create_new_machine_images"
    seen_ami_ids = {
        instance["ImageId"]
        for instances in instances_data.values()
        for instance in instances
    }
    logger.info(
        _("%(prefix)s: all AMI IDs found: %(seen_ami_ids)s"),
        {"prefix": log_prefix, "seen_ami_ids": seen_ami_ids},
    )
    known_images = AwsMachineImage.objects.filter(ec2_ami_id__in=list(seen_ami_ids))
    known_ami_ids = {image.ec2_ami_id for image in known_images}
    logger.info(
        _("%(prefix)s: Skipping known AMI IDs: %(known_ami_ids)s"),
        {"prefix": log_prefix, "known_ami_ids": known_ami_ids},
    )

    new_described_images = {}
    windows_ami_ids = []

    for region_id, instances in instances_data.items():
        ami_ids = set([instance["ImageId"] for instance in instances])
        new_ami_ids = ami_ids - known_ami_ids
        if new_ami_ids:
            new_described_images[region_id] = aws.describe_images(
                session, new_ami_ids, region_id
            )
        windows_ami_ids.extend(
            {instance["ImageId"] for instance in instances if aws.is_windows(instance)}
        )
    logger.info(
        _("%(prefix)s: Windows AMI IDs found: %(windows_ami_ids)s"),
        {"prefix": log_prefix, "windows_ami_ids": windows_ami_ids},
    )

    new_image_ids = []
    for region_id, described_images in new_described_images.items():
        for described_image in described_images:
            ami_id = described_image["ImageId"]
            owner_id = Decimal(described_image["OwnerId"])
            name = described_image["Name"]
            windows = ami_id in windows_ami_ids
            region = region_id
            openshift = (
                len(
                    [
                        tag
                        for tag in described_image.get("Tags", [])
                        if tag.get("Key") == aws.OPENSHIFT_TAG
                    ]
                )
                > 0
            )

            logger.info(
                _("%(prefix)s: Saving new AMI ID: %(ami_id)s"),
                {"prefix": log_prefix, "ami_id": ami_id},
            )
            image, new = save_new_aws_machine_image(
                ami_id, name, owner_id, openshift, windows, region
            )
            if new:
                new_image_ids.append(ami_id)

    return new_image_ids


def save_new_aws_machine_image(
    ami_id, name, owner_aws_account_id, openshift_detected, windows_detected, region
):
    """
    Save a new AwsMachineImage image object.

    Note:
        If an AwsMachineImage already exists with the provided ami_id, we do
        not create a new image nor do we modify the existing one. In that case,
        we simply fetch and return the image with the matching ami_id.

    Args:
        ami_id (str): The AWS AMI ID.
        name (str): the name of the image
        owner_aws_account_id (Decimal): the AWS account ID that owns this image
        openshift_detected (bool): was openshift detected for this image
        windows_detected (bool): was windows detected for this image
        region (str): Region where the image was found

    Returns (AwsMachineImage, bool): The object representing the saved model
        and a boolean of whether it was new or not.

    """
    platform = AwsMachineImage.NONE
    status = MachineImage.PENDING
    if windows_detected:
        platform = AwsMachineImage.WINDOWS
        status = MachineImage.INSPECTED

    with transaction.atomic():
        awsmachineimage, created = AwsMachineImage.objects.get_or_create(
            ec2_ami_id=ami_id,
            defaults={
                "platform": platform,
                "owner_aws_account_id": owner_aws_account_id,
                "region": region,
            },
        )

        if created:
            MachineImage.objects.create(
                name=name,
                status=status,
                openshift_detected=openshift_detected,
                content_object=awsmachineimage,
            )

        # This should not be necessary, but we really need this to exist.
        # If it doesn't, this will kill the transaction with an exception.
        awsmachineimage.machine_image.get()

    return awsmachineimage, created


def create_initial_aws_instance_events(account, instances_data):
    """
    Create AwsInstance and AwsInstanceEvent the first time we see an instance.

    This function is a convenience helper for recording the first time we
    discover a running instance wherein we assume that "now" is the earliest
    known time that the instance was running.

    Args:
        account (CloudAccount): The account that owns the instance that spawned
            the data for these InstanceEvents.
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance
    """
    for region, instances in instances_data.items():
        for instance_data in instances:
            instance = save_instance(account, instance_data, region)
            if aws.InstanceState.is_running(instance_data["State"]["Code"]):
                save_instance_events(instance, instance_data)


@transaction.atomic()
def save_instance(account, instance_data, region):
    """
    Create or Update the instance object.

    Note: This function assumes the images related to the instance have
    already been created and saved.

    Args:
        account (CloudAccount): The account that owns the instance that spawned
            the data for this Instance.
        instance_data (dict): Dictionary containing instance information.
        region (str): AWS Region.
        events (list[dict]): List of dicts representing Events to be saved.

    Returns:
        AwsInstance: Object representing the saved instance.

    """
    instance_id = (
        instance_data.get("InstanceId")
        if isinstance(instance_data, dict)
        else getattr(instance_data, "instance_id", None)
    )
    image_id = (
        instance_data.get("ImageId")
        if isinstance(instance_data, dict)
        else getattr(instance_data, "image_id", None)
    )
    logger.info(
        _(
            "saving models for aws instance id %(instance_id)s having aws "
            "image id %(image_id)s for %(cloud_account)s"
        ),
        {"instance_id": instance_id, "image_id": image_id, "cloud_account": account,},
    )

    awsinstance, created = AwsInstance.objects.get_or_create(
        ec2_instance_id=instance_id, region=region,
    )

    if created:
        Instance.objects.create(cloud_account=account, content_object=awsinstance)

    # This should not be necessary, but we really need this to exist.
    # If it doesn't, this will kill the transaction with an exception.
    awsinstance.instance.get()

    # If for some reason we don't get the image_id, we cannot look up
    # the associated image.
    if image_id is None:
        machineimage = None
    else:
        logger.info(_("AwsMachineImage get_or_create for EC2 AMI %s"), image_id)
        awsmachineimage, created = AwsMachineImage.objects.get_or_create(
            ec2_ami_id=image_id, defaults={"region": region},
        )
        if created:
            logger.info(
                _("Missing image data for %s; creating " "UNAVAILABLE stub image."),
                instance_data,
            )
            MachineImage.objects.create(
                status=MachineImage.UNAVAILABLE, content_object=awsmachineimage,
            )
        try:
            machineimage = awsmachineimage.machine_image.get()
        except MachineImage.DoesNotExist:
            # We are not sure how this could happen. Whenever we save a new
            # AwsMachineImage, we *should* always follow up with creating
            # its paired MachineImage. Investigate if you see this error!
            logger.error(
                _(
                    "Existing AwsMachineImage %(awsmachineimage_id)s "
                    "(ec2_ami_id=%(ec2_ami_id)s) found has no "
                    "MachineImage. This should not happen!"
                ),
                {"awsmachineimage_id": awsmachineimage.id, "ec2_ami_id": image_id,},
            )
            logger.info(
                _("Missing image data for %s; creating " "UNAVAILABLE stub image."),
                instance_data,
            )
            MachineImage.objects.create(
                status=MachineImage.UNAVAILABLE, content_object=awsmachineimage,
            )
            machineimage = awsmachineimage.machine_image.get()

    if machineimage is not None:
        instance = awsinstance.instance.get()
        instance.machine_image = machineimage
        instance.save()
    return awsinstance


def save_instance_events(awsinstance, instance_data, events=None):
    """
    Save provided events, and create the instance object if it does not exist.

    Note: This function assumes the images related to the instance events have
    already been created and saved.

    Args:
        awsinstance (AwsInstance): The Instance is associated with
            these InstanceEvents.
        instance_data (dict): Dictionary containing instance information.
        region (str): AWS Region.
        events (list[dict]): List of dicts representing Events to be saved.

    Returns:
        AwsInstance: Object representing the saved instance.

    """
    from api.tasks import process_instance_event

    if events is None:
        with transaction.atomic():
            awsevent = AwsInstanceEvent.objects.create(
                subnet=instance_data["SubnetId"],
                instance_type=instance_data["InstanceType"],
            )
            InstanceEvent.objects.create(
                event_type=InstanceEvent.TYPE.power_on,
                occurred_at=get_now(),
                instance=awsinstance.instance.get(),
                content_object=awsevent,
            )
            # This get is separate from the create to ensure the relationship
            # exists correctly even though it shouldn't strictly be necessary.
            event = awsevent.instance_event.get()

        process_instance_event(event)
    else:
        logger.info(
            _("Saving %(count)s new event(s) for %(instance)s"),
            {"count": len(events), "instance": awsinstance},
        )
        events = sorted(events, key=lambda e: e["occurred_at"])

        have_instance_type = False

        for e in events:
            # Special case for "power on" events! If we have never saved the
            # instance type before, we need to try to get the type from the
            # described instance and use that on the event.
            if (
                have_instance_type is False
                and e["event_type"] == InstanceEvent.TYPE.power_on
                and e["instance_type"] is None
                and not AwsInstanceEvent.objects.filter(
                    instance_event__instance__aws_instance=awsinstance,
                    instance_event__occurred_at__lte=e["occurred_at"],
                    instance_type__isnull=False,
                ).exists()
            ):
                instance_type = instance_data.get("InstanceType")
                logger.info(
                    _(
                        "Setting type %(instance_type)s for %(event_type)s "
                        "event at %(occurred_at)s from EC2 instance ID "
                        "%(ec2_instance_id)s"
                    ),
                    {
                        "instance_type": instance_type,
                        "event_type": e.get("event_type"),
                        "occurred_at": e.get("occurred_at"),
                        "ec2_instance_id": awsinstance.ec2_instance_id,
                    },
                )
                e["instance_type"] = instance_type
                have_instance_type = True

            awsevent = AwsInstanceEvent(
                subnet=e["subnet"], instance_type=e["instance_type"]
            )
            awsevent.save()
            instance = awsinstance.instance.get()
            event = InstanceEvent(
                instance=instance,
                event_type=e["event_type"],
                occurred_at=e["occurred_at"],
                content_object=awsevent,
            )
            event.save()

            # Need to reload event from DB, otherwise occurred_at is passed
            # as a string instead of a datetime object.
            event.refresh_from_db()
            process_instance_event(event)

    return awsinstance


def recalculate_runs(event):
    """
    Take in an event and (re)calculate runs based on it.

    The simplest use case here is if the event is newer than any runs, and that
    means a new run may be created. The more complex use case is if the event
    occurred during or before existing runs, and that means any overlapping or
    future runs must be deleted and recreated.
    """
    # Get all runs that occurred after event or occurred during event.
    after_run = Q(start_time__gt=event.occurred_at)
    during_run = Q(start_time__lte=event.occurred_at, end_time__gt=event.occurred_at)
    during_run_no_end = Q(start_time__lte=event.occurred_at, end_time=None)
    filters = after_run | during_run | during_run_no_end
    runs = Run.objects.filter(filters, instance_id=event.instance_id)

    # Get the earliest time of relevant runs.
    # We can use this as a baseline to fetch all relevant events.
    # All of these runs get torched, since we recalculate them based
    # on the newest event.
    # If no runs exist in this query, this event is the start of a new run
    try:
        earliest_run = (
            runs.earliest("start_time").start_time
            if runs.earliest("start_time").start_time < event.occurred_at
            else event.occurred_at
        )
    except Run.DoesNotExist:
        if event.event_type == event.TYPE.power_on:
            normalized_runs = normalize_runs([event])
            saved_runs = []
            for index, normalized_run in enumerate(normalized_runs):
                logger.info(
                    "Processing run %(index)s of %(runs)s",
                    {"index": index + 1, "runs": len(normalized_runs)},
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
                saved_runs.append(run)
            calculate_max_concurrent_usage_from_runs(runs)
        return

    events = (
        InstanceEvent.objects.filter(
            instance_id=event.instance_id, occurred_at__gte=earliest_run
        )
        .select_related("instance")
        .order_by("occurred_at")
    )

    normalized_runs = normalize_runs(events)
    with transaction.atomic():
        runs.delete()
        saved_runs = []
        for index, normalized_run in enumerate(normalized_runs):
            logger.info(
                "Processing run %(index)s of %(runs)s",
                {"index": index + 1, "runs": len(normalized_runs)},
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
            saved_runs.append(run)
        calculate_max_concurrent_usage_from_runs(runs)


def generate_aws_ami_messages(instances_data, ami_id_list):
    """
    Format information about the machine image for messaging.

    This is a pre-step to sending messages to a message queue.

    Args:
        instances_data (dict): Dict whose keys are AWS region IDs and values
            are each a list of dictionaries that represent an instance
        ami_id_list (list): A list of machine image IDs that need
            messages generated.

    Returns:
        list[dict]: A list of message dictionaries

    """
    messages = []
    for region, instances in instances_data.items():
        for instance in instances:
            if instance["ImageId"] in ami_id_list and not aws.is_windows(instance):
                messages.append(
                    {
                        "cloud_provider": AWS_PROVIDER_STRING,
                        "region": region,
                        "image_id": instance["ImageId"],
                    }
                )
    return messages


@transaction.atomic
def start_image_inspection(arn, ami_id, region):
    """
    Start image inspection of the provided image.

    Args:
        arn (str):  The AWS Resource Number for the account with the snapshot
        ami_id (str): The AWS ID for the machine image
        region (str): The region the snapshot resides in

    Returns:
        MachineImage: Image being inspected

    """
    logger.info(
        _(
            "Starting inspection for ami %(ami_id)s in region %(region)s "
            "through arn %(arn)s"
        ),
        {"ami_id": ami_id, "region": region, "arn": arn},
    )

    try:
        ami = AwsMachineImage.objects.get(ec2_ami_id=ami_id)

        machine_image = ami.machine_image.get()
        machine_image.status = machine_image.PREPARING
        machine_image.save()

        if (
            MachineImageInspectionStart.objects.filter(
                machineimage=machine_image
            ).count()
            > settings.MAX_ALLOWED_INSPECTION_ATTEMPTS
        ):
            logger.info(
                _("Exceeded %(count)s inspection attempts for %(ami)s"),
                {"count": settings.MAX_ALLOWED_INSPECTION_ATTEMPTS, "ami": ami,},
            )
            machine_image.status = machine_image.ERROR
            machine_image.save()
            return machine_image

        MachineImageInspectionStart.objects.create(machineimage=machine_image)

        if machine_image.is_marketplace or machine_image.is_cloud_access:
            machine_image.status = machine_image.INSPECTED
            machine_image.save()
        else:
            # Local import to get around a circular import issue
            from api.tasks import copy_ami_snapshot

            copy_ami_snapshot.delay(arn, ami_id, region)

        return machine_image

    except AwsMachineImage.DoesNotExist:
        logger.warning(
            _(
                "AwsMachineImage for ec2_ami_id %(ec2_ami_id)s could not be "
                "found for start_image_inspection"
            ),
            {"ec2_ami_id": ami_id},
        )
        return

    except MachineImage.DoesNotExist:
        logger.warning(
            _(
                "MachineImage for ec2_ami_id %(ec2_ami_id)s could not be "
                "found for start_image_inspection"
            ),
            {"ec2_ami_id": ami_id},
        )
        return


def create_aws_machine_image_copy(copy_ami_id, reference_ami_id):
    """
    Create an AwsMachineImageCopy given the copy and reference AMI IDs.

    Args:
        copy_ami_id (str): the AMI IS of the copied image
        reference_ami_id (str): the AMI ID of the original reference image
    """
    with transaction.atomic():
        reference = AwsMachineImage.objects.get(ec2_ami_id=reference_ami_id)
        awsmachineimagecopy = AwsMachineImageCopy.objects.create(
            ec2_ami_id=copy_ami_id,
            owner_aws_account_id=reference.owner_aws_account_id,
            reference_awsmachineimage=reference,
        )
        MachineImage.objects.create(content_object=awsmachineimagecopy)

        # This should not be necessary, but we really need this to exist.
        # If it doesn't, this will kill the transaction with an exception.
        awsmachineimagecopy.machine_image.get()


@transaction.atomic
def get_aws_machine_image(ec2_ami_id):
    """
    Get the AwsMachineImage and its MachineImage for the given EC2 AMI ID.

    If either the AwsMachineImage or its related MachineImage object could not
    be loaded, return (None, None).

    Args:
        ec2_ami_id (str): the AWS EC2 AMI ID for the image

    Returns:
        tuple of AwsMachineImage, MachineImage or tuple None, None.

    """
    try:
        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
        machine_image = aws_machine_image.machine_image.get()
    except AwsMachineImage.DoesNotExist:
        logger.warning(
            _("AwsMachineImage for ec2_ami_id %(ec2_ami_id)s not found"),
            {"ec2_ami_id": ec2_ami_id},
        )
        return None, None
    except MachineImage.DoesNotExist:
        logger.warning(
            _("MachineImage for ec2_ami_id %(ec2_ami_id)s not found"),
            {"ec2_ami_id": ec2_ami_id},
        )
        return None, None
    return aws_machine_image, machine_image


def add_messages_to_queue(queue_name, messages):
    """
    Send messages to an SQS queue.

    Args:
        queue_name (str): The queue to add messages to
        messages (list[dict]): A list of message dictionaries. The message
            dicts will be serialized as JSON strings.
    """
    queue_url = aws.get_sqs_queue_url(queue_name)
    sqs = boto3.client("sqs")

    wrapped_messages = [_sqs_wrap_message(message) for message in messages]
    batch_count = math.ceil(len(messages) / SQS_SEND_BATCH_SIZE)

    for batch_num in range(batch_count):
        start_pos = batch_num * SQS_SEND_BATCH_SIZE
        end_pos = start_pos + SQS_SEND_BATCH_SIZE - 1
        batch = wrapped_messages[start_pos:end_pos]
        sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)


def _sqs_wrap_message(message):
    """
    Wrap the message in a dict for SQS batch sending.

    Args:
        message (object): message to encode and wrap

    Returns:
        dict: structured entry for sending to send_message_batch

    """
    return {
        "Id": str(uuid.uuid4()),
        # Yes, the outgoing message uses MessageBody, not Body.
        "MessageBody": jsonpickle.encode(message),
    }


def read_messages_from_queue(queue_name, max_count=1):
    """
    Read messages (up to max_count) from an SQS queue.

    Args:
        queue_name (str): The queue to read messages from
        max_count (int): Max number of messages to read

    Returns:
        list[object]: The de-queued messages.

    """
    queue_url = aws.get_sqs_queue_url(queue_name)
    sqs = boto3.client("sqs")
    sqs_messages = []
    max_batch_size = min(SQS_RECEIVE_BATCH_SIZE, max_count)
    for __ in range(max_count):
        # Because receive_message does *not* actually reliably return
        # MaxNumberOfMessages number of messages especially (read the docs),
        # our iteration count is actually max_count and we have some
        # conditions at the end that break us out when we reach the true end.
        new_messages = sqs.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=max_batch_size
        ).get("Messages", [])
        if len(new_messages) == 0:
            break
        sqs_messages.extend(new_messages)
        if len(sqs_messages) >= max_count:
            break
    messages = []
    for sqs_message in sqs_messages:
        try:
            unwrapped = _sqs_unwrap_message(sqs_message)
            sqs.delete_message(
                QueueUrl=queue_url, ReceiptHandle=sqs_message["ReceiptHandle"],
            )
            messages.append(unwrapped)
        except ClientError as e:
            # I'm not sure exactly what exceptions could land here, but we
            # probably should log them, stop attempting further deletes, and
            # return what we have received (and thus deleted!) so far.
            logger.error(
                _(
                    "Unexpected error when attempting to read from %(queue)s: "
                    "%(error)s"
                ),
                {"queue": queue_url, "error": getattr(e, "response", {}).get("Error")},
            )
            logger.exception(e)
            break
    return messages


def _sqs_unwrap_message(sqs_message):
    """
    Unwrap the sqs_message to get the original message.

    Args:
        sqs_message (dict): object to unwrap and decode

    Returns:
        object: the unwrapped and decoded message object

    """
    return jsonpickle.decode(
        # Yes, the response has Body, not MessageBody.
        sqs_message["Body"]
    )


def convert_param_to_int(name, value):
    """Check if a value is convertible to int.

    Args:
        name (str): The field name being validated
        value: The value to convert to int

    Returns:
        int: The int value
    Raises:
        ValidationError if value not convertable to an int

    """
    try:
        return int(value)
    except ValueError:
        error = {name: [_("{} must be an integer.".format(name))]}
        raise ValidationError(error)


def update_aws_image_status_inspected(
    ec2_ami_id, aws_marketplace_image=None, inspection_json=None
):
    """
    Set an AwsMachineImage's MachineImage status to INSPECTED.

    Args:
        ec2_ami_id (str): the AWS EC2 AMI ID of the AwsMachineImage to update.
        aws_marketplace_image (bool): optional value for aws_marketplace_image.
        inspection_json (str): optional value for inspection_json.

    Returns:
        bool True if status is successfully updated, else False.

    """
    with transaction.atomic():
        aws_machine_image, machine_image = get_aws_machine_image(ec2_ami_id)
        if not aws_machine_image:
            logger.warning(
                _(
                    "AwsMachineImage with EC2 AMI ID %(ec2_ami_id)s could not "
                    "be found for update_aws_image_status_inspected"
                ),
                {"ec2_ami_id": ec2_ami_id},
            )
            return False
        if aws_marketplace_image is not None:
            aws_machine_image.aws_marketplace_image = aws_marketplace_image
            aws_machine_image.save()
        machine_image.status = machine_image.INSPECTED
        if inspection_json is not None:
            machine_image.inspection_json = inspection_json
        machine_image.save()
    return True


def update_aws_image_status_error(ec2_ami_id):
    """
    Set an AwsMachineImage's MachineImage status to ERROR.

    Args:
        ec2_ami_id (str): the AWS EC2 AMI ID of the AwsMachineImage to update.

    Returns:
        bool True if status is successfully updated, else False.

    """
    with transaction.atomic():
        aws_machine_image, machine_image = get_aws_machine_image(ec2_ami_id)
        if not aws_machine_image:
            logger.warning(
                _(
                    "AwsMachineImage with EC2 AMI ID %(ec2_ami_id)s could not "
                    "be found for update_aws_image_status_error"
                ),
                {"ec2_ami_id": ec2_ami_id},
            )
            return False
        machine_image.status = machine_image.ERROR
        machine_image.save()
    return True


def get_standard_cloud_account_name(cloud_name, external_cloud_account_id):
    """
    Get cloudigrade's standard CloudAccount name for a given account ID.

    Args:
        cloud_name (str): cloud name (e.g. 'aws')
        external_cloud_account_id (str): customer's external cloud account id

    Returns:
        str of cloudigrade's standard CloudAccount name

    """
    return cloud_account_name_pattern.format(
        cloud_name=cloud_name, external_cloud_account_id=external_cloud_account_id,
    )


def verify_permissions_and_create_aws_cloud_account(
    user, customer_role_arn, cloud_account_name, customer_access_key_id=None
):
    """
    Verify AWS permissions and create AwsCloudAccount for the customer user.

    This function may raise ValidationError if certain verification steps fail.

    Args:
        user (django.contrib.auth.models.User): user to own the CloudAccount
        customer_role_arn (str): ARN to access the customer's AWS account
        cloud_account_name (str): the name to use for our CloudAccount
        customer_access_key_id (str): optional customer's AWS access key ID

    Returns:
        CloudAccount the created cloud account.

    """
    aws_account_id = aws.AwsArn(customer_role_arn).account_id
    arn_str = str(customer_role_arn)

    account_exists = AwsCloudAccount.objects.filter(
        aws_account_id=aws_account_id
    ).exists()
    if account_exists:
        raise ValidationError(
            detail={
                "account_arn": [
                    _('An ARN already exists for account "{0}"').format(aws_account_id)
                ]
            }
        )

    try:
        session = aws.get_session(arn_str)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "AccessDenied":
            raise ValidationError(
                detail={
                    "account_arn": [
                        _('Permission denied for ARN "{0}"').format(arn_str)
                    ]
                }
            )
        raise
    account_verified, failed_actions = aws.verify_account_access(session)
    if account_verified:
        try:
            aws.configure_cloudtrail(session, aws_account_id)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "AccessDeniedException":
                raise ValidationError(
                    detail={
                        "account_arn": [
                            _(
                                "Access denied to create CloudTrail for " 'ARN "{0}"'
                            ).format(arn_str)
                        ]
                    }
                )
            raise
    else:
        failure_details = [_("Account verification failed.")]
        failure_details += [
            _('Access denied for policy action "{0}".').format(action)
            for action in failed_actions
        ]
        raise ValidationError(detail={"account_arn": failure_details})

    with transaction.atomic():
        # How is it possible that the AwsCloudAccount already exists?
        # The account check at the start of this function should have caught
        # any existing accounts and exited early, but another request or task
        # may have created the AwsCloudAccount while this function was talking
        # with AWS (i.e. verify_account_access) and not in a transaction.
        # We need to check for that and exit early here if it exists.
        aws_cloud_account, created = AwsCloudAccount.objects.get_or_create(
            account_arn=arn_str,
            defaults={
                "aws_account_id": aws_account_id,
                "aws_access_key_id": customer_access_key_id,
            },
        )
        if not created:
            raise ValidationError(
                detail={
                    "account_arn": [
                        _('An ARN already exists for account "{0}"').format(
                            aws_account_id
                        )
                    ]
                }
            )

        # We have to do this ugly id and ContentType lookup because Django
        # can't perform the lookup we need using GenericForeignKey.
        content_type_id = ContentType.objects.get_for_model(AwsCloudAccount).id
        cloud_account, __ = CloudAccount.objects.get_or_create(
            user=user,
            object_id=aws_cloud_account.id,
            content_type_id=content_type_id,
            defaults={"name": cloud_account_name},
        )

        # Local import to get around a circular import issue.
        from api.tasks import initial_aws_describe_instances

        transaction.on_commit(
            lambda: initial_aws_describe_instances.delay(aws_cloud_account.id)
        )

    return cloud_account
