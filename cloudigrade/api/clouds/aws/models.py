"""Cloudigrade API v2 Models for AWS."""
import logging

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from api import AWS_PROVIDER_STRING
from api.models import CloudAccount, MachineImage
from util.models import BaseModel

logger = logging.getLogger(__name__)
CLOUD_ACCESS_NAME_TOKEN = "-Access2"
MARKETPLACE_NAME_TOKEN = "-hourly2"


class AwsCloudAccount(BaseModel):
    """AWS Customer Cloud Account Model."""

    cloud_account = GenericRelation(
        CloudAccount, related_query_name="aws_cloud_account"
    )
    aws_account_id = models.DecimalField(
        max_digits=12, decimal_places=0, db_index=True, unique=True
    )
    account_arn = models.CharField(max_length=256, unique=True)

    @property
    def cloud_account_id(self):
        """Get the AWS Account ID for this account."""
        return str(self.aws_account_id)

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses AWS."""
        return AWS_PROVIDER_STRING

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"aws_account_id={self.aws_account_id}, "
            f"account_arn='{self.account_arn}', "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    def enable(self):
        """
        Enable this AwsCloudAccount.

        This method only handles the AWS-specific piece of enabling a cloud account.
        If you want to completely enable a cloud account, use CloudAccount.enable().

        Enabling an AwsCloudAccount has the side effect of attempting to verify our
        expected IAM permissions in the customer's AWS account and then to configure and
        enable CloudTrail in the customer's AWS account. If either of these fails, we
        raise an exception for the caller to handle. Otherwise, we proceed to perform
        the "initial" describe to discover current EC2 instances.

        Raises:
            ValidationError or ClientError from verify_permissions if it fails.
        """
        logger.info(_("Enabling %(account)s"), {"account": self})
        cloud_account = self.cloud_account.get()
        if cloud_account.is_synthetic:
            # Bypass permission verify, describe, etc. if this is a synthetic account.
            logger.info(_("Enabled synthetic AwsCloudAccount %(id)s"), {"id": self.id})
            return True

        from api.clouds.aws import util  # Avoid circular import.

        verified = util.verify_permissions(self.account_arn)
        if not verified:
            message = f"Could not enable {repr(self)}; verify_permissions failed"
            logger.info(message)
            raise ValidationError({"account_arn": message})

        logger.info(_("Finished enabling %(account)s"), {"account": self})
        return True

    def disable(self):
        """
        Disable this AwsCloudAccount.

        This method only handles the AWS-specific piece of disabling a cloud account.
        If you want to completely disable a cloud account, use CloudAccount.disable().

        Disabling an AwsCloudAccount has the side effect of attempting to delete the
        AWS CloudTrail only upon committing the transaction.  If we cannot delete the
        CloudTrail, we simply log a message and proceed regardless.
        """
        logger.info(_("Attempting to disable %(account)s"), {"account": self})
        try:
            if self.cloud_account.get().is_synthetic:
                # Bypass cloudtrail operations if this is a synthetic account.
                return
        except CloudAccount.DoesNotExist:
            # The related CloudAccount normally should always exist, but it might not if
            # we are in the middle of deleting this account and/or the AwsCloudAccount
            # has been (temporarily?) orphaned from its CloudAccount.
            pass
        transaction.on_commit(lambda: _delete_cloudtrail(self))
        logger.info(_("Finished disabling %(account)s"), {"account": self})


def _delete_cloudtrail(aws_cloud_account):
    """Delete the given AwsCloudAccount's AWS CloudTrail."""
    logger.info(
        _("Attempting _delete_cloudtrail for %(account)s"),
        {"account": aws_cloud_account},
    )
    try:
        cloud_account = aws_cloud_account.cloud_account.get()
        if cloud_account.is_enabled:
            logger.warning(
                _(
                    "Aborting _delete_cloudtrail because CloudAccount ID "
                    "%(cloud_account_id)s is enabled."
                ),
                {"cloud_account_id": cloud_account.id},
            )
            return
    except CloudAccount.DoesNotExist:
        pass

    from api.clouds.aws import util  # Avoid circular import.

    if not util.delete_cloudtrail(aws_cloud_account):
        logger.info(
            _(
                "Failed to delete CloudTrail when disabling AwsCloudAccount ID "
                "%(aws_cloud_account_id)s (AWS account ID %(aws_account_id)s)"
            ),
            {
                "aws_cloud_account_id": aws_cloud_account.id,
                "aws_account_id": aws_cloud_account.aws_account_id,
            },
        )


class AwsMachineImage(BaseModel):
    """MachineImage model for an AWS EC2 instance."""

    NONE = "none"
    WINDOWS = "windows"
    PLATFORM_CHOICES = (
        (NONE, "None"),
        (WINDOWS, "Windows"),
    )
    machine_image = GenericRelation(
        MachineImage, related_query_name="aws_machine_image"
    )
    ec2_ami_id = models.CharField(
        max_length=256, unique=True, db_index=True, null=False, blank=False
    )
    platform = models.CharField(
        max_length=7,
        choices=PLATFORM_CHOICES,
        default=NONE,
        null=True,
    )
    owner_aws_account_id = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        null=True,
    )
    region = models.CharField(
        max_length=256,
        null=True,
        blank=True,
    )
    aws_marketplace_image = models.BooleanField(default=False)
    product_codes = models.JSONField(null=True)
    platform_details = models.CharField(max_length=256, null=True, blank=True)
    usage_operation = models.CharField(max_length=256, null=True, blank=True)

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        platform = str(repr(self.platform)) if self.platform is not None else None
        region = str(repr(self.region)) if self.region is not None else None
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"ec2_ami_id='{self.ec2_ami_id}', "
            f"platform={platform}, "
            f"owner_aws_account_id={self.owner_aws_account_id}, "
            f"region={region}, "
            f"aws_marketplace_image={self.aws_marketplace_image}, "
            f"product_codes={self.product_codes}, "
            f"platform_details={self.platform_details}, "
            f"usage_operation={self.usage_operation}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )


class AwsMachineImageCopy(AwsMachineImage):
    """
    Special machine image model for when we needed to make a copy.

    There are some cases in which we have to create and leave in the customer's
    AWS account a copy of an AWS image, but we need to keep track of this and
    somehow notify the customer about its existence.

    This model class extends all the same attributes of AwsMachineImage but
    adds a foreign key to point to the original reference image from which this
    copy was made.
    """

    # Placeholder field while breaking foreign keys for database cleanup.
    reference_awsmachineimage_id = models.IntegerField(db_index=False, null=True)

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        reference_awsmachineimage_id = self.reference_awsmachineimage_id
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"reference_awsmachineimage_id={reference_awsmachineimage_id}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )
