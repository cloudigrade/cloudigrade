"""Utility functions for AWS models and use cases."""
import json
import logging
from decimal import Decimal

from botocore.exceptions import ClientError
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import AWS_PROVIDER_STRING, error_codes
from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    AwsMachineImageCopy,
)
from api.models import (
    CloudAccount,
    Instance,
    InstanceEvent,
    MachineImage,
    MachineImageInspectionStart,
)
from util import aws
from util.exceptions import (
    InvalidArn,
    InvalidHoundigradeJsonFormat,
    MaximumNumberOfTrailsExceededException,
)
from util.misc import get_now

logger = logging.getLogger(__name__)


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
        logger.info(
            _("%(prefix)s: found instances in region %(region_id)s"),
            {"prefix": log_prefix, "region_id": region_id},
        )
        logger.info("%s", instances)

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
            architecture = described_image.get("Architecture")
            if not architecture:
                logger.warning(
                    _(
                        "%(prefix)s: No architecture found in region %(region_id)s for "
                        "described image %(described_image)s"
                    ),
                    {
                        "prefix": log_prefix,
                        "region_id": region_id,
                        "described_image": described_image,
                    },
                )

            tag_keys = [tag.get("Key") for tag in described_image.get("Tags", [])]
            rhel_detected_by_tag = aws.RHEL_TAG in tag_keys
            openshift = aws.OPENSHIFT_TAG in tag_keys

            logger.info(
                _("%(prefix)s: Saving new AMI ID: %(ami_id)s"),
                {"prefix": log_prefix, "ami_id": ami_id},
            )
            image, new = save_new_aws_machine_image(
                ami_id,
                name,
                owner_id,
                rhel_detected_by_tag,
                openshift,
                windows,
                region,
                architecture,
            )
            if new:
                new_image_ids.append(ami_id)

    return new_image_ids


def save_new_aws_machine_image(
    ami_id,
    name,
    owner_aws_account_id,
    rhel_detected_by_tag,
    openshift_detected,
    windows_detected,
    region,
    architecture,
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
        rhel_detected_by_tag (bool) was RHEL detected by tag for this image
        openshift_detected (bool): was openshift detected for this image
        windows_detected (bool): was windows detected for this image
        region (str): Region where the image was found
        architecture (str): CPU architecture detected for this image

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
            logger.info(
                _("save_new_aws_machine_image created %(awsmachineimage)s"),
                {"awsmachineimage": awsmachineimage},
            )
            machineimage = MachineImage.objects.create(
                name=name,
                status=status,
                rhel_detected_by_tag=rhel_detected_by_tag,
                openshift_detected=openshift_detected,
                content_object=awsmachineimage,
                architecture=architecture,
            )
            logger.info(
                _("save_new_aws_machine_image created %(machineimage)s"),
                {"machineimage": machineimage},
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
        {
            "instance_id": instance_id,
            "image_id": image_id,
            "cloud_account": account,
        },
    )

    awsinstance, created = AwsInstance.objects.get_or_create(
        ec2_instance_id=instance_id,
        region=region,
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
            ec2_ami_id=image_id,
            defaults={"region": region},
        )
        if created:
            logger.info(
                _("Missing image data for %s; creating UNAVAILABLE stub image."),
                instance_data,
            )
            MachineImage.objects.create(
                status=MachineImage.UNAVAILABLE,
                content_object=awsmachineimage,
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
                {
                    "awsmachineimage_id": awsmachineimage.id,
                    "ec2_ami_id": image_id,
                },
            )
            logger.info(
                _("Missing image data for %s; creating UNAVAILABLE stub image."),
                instance_data,
            )
            MachineImage.objects.create(
                status=MachineImage.UNAVAILABLE,
                content_object=awsmachineimage,
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
    from api.tasks import process_instance_event  # local import to avoid loop

    if events is None:
        with transaction.atomic():
            occurred_at = get_now()
            instance = awsinstance.instance.get()

            latest_event = (
                InstanceEvent.objects.filter(
                    instance=instance, occurred_at__lte=occurred_at
                )
                .order_by("-occurred_at")
                .first()
            )
            # If the most recently occurred event was power_on, then adding another
            # power_on event here is redundant and can be skipped.
            if latest_event and latest_event.event_type == InstanceEvent.TYPE.power_on:
                return

            awsevent = AwsInstanceEvent.objects.create(
                subnet=instance_data.get("SubnetId"),
                instance_type=instance_data["InstanceType"],
            )
            InstanceEvent.objects.create(
                event_type=InstanceEvent.TYPE.power_on,
                occurred_at=occurred_at,
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


def create_missing_power_off_aws_instance_events(account, instances_data):
    """
    Create missing power_off for instances that are not currently running.

    If our CloudTrail log processing is working normally and isn't terribly behind
    schedule, then this function usually should have no material effect. However, since
    it's *possible* to lose messages in case of an unexpected error, this function gives
    us the ability to "fix" our runs with a new power_off that occurs "now". Without
    this, we risk letting dead instances with never-ending runs contribute erroneously
    to concurrent usage calculations for new days.
    """
    from api.tasks import process_instance_event  # local import to avoid loop

    # Build a list of currently-running instance IDs according to the described data.
    running_ec2_instance_ids = set()
    for region, instances in instances_data.items():
        for instance_data in instances:
            instance_id = instance_data.get("InstanceId")
            state_code = instance_data.get("State", {}).get("Code")
            if state_code and aws.InstanceState.is_running(state_code):
                running_ec2_instance_ids.add(instance_id)

    # Get AWS instances that we already have saved but that are *not*
    # in the set of instances running according to the described data.
    known_aws_instances = AwsInstance.objects.filter(
        instance__cloud_account=account
    ).exclude(ec2_instance_id__in=running_ec2_instance_ids)

    # Filter down that set of instances to ones whose most recent power-related event
    # is *not* power_off. This means we erroneously think they are still running.
    # Note that we're not simply looking at the last event because it might not be
    # power-related, and we only care about the power state here.
    still_running_instances = {}  # {ec2_instance_id: (Instance, AwsInstance)}
    for aws_instance in known_aws_instances:
        instance = aws_instance.instance.get()
        last_occurred_power_event = (
            InstanceEvent.objects.filter(
                instance=instance,
                event_type__in=(
                    InstanceEvent.TYPE.power_on,
                    InstanceEvent.TYPE.power_off,
                ),
            )
            .order_by("-occurred_at")
            .first()
        )
        if (
            last_occurred_power_event
            and last_occurred_power_event.event_type == InstanceEvent.TYPE.power_on
        ):
            still_running_instances[aws_instance.ec2_instance_id] = (
                instance,
                aws_instance,
            )

    occurred_at = get_now()
    event_type = InstanceEvent.TYPE.power_off
    for instance, aws_instance in still_running_instances.values():
        # Let's log this at error level for now because we should be made aware of how
        # frequently this is happening. If we are regularly creating events here, that
        # means we probably have something broken in our CloudTrail processing that is
        # losing messages!
        logger.error(
            "Adding missing InstanceEvent power_off for %(instance)s %(aws_instance)s",
            {"instance": instance, "aws_instance": aws_instance},
        )
        aws_instance_event = AwsInstanceEvent.objects.create()
        event = InstanceEvent.objects.create(
            instance=instance,
            event_type=event_type,
            occurred_at=occurred_at,
            content_object=aws_instance_event,
        )
        process_instance_event(event)


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
    # Ensure there is only one of each message.
    # If there were multiple instances using the same image, the message.append could
    # have been reached once for *each* of those multiple instances.
    # Unfortunately, dict objects are not hashable and cannot be de-duped using sets.
    # So, this ugly comprehension iterates their contents to ensure unique messages.
    messages = [dict(s) for s in set(frozenset(m.items()) for m in messages)]
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

        if machine_image.rhel_detected_by_tag:
            # If we saw a tag indicating RHEL, we choose to trust the customer and
            # short-circuit the inspection process. The customer may have set that tag
            # with the intent to prevent us from looking at the image's contents.
            logger.info(
                _(
                    "AwsMachineImage for ec2_ami_id %(ec2_ami_id)s must not start "
                    "inspection because rhel_detected_by_tag is True."
                ),
                {"ec2_ami_id": ami_id},
            )
            machine_image.status = machine_image.INSPECTED
            machine_image.save()
            return machine_image

        if (
            MachineImageInspectionStart.objects.filter(
                machineimage=machine_image
            ).count()
            > settings.MAX_ALLOWED_INSPECTION_ATTEMPTS
        ):
            logger.info(
                _("Exceeded %(count)s inspection attempts for %(ami)s"),
                {
                    "count": settings.MAX_ALLOWED_INSPECTION_ATTEMPTS,
                    "ami": ami,
                },
            )
            machine_image.status = machine_image.ERROR
            machine_image.save()
            return machine_image

        start = MachineImageInspectionStart.objects.create(machineimage=machine_image)
        logger.info(
            _(
                "MachineImageInspectionStart %(inspection_start_id)s created for "
                "MachineImage %(machine_image_id)s (AMI %(ami)s)"
            ),
            {
                "inspection_start_id": start.id,
                "machine_image_id": machine_image.id,
                "ami": ami,
            },
        )

        if machine_image.is_marketplace or machine_image.is_cloud_access:
            logger.info(
                _(
                    "Saving image %(machine_image_id)s for AMI %(ami)s as INSPECTED. "
                    "is_marketplace is %(is_marketplace)s. "
                    "is_cloud_access is %(is_cloud_access)s."
                ),
                {
                    "machine_image_id": machine_image.id,
                    "ami": ami,
                    "is_marketplace": machine_image.is_marketplace,
                    "is_cloud_access": machine_image.is_cloud_access,
                },
            )
            machine_image.status = machine_image.INSPECTED
            machine_image.save()
        else:
            # Local import to get around a circular import issue
            from api.clouds.aws.tasks import copy_ami_snapshot

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


def verify_permissions(customer_role_arn):
    """
    Verify AWS permissions.

    This function may raise ValidationError if certain verification steps fail.

    Args:
        customer_role_arn (str): ARN to access the customer's AWS account

    Note:
        This function not only verifies; it also has the side effect of configuring
        the AWS CloudTrail. This should be refactored into a more explicit operation,
        but at the time of this writing, there is no "dry run" check for CloudTrail
        operations. Callers should be aware of the risk that we may configure CloudTrail
        but somewhere else rollback our transaction, leaving that Trail orphaned.

        This function also has the side-effect of notifying sources and updating the
        application status to unavailable if we cannot complete processing normally.

    Returns:
        boolean indicating if the verification and CloudTrail setup succeeded.

    """
    aws_account_id = aws.AwsArn(customer_role_arn).account_id
    arn_str = str(customer_role_arn)

    access_verified = False
    cloudtrail_setup_complete = False

    try:
        cloud_account = CloudAccount.objects.get(
            aws_cloud_account__aws_account_id=aws_account_id
        )
        # Get the username immediately from the related user in case the user is deleted
        # while we are verifying access and configuring cloudtrail; we'll need it later
        # in order to notify sources of our error.
        username = cloud_account.user.username

        session = aws.get_session(arn_str)
        access_verified, failed_actions = aws.verify_account_access(session)
        if access_verified:
            aws.configure_cloudtrail(session, aws_account_id)
            cloudtrail_setup_complete = True
        else:
            for action in failed_actions:
                logger.info(
                    "Policy action %(action)s failed in verification for via %(arn)s",
                    {"action": action, "arn": arn_str},
                )
            error_code = error_codes.CG3000  # TODO Consider a new error code?
            error_code.notify(username, cloud_account.platform_application_id)
    except CloudAccount.DoesNotExist:
        # Failure to get CloudAccount means it was removed before this function started.
        logger.warning(
            "Cannot verify permissions because CloudAccount does not exist for %(arn)s",
            {"arn": customer_role_arn},
        )
        # Alas, we can't notify sources here since we don't have the CloudAccount which
        # is what has the required platform_application_id.
    except ClientError as error:
        # Generally only raised when we don't have access to the AWS account.
        client_error_code = error.response.get("Error", {}).get("Code")
        if client_error_code not in aws.COMMON_AWS_ACCESS_DENIED_ERROR_CODES:
            # We only expect to get those types of access errors, all of which basically
            # mean the permissions were removed by the time we made a call the AWS.
            # If we get any *other* kind of error, we need to alert ourselves about it!
            logger.error(
                "Unexpected AWS ClientError '%(code)s' in verify_permissions.",
                {"code": client_error_code},
            )
        # Irrespective of error code, log and notify sources about the access error.
        error_code = error_codes.CG3000
        error_code.log_internal_message(
            logger, {"cloud_account_id": cloud_account.id, "exception": error}
        )
        error_code.notify(username, cloud_account.platform_application_id)
    except MaximumNumberOfTrailsExceededException as error:
        error_code = error_codes.CG3001
        error_code.log_internal_message(
            logger, {"cloud_account_id": cloud_account.id, "exception": error}
        )
        error_code.notify(username, cloud_account.platform_application_id)
    except Exception as error:
        # It's unclear what could cause any other kind of exception to be raised here,
        # but we must handle anything, log/alert ourselves, and notify sources.
        logger.exception(
            "Unexpected exception in verify_permissions: %(error)s", {"error": error}
        )
        error_code = error_codes.CG3000  # TODO Consider a new error code?
        error_code.notify(username, cloud_account.platform_application_id)

    return access_verified and cloudtrail_setup_complete


def create_aws_cloud_account(
    user,
    customer_role_arn,
    cloud_account_name,
    platform_authentication_id,
    platform_application_id,
    platform_source_id,
):
    """
    Create AwsCloudAccount for the customer user.

    This function may raise ValidationError if certain verification steps fail.

    We call CloudAccount.enable after creating it, and that effectively verifies AWS
    permission and configures CloudTrail. If that fails, we must abort this creation.
    That is why we put almost everything here in a transaction.atomic() context.

    Args:
        user (django.contrib.auth.models.User): user to own the CloudAccount
        customer_role_arn (str): ARN to access the customer's AWS account
        cloud_account_name (str): the name to use for our CloudAccount
        platform_authentication_id (str): Platform Sources' Authentication object id
        platform_application_id (str): Platform Sources' Application object id
        platform_source_id (str): Platform Sources' Source object id

    Returns:
        CloudAccount the created cloud account.

    """
    logger.info(
        _(
            "Creating an AwsCloudAccount. "
            "user=%(user)s, "
            "customer_role_arn=%(customer_role_arn)s, "
            "cloud_account_name=%(cloud_account_name)s, "
            "platform_authentication_id=%(platform_authentication_id)s, "
            "platform_application_id=%(platform_application_id)s, "
            "platform_source_id=%(platform_source_id)s"
        ),
        {
            "user": user.username,
            "customer_role_arn": customer_role_arn,
            "cloud_account_name": cloud_account_name,
            "platform_authentication_id": platform_authentication_id,
            "platform_application_id": platform_application_id,
            "platform_source_id": platform_source_id,
        },
    )
    aws_account_id = aws.AwsArn(customer_role_arn).account_id
    arn_str = str(customer_role_arn)

    with transaction.atomic():
        # Verify that no AwsCloudAccount already exists with the same ARN.
        if AwsCloudAccount.objects.filter(account_arn=arn_str).exists():
            error_code = error_codes.CG1001
            existing_user_id = (
                AwsCloudAccount.objects.get(account_arn=arn_str)
                .cloud_account.get()
                .user.id
            )
            # If the CloudAccount with the duplicate ARN belongs to the same user,
            # we want to give the error code in addition to the generic message
            error_message = _notify_error_with_generic_message_for_different_user(
                error_code, existing_user_id, user, platform_application_id, arn_str
            )
            raise ValidationError({"account_arn": error_message})

        # Verify that no AwsCloudAccount already exists with the same AWS Account ID.
        if AwsCloudAccount.objects.filter(aws_account_id=aws_account_id).exists():
            error_code = error_codes.CG1002
            existing_user_id = (
                AwsCloudAccount.objects.get(aws_account_id=aws_account_id)
                .cloud_account.get()
                .user.id
            )
            error_message = _notify_error_with_generic_message_for_different_user(
                error_code, existing_user_id, user, platform_application_id, arn_str
            )
            raise ValidationError({"account_arn": error_message})

        # Verify that no CloudAccount exists with the same name.
        if CloudAccount.objects.filter(user=user, name=cloud_account_name).exists():
            error_code = error_codes.CG1003
            error_code.log_internal_message(
                logger,
                {
                    "application_id": platform_application_id,
                    "name": cloud_account_name,
                },
            )
            error_code.notify(user.username, platform_application_id)
            raise ValidationError({"name": error_code.get_message()})

        try:
            # Use get_or_create here in case there is another task running concurrently
            # that created the AwsCloudAccount at the same time.
            aws_cloud_account, created = AwsCloudAccount.objects.get_or_create(
                aws_account_id=aws_account_id, account_arn=arn_str
            )
        except IntegrityError:
            # get_or_create can throw integrity error in the case that
            # aws_account_id xor arn already exists in an account.
            error_code = error_codes.CG1002
            existing_user_id = (
                AwsCloudAccount.objects.get(aws_account_id=aws_account_id)
                .cloud_account.get()
                .user.id
            )
            error_message = _notify_error_with_generic_message_for_different_user(
                error_code, existing_user_id, user, platform_application_id, arn_str
            )
            raise ValidationError({"account_arn": error_message})

        if not created:
            # If aws_account_id and arn already exist in an account because a
            # another task created it, notify the user.
            error_code = error_codes.CG1002
            existing_user_id = (
                AwsCloudAccount.objects.get(aws_account_id=aws_account_id)
                .cloud_account.get()
                .user.id
            )
            error_message = _notify_error_with_generic_message_for_different_user(
                error_code, existing_user_id, user, platform_application_id, arn_str
            )
            raise ValidationError({"account_arn": error_message})

        cloud_account = CloudAccount.objects.create(
            user=user,
            name=cloud_account_name,
            content_object=aws_cloud_account,
            platform_application_id=platform_application_id,
            platform_authentication_id=platform_authentication_id,
            platform_source_id=platform_source_id,
        )

        # This enable call *must* be inside the transaction because we need to
        # know to rollback the transaction if anything related to enabling fails.
        # Yes, this means holding the transaction open while we wait on calls
        # to AWS.
        if cloud_account.enable() is False:
            # Enabling of cloud account failed, rolling back.
            transaction.set_rollback(True)
            raise ValidationError(
                {
                    "is_enabled": "Could not enable cloud account. "
                    "Please check your credentials."
                }
            )

    return cloud_account


def _notify_error_with_generic_message_for_different_user(
    error_code, existing_user_id, user, platform_application_id, arn_str
):
    """
    Conditionally notify the user with generic error message.

    If the CloudAccount with the duplicate AWS Account ID or duplicate ARN
    belongs to the same user, we want to give the error code in addition to the
    generic message. Otherwise give only the generic message.
    """
    error_code.log_internal_message(
        logger,
        {
            "application_id": platform_application_id,
            "arn": arn_str,
            "username": existing_user_id,
        },
    )

    if user.id == existing_user_id:
        error_message = error_code.get_message()
    else:
        error_message = error_codes.GENERIC_ACCOUNT_SETUP_ERROR_MESSAGE

    error_code.notify(user.username, platform_application_id, error_message)
    return error_message


def update_aws_cloud_account(
    cloud_account,
    customer_arn,
    account_number,
    authentication_id,
    source_id,
):
    """
    Update aws_cloud_account with the new arn.

    Args:
        cloud_account (api.models.CloudAccount)
        customer_arn (str): customer's ARN
        account_number (str): customer's account number
        authentication_id (str): Platform Sources' Authentication object id
        source_id (str): Platform Sources' Source object id
    """
    logger.info(
        _(
            "Updating an AwsCloudAccount. "
            "cloud_account=%(cloud_account)s, "
            "customer_arn=%(customer_arn)s, "
            "account_number=%(account_number)s, "
            "authentication_id=%(authentication_id)s, "
            "source_id=%(source_id)s"
        ),
        {
            "cloud_account": cloud_account,
            "customer_arn": customer_arn,
            "account_number": account_number,
            "authentication_id": authentication_id,
            "source_id": source_id,
        },
    )
    application_id = cloud_account.platform_application_id

    try:
        customer_aws_account_id = aws.AwsArn(customer_arn).account_id
    except InvalidArn:
        error = error_codes.CG1004
        error.log_internal_message(logger, {"application_id": application_id})
        error.notify(account_number, application_id)
        return

    # If the aws_account_id is different, then we disable the account,
    # delete all related instances, and then enable the account.
    # Otherwise just update the account_arn.
    if cloud_account.content_object.aws_account_id != customer_aws_account_id:
        logger.info(
            _(
                "Cloud Account with ID %(clount_id)s and aws_account_id "
                "%(old_aws_account_id)s has received an update request for ARN "
                "%(new_arn)s and aws_account_id %(new_aws_account_id)s. "
                "Since the aws_account_id is different, Cloud Account ID "
                "%(clount_id)s will be deleted. A new Cloud Account will be created "
                "with aws_account_id %(new_aws_account_id)s and arn %(new_arn)s."
            ),
            {
                "clount_id": cloud_account.id,
                "old_aws_account_id": cloud_account.content_object.aws_account_id,
                "new_aws_account_id": customer_aws_account_id,
                "new_arn": customer_arn,
            },
        )

        cloud_account.disable(power_off_instances=False)

        # Remove instances associated with the clount
        Instance.objects.filter(cloud_account=cloud_account).delete()

        try:
            customer_aws_account_id = aws.AwsArn(customer_arn).account_id
        except InvalidArn:
            error = error_codes.CG1004
            error.log_internal_message(logger, {"application_id": application_id})
            error.notify(account_number, application_id)
            return

        # Verify that no AwsCloudAccount already exists with the same ARN.
        if AwsCloudAccount.objects.filter(account_arn=customer_arn).exists():
            error_code = error_codes.CG1001
            existing_user_id = (
                AwsCloudAccount.objects.get(account_arn=customer_arn)
                .cloud_account.get()
                .user.id
            )
            # If the CloudAccount with the duplicate ARN belongs to the same user,
            # we want to give the error code in addition to the generic message
            _notify_error_with_generic_message_for_different_user(
                error_code,
                existing_user_id,
                account_number,
                application_id,
                customer_arn,
            )
            return

        # Verify that no AwsCloudAccount already exists with the same AWS Account ID.
        if AwsCloudAccount.objects.filter(
            aws_account_id=customer_aws_account_id
        ).exists():
            error_code = error_codes.CG1002
            existing_user_id = (
                AwsCloudAccount.objects.get(aws_account_id=customer_aws_account_id)
                .cloud_account.get()
                .user.id
            )
            _notify_error_with_generic_message_for_different_user(
                error_code,
                existing_user_id,
                account_number,
                application_id,
                customer_arn,
            )
            return
        cloud_account.content_object.account_arn = customer_arn
        cloud_account.content_object.aws_account_id = customer_aws_account_id
        cloud_account.content_object.save()

        cloud_account.enable()

    else:
        try:
            cloud_account.content_object.account_arn = customer_arn
            cloud_account.content_object.save()
            verify_permissions(customer_arn)
            cloud_account.enable()
        except ValidationError as e:
            logger.info(
                _("ARN %s failed validation. The Cloud Account will still be updated."),
                customer_arn,
            )
            # Tell the cloud account why we're disabling it
            cloud_account.disable(message=str(e.detail))

        logger.info(
            _("Cloud Account with ID %s has been updated with arn %s. "),
            cloud_account.id,
            customer_arn,
        )


def delete_cloudtrail(aws_cloud_account):
    """
    Delete an AwsCloudAccount's CloudTrail.

    Note:
        If the incoming AwsCloudAccount instance is being deleted, this call to
        delete_cloudtrail may occur after the DB record has been deleted, and we are
        only working with a shallow reference copy of the AwsCloudAccount. This means we
        cannot reliably load related objects (e.g. aws_cloud_account.cloud_account).

    Args:
        aws_cloud_account (api.clouds.aws.models.AwsCloudAccount): the AwsCloudAccount
            for which we should delete the CloudTrail

    Returns:
        bool True if CloudTrail was successfully deleted, else False.

    """
    cloudtrail_name = aws.get_cloudtrail_name(aws_cloud_account.cloud_account_id)

    try:
        session = aws.get_session(str(aws_cloud_account.account_arn))
        cloudtrail_session = session.client("cloudtrail")
        logger.info(
            "attempting to delete cloudtrail '%(name)s' via ARN '%(arn)s'",
            {"name": cloudtrail_name, "arn": aws_cloud_account.account_arn},
        )
        aws.delete_cloudtrail(cloudtrail_session, cloudtrail_name)
        return True

    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code")
        if error_code == "TrailNotFoundException":
            # If a cloudtrail does not exist, then we have nothing to do here!
            return True
        elif error_code in aws.COMMON_AWS_ACCESS_DENIED_ERROR_CODES:
            # We may get AccessDenied if the user deletes the AWS account or role.
            # We may get AccessDeniedException if the role or policy is broken.
            # These could result in an orphaned cloudtrail writing to our s3 bucket.
            logger.warning(
                _(
                    "AwsCloudAccount ID %(aws_cloud_account_id)s for AWS account ID "
                    "%(aws_account_id)s encountered %(error_code)s and cannot "
                    "delete cloudtrail %(cloudtrail_name)s."
                ),
                {
                    "aws_cloud_account_id": aws_cloud_account.id,
                    "aws_account_id": aws_cloud_account.cloud_account_id,
                    "error_code": error_code,
                    "cloudtrail_name": cloudtrail_name,
                },
            )
            logger.info(error)
        else:
            logger.exception(error)
            logger.error(
                _(
                    "Unexpected error %(error_code)s occurred disabling CloudTrail "
                    "%(cloudtrail_name)s for AwsCloudAccount ID "
                    "%(aws_cloud_account_id)s. "
                ),
                {
                    "error_code": error_code,
                    "cloudtrail_name": cloudtrail_name,
                    "aws_cloud_account_id": aws_cloud_account.id,
                },
            )
    return False


@transaction.atomic
def persist_aws_inspection_cluster_results(inspection_results):
    """
    Persist the aws houndigrade inspection result.

    Args:
        inspection_results (dict): A dict containing houndigrade results
    Returns:
        None
    """
    images = inspection_results.get("images")
    if images is None:
        raise InvalidHoundigradeJsonFormat(
            _("Inspection results json missing images: {}").format(inspection_results)
        )

    for image_id, image_json in images.items():
        for error in image_json.get("errors", []):
            logger.info(
                _(
                    "Error reported in inspection results for image %(image_id)s: "
                    "%(error)s"
                ),
                {"image_id": image_id, "error": error},
            )
        save_success = update_aws_image_status_inspected(
            image_id, inspection_json=json.dumps(image_json)
        )
        if not save_success:
            logger.warning(
                _(
                    "Persisting AWS inspection results for EC2 AMI ID "
                    "%(ec2_ami_id)s, but we do not have any record of it. "
                    "Inspection results are: %(inspection_json)s"
                ),
                {"ec2_ami_id": image_id, "inspection_json": image_json},
            )

    general_errors = inspection_results.get("errors", [])
    for error in general_errors:
        logger.info(_("General error reported in inspection results: %s"), error)
