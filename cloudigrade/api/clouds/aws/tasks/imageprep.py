"""Celery tasks related to preparing AWS images for inspection."""
import logging

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils.translation import gettext as _

from api.clouds.aws.models import AwsMachineImage
from api.clouds.aws.tasks import launch_inspection_instance
from api.clouds.aws.util import (
    create_aws_machine_image_copy,
    update_aws_image_status_error,
    update_aws_image_status_inspected,
)
from api.models import MachineImage
from util import aws
from util.aws import rewrap_aws_errors
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)

# Constants
CLOUD_KEY = "cloud"
CLOUD_TYPE_AWS = "aws"


@retriable_shared_task(name="api.clouds.aws.tasks.copy_ami_snapshot")
@rewrap_aws_errors
def copy_ami_snapshot(  # noqa: C901
    arn, ami_id, snapshot_region, reference_ami_id=None
):
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
    logger.info(
        _(
            "Starting copy_ami_snapshot using ARN %(arn)s for AMI %(ami_id)s "
            "in region %(snapshot_region)s (reference AMI %(reference_ami_id)s)"
        ),
        {
            "arn": arn,
            "ami_id": ami_id,
            "snapshot_region": snapshot_region,
            "reference_ami_id": reference_ami_id,
        },
    )

    if reference_ami_id:
        if not AwsMachineImage.objects.filter(ec2_ami_id=reference_ami_id).exists():
            logger.warning(
                _(
                    "AwsMachineImage with EC2 AMI ID %(ami_id)s could not be "
                    "found for copy_ami_snapshot (using reference_ami_id)."
                ),
                {"ami_id": ami_id},
            )
            return
    elif not AwsMachineImage.objects.filter(ec2_ami_id=ami_id).exists():
        logger.warning(
            _(
                "AwsMachineImage with EC2 AMI ID %(ami_id)s could not be "
                "found for copy_ami_snapshot."
            ),
            {"ami_id": ami_id},
        )
        return

    session = aws.get_session(arn)
    session_account_id = aws.get_session_account_id(session)
    ami = aws.get_ami(session, ami_id, snapshot_region)
    if not ami:
        logger.info(
            _(
                "Cannot copy AMI %(image_id)s snapshot from "
                "%(source_region)s. Saving ERROR status."
            ),
            {"image_id": ami_id, "source_region": snapshot_region},
        )
        update_aws_image_status_error(ami_id)
        return

    customer_snapshot_id = aws.get_ami_snapshot_id(ami)
    if not customer_snapshot_id:
        logger.info(
            _(
                "Cannot get customer snapshot id from AMI %(image_id)s "
                "in %(source_region)s. Saving ERROR status."
            ),
            {"image_id": ami_id, "source_region": snapshot_region},
        )
        update_aws_image_status_error(ami_id)
        return
    try:
        customer_snapshot = aws.get_snapshot(
            session, customer_snapshot_id, snapshot_region
        )

        if customer_snapshot.encrypted:
            awsimage = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
            image = awsimage.machine_image.get()
            image.is_encrypted = True
            image.status = image.ERROR
            image.save()
            logger.info(
                _(
                    'AWS snapshot "%(snapshot_id)s" for image "%(image_id)s" '
                    'found using customer ARN "%(arn)s" is encrypted and '
                    "cannot be copied."
                ),
                {
                    "snapshot_id": customer_snapshot.snapshot_id,
                    "image_id": ami.id,
                    "arn": arn,
                },
            )
            return

        logger.info(
            _(
                'AWS snapshot "%(snapshot_id)s" for image "%(image_id)s" has '
                'owner "%(owner_id)s"; current session is account '
                '"%(account_id)s"'
            ),
            {
                "snapshot_id": customer_snapshot.snapshot_id,
                "image_id": ami.id,
                "owner_id": customer_snapshot.owner_id,
                "account_id": session_account_id,
            },
        )

        if (
            customer_snapshot.owner_id != session_account_id
            and reference_ami_id is None
        ):
            logger.info(
                _(
                    "Snapshot owner is not current session account. "
                    "Copying AMI %(ami)s to customer account with ARN %(arn)s"
                ),
                {"ami": ami, "arn": arn},
            )
            copy_ami_to_customer_account.delay(arn, ami_id, snapshot_region)
            # Early return because we need to stop processing the current AMI.
            # A future call will process this new copy of the
            # current AMI instead.
            return
    except ClientError as e:
        error_code = e.response.get("Error").get("Code")
        if error_code == "InvalidSnapshot.NotFound":
            # Possibly a marketplace AMI, try to handle it by copying.
            logger.info(
                _(
                    "Encountered %(error_code)s. Possibly a marketplace AMI? "
                    "Copying AMI %(ami)s to customer account with ARN %(arn)s"
                ),
                {"error_code": error_code, "ami": ami, "arn": arn},
            )
            copy_ami_to_customer_account.delay(arn, ami_id, snapshot_region)
            return
        raise e

    aws.add_snapshot_ownership(customer_snapshot)

    snapshot_copy_id = aws.copy_snapshot(customer_snapshot_id, snapshot_region)
    logger.info(
        _(
            "%(label)s: customer_snapshot_id=%(snapshot_id)s, "
            "snapshot_copy_id=%(copy_id)s"
        ),
        {
            "label": "copy_ami_snapshot",
            "snapshot_id": customer_snapshot_id,
            "copy_id": snapshot_copy_id,
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

    # We only need the snapshot to launch the inspection now, so...
    launch_inspection_instance.delay(ami_id, snapshot_copy_id)
    # Schedule a task to cleanup the snapshot once the inspection is done.
    delete_snapshot.apply_async(
        args=[snapshot_copy_id, ami_id, snapshot_region],
        countdown=settings.INSPECTION_SNAPSHOT_CLEAN_UP_INITIAL_DELAY,
    )


@retriable_shared_task(name="api.clouds.aws.tasks.copy_ami_to_customer_account")
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
    logger.info(
        _(
            "Starting copy_ami_to_customer_account using ARN %(arn)s "
            "for reference AMI %(reference_ami_id)s "
            "in region %(snapshot_region)s"
        ),
        {
            "arn": arn,
            "reference_ami_id": reference_ami_id,
            "snapshot_region": snapshot_region,
        },
    )

    if not AwsMachineImage.objects.filter(ec2_ami_id=reference_ami_id).exists():
        logger.warning(
            _(
                "AwsMachineImage with EC2 AMI ID %(reference_ami_id)s could "
                "not be found for copy_ami_to_customer_account."
            ),
            {"reference_ami_id": reference_ami_id},
        )
        return

    session = aws.get_session(arn)
    reference_ami = aws.get_ami(session, reference_ami_id, snapshot_region)
    if not reference_ami:
        logger.info(
            _(
                "Cannot copy reference AMI %(image_id)s from "
                "%(source_region)s. Saving ERROR status."
            ),
            {"image_id": reference_ami_id, "source_region": snapshot_region},
        )
        update_aws_image_status_error(reference_ami_id)
        return

    try:
        new_ami_id = aws.copy_ami(session, reference_ami.id, snapshot_region)
        logger.info(
            _(
                "New temporary copy AMI ID is %(new_ami_id)s "
                "from reference AMI ID %(reference_ami_id)s"
            ),
            {"new_ami_id": new_ami_id, "reference_ami_id": reference_ami.id},
        )
    except ClientError as e:
        public_errors = (
            "Images from AWS Marketplace cannot be copied to another AWS account",
            "Images with EC2 BillingProduct codes cannot be copied to another "
            "AWS account",
            "You do not have permission to access the storage of this ami",
        )
        private_errors = "You do not have permission to access the storage of this ami"
        if e.response.get("Error").get("Code") == "InvalidRequest":
            error = (
                e.response.get("Error").get("Message")[:-1]
                if e.response.get("Error").get("Message").endswith(".")
                else e.response.get("Error").get("Message")
            )

            if not reference_ami.public and error in private_errors:
                # This appears to be a private AMI, shared with our customer,
                # but not given access to the storage.
                logger.warning(
                    _(
                        'Found a private image "%s" with inaccessible '
                        "storage. Saving ERROR status."
                    ),
                    reference_ami_id,
                )
                update_aws_image_status_error(reference_ami_id)
                return
            elif error in public_errors:
                # This appears to be a marketplace AMI, mark it as inspected.
                logger.info(
                    _(
                        'Found a marketplace/community image "%s", '
                        "marking as inspected"
                    ),
                    reference_ami_id,
                )
                update_aws_image_status_inspected(
                    ec2_ami_id=reference_ami_id, aws_marketplace_image=True
                )
                return

        raise e

    copy_ami_snapshot.delay(arn, new_ami_id, snapshot_region, reference_ami_id)


@retriable_shared_task(name="api.clouds.aws.tasks.remove_snapshot_ownership")
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
    ec2 = boto3.resource("ec2")

    # Wait for snapshot to be ready
    try:
        snapshot_copy = ec2.Snapshot(snapshot_copy_id)
        aws.check_snapshot_state(snapshot_copy)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") == "InvalidSnapshot.NotFound":
            logger.info(
                _(
                    "%(label)s detected snapshot_copy_id %(copy_id)s "
                    "already deleted."
                ),
                {"label": "remove_snapshot_ownership", "copy_id": snapshot_copy_id},
            )
        else:
            raise

    # Remove permissions from customer_snapshot
    logger.info(
        _("%(label)s remove ownership from customer snapshot %(snapshot_id)s"),
        {"label": "remove_snapshot_ownership", "snapshot_id": customer_snapshot_id},
    )
    session = aws.get_session(arn)
    customer_snapshot = aws.get_snapshot(
        session, customer_snapshot_id, customer_snapshot_region
    )
    aws.remove_snapshot_ownership(customer_snapshot)


@retriable_shared_task(name="api.clouds.aws.tasks.delete_snapshot")
@rewrap_aws_errors
def delete_snapshot(snapshot_copy_id, ami_id, snapshot_region):
    """
    Delete snapshot after image is inspected.

    Args:
        snapshot_copy_id (str): The id of the snapshot to delete
        ami_id (str): The id of the image that must be inspected
        snapshot_region (str): The region the snapshot resides in
    Returns:
        None: Run as an asynchronous Celery task.
    """
    clean_up = False
    try:
        ami = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = ami.machine_image.get()
        if machine_image.status == MachineImage.INSPECTED:
            clean_up = True
    except AwsMachineImage.DoesNotExist:
        logger.info(
            _(
                "%(label)s AMI ID %(ami_id)s no longer available, "
                "snapshot id %(snapshot_copy_id)s being cleaned up."
            ),
            {
                "label": "delete_snapshot",
                "ami_id": ami_id,
                "snapshot_copy_id": snapshot_copy_id,
            },
        )
        clean_up = True

    if clean_up:
        logger.info(
            _("%(label)s delete cloudigrade snapshot copy %(copy_id)s"),
            {"label": "delete_snapshot", "copy_id": snapshot_copy_id},
        )
        ec2 = boto3.resource("ec2")
        snapshot_copy = ec2.Snapshot(snapshot_copy_id)
        snapshot_copy.delete(DryRun=False)
    else:
        logger.info(
            _(
                "%(label)s cloudigrade snapshot copy "
                "%(copy_id)s not inspected yet, not deleting."
            ),
            {"label": "delete_snapshot", "copy_id": snapshot_copy_id},
        )
        delete_snapshot.apply_async(
            args=[snapshot_copy_id, ami_id, snapshot_region],
            countdown=settings.INSPECTION_SNAPSHOT_CLEAN_UP_RETRY_DELAY,
        )
