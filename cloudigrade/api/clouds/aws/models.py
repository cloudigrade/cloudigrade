"""Cloudigrade API v2 Models for AWS."""
import json
import logging

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_celery_beat.models import IntervalSchedule, PeriodicTask
from rest_framework.exceptions import ValidationError

from api import AWS_PROVIDER_STRING
from api.models import CloudAccount, Instance, InstanceEvent, MachineImage
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
    verify_task = models.OneToOneField(
        PeriodicTask, models.CASCADE, blank=True, null=True
    )

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
            f"verify_task_id='{self.verify_task_id}', "
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
        from api.clouds.aws import tasks, util  # Avoid circular import.

        verified = util.verify_permissions(self.account_arn)
        if not verified:
            message = f"Could not enable {repr(self)}; verify_permissions failed"
            logger.info(message)
            raise ValidationError({"account_arn": message})

        self._enable_verify_task()

        if not self.cloud_account.get().platform_application_is_paused:
            # Only describe if the application is *not* paused.
            transaction.on_commit(
                lambda: tasks.initial_aws_describe_instances.delay(self.id)
            )

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
        self._disable_verify_task()
        transaction.on_commit(lambda: _delete_cloudtrail(self))
        logger.info(_("Finished disabling %(account)s"), {"account": self})

    def _enable_verify_task(self):
        """Enable the given AwsCloudAccount's Verify Task."""
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=settings.SCHEDULE_VERIFY_VERIFY_TASKS_INTERVAL,
            period=IntervalSchedule.SECONDS,
        )
        verify_task, created = PeriodicTask.objects.get_or_create(
            interval=schedule,
            name=f"Verify {self.account_arn}.",
            task="api.clouds.aws.tasks.verify_account_permissions",
            kwargs=json.dumps(
                {
                    "account_arn": self.account_arn,
                }
            ),
            defaults={"start_time": self.created_at},
        )
        self.verify_task = verify_task
        self.save()
        if not created:
            verify_task.enabled = True
            verify_task.save()

    def _disable_verify_task(self):
        """Disable the given AwsCloudAccount's Verify Task."""
        if self.verify_task:
            self.verify_task.enabled = False
            self.verify_task.save()
        else:
            logger.error(
                _(
                    "Disable verify task for AWSCloudAccount ID "
                    "%(aws_cloud_account_id)s failed, as no verify "
                    "task was present. This should not be possible "
                    "as every AwsCloudAccount should have a verify task."
                ),
                {"aws_cloud_account_id": self.id},
            )


@receiver(post_delete, sender=AwsCloudAccount)
def awscloudaccount_post_delete_callback(*args, **kwargs):
    """
    Delete AwsCloudAccount.verify_task upon deleting AwsCloudAccount.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    aws_cloud_account = kwargs["instance"]

    if aws_cloud_account.verify_task:
        logger.info(
            _(
                "%(periodic_task)s is no longer used by %(aws_cloud_account)s and "
                "will be deleted."
            ),
            {
                "periodic_task": aws_cloud_account.verify_task,
                "aws_cloud_account": aws_cloud_account,
            },
        )
        aws_cloud_account.verify_task.delete()


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

    @property
    def is_cloud_access(self):
        """Indicate if the image is from Cloud Access."""
        return (
            self.machine_image.get().name is not None
            and CLOUD_ACCESS_NAME_TOKEN.lower() in self.machine_image.get().name.lower()
            and self.owner_aws_account_id in settings.RHEL_IMAGES_AWS_ACCOUNTS
        )

    @property
    def is_marketplace(self):
        """Indicate if the image is from AWS Marketplace."""
        return self.aws_marketplace_image or (
            self.machine_image.get().name is not None
            and MARKETPLACE_NAME_TOKEN.lower() in self.machine_image.get().name.lower()
            and self.owner_aws_account_id in settings.RHEL_IMAGES_AWS_ACCOUNTS
        )

    @property
    def cloud_image_id(self):
        """Get the AWS EC2 AMI ID."""
        return self.ec2_ami_id

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses AWS."""
        return AWS_PROVIDER_STRING

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

    reference_awsmachineimage = models.ForeignKey(
        AwsMachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
        related_name="+",
    )

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


class AwsInstance(BaseModel):
    """Amazon Web Services EC2 instance model."""

    instance = GenericRelation(Instance, related_query_name="aws_instance")
    ec2_instance_id = models.CharField(
        max_length=256,
        unique=True,
        db_index=True,
        null=False,
        blank=False,
    )
    region = models.CharField(
        max_length=256,
        null=False,
        blank=False,
    )

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
            f"ec2_instance_id='{self.ec2_instance_id}', "
            f"region='{self.region}', "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses AWS."""
        return AWS_PROVIDER_STRING

    @property
    def cloud_instance_id(self):
        """Get the cloud instance id."""
        return self.ec2_instance_id


class AwsInstanceEvent(BaseModel):
    """Event model for an event triggered by an AwsInstance."""

    instance_event = GenericRelation(
        InstanceEvent, related_query_name="aws_instance_event"
    )
    subnet = models.CharField(max_length=256, null=True, blank=True)
    instance_type = models.CharField(max_length=64, null=True, blank=True)

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses AWS."""
        return AWS_PROVIDER_STRING

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        subnet = str(repr(self.subnet)) if self.subnet is not None else None
        instance_type = (
            str(repr(self.instance_type)) if self.instance_type is not None else None
        )
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"subnet={subnet}, "
            f"instance_type={instance_type}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )
