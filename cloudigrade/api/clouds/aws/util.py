"""Utility functions for AWS models and use cases."""
import logging
from decimal import Decimal

from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import AWS_PROVIDER_STRING
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
                _("Missing image data for %s; creating UNAVAILABLE stub image."),
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
                _("Missing image data for %s; creating UNAVAILABLE stub image."),
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
        from api.clouds.aws.tasks import initial_aws_describe_instances

        transaction.on_commit(
            lambda: initial_aws_describe_instances.delay(aws_cloud_account.id)
        )

    return cloud_account