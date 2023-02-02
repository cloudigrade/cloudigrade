"""Cloudigrade API v2 Models for AWS."""
import logging

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from api import AWS_PROVIDER_STRING
from api.models import CloudAccount
from util.models import BaseModel

logger = logging.getLogger(__name__)


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
