"""Cloudigrade Account Models."""
import json
import logging
import operator

import model_utils
from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models, transaction
from django.utils.translation import gettext as _

from account import AWS_PROVIDER_STRING
from util.aws import disable_cloudtrail, get_session
from util.exceptions import CloudTrailCannotStopLogging
from util.models import BasePolymorphicModel

logger = logging.getLogger(__name__)


class Account(BasePolymorphicModel):
    """Base customer account model."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    name = models.CharField(
        max_length=256,
        null=True,
        blank=True,
        db_index=True
    )

    class Meta:
        unique_together = ('user', 'name')

    @property
    def cloud_account_id(self):
        """
        Get the external cloud provider's ID for this account.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        raise NotImplementedError

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        raise NotImplementedError


class MachineImage(BasePolymorphicModel):
    """Base model for a cloud VM image."""

    PENDING = 'pending'
    PREPARING = 'preparing'
    INSPECTING = 'inspecting'
    INSPECTED = 'inspected'
    ERROR = 'error'
    STATUS_CHOICES = (
        (PENDING, 'Pending Inspection'),
        (PREPARING, 'Preparing for Inspection'),
        (INSPECTING, 'Being Inspected'),
        (INSPECTED, 'Inspected'),
        (ERROR, 'Error'),
    )
    inspection_json = models.TextField(null=True,
                                       blank=True)
    is_encrypted = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=PENDING)
    rhel_challenged = models.BooleanField(default=False)
    openshift_detected = models.BooleanField(default=False)
    openshift_challenged = models.BooleanField(default=False)
    name = models.CharField(max_length=256, null=True, blank=True)

    @property
    def rhel(self):
        """
        Indicate if the image contains RHEL.

        Returns:
            bool: XOR of `rhel_detected` and `rhel_challenged` properties.

        """
        return operator.xor(self.rhel_detected, self.rhel_challenged)

    @property
    def rhel_enabled_repos_found(self):
        """
        Indicate if the image contains RHEL enabled repos.

        Returns:
            bool: Value of `rhel_enabled_repos_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get('rhel_enabled_repos_found', False)
        return False

    @property
    def rhel_product_certs_found(self):
        """
        Indicate if the image contains Red Hat produc certs.

        Returns:
            bool: Value of `rhel_product_certs_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get('rhel_product_certs_found', False)
        return False

    @property
    def rhel_release_files_found(self):
        """
        Indicate if the image contains RHEL release files.

        Returns:
            bool: Value of `rhel_release_files_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get('rhel_release_files_found', False)
        return False

    @property
    def rhel_signed_packages_found(self):
        """
        Indicate if the image contains Red Hat signed packages.

        Returns:
            bool: Value of `rhel_signed_packages_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get('rhel_signed_packages_found', False)
        return False

    @property
    def rhel_detected(self):
        """
        Indicate if the image detected RHEL.

        Returns:
            bool: OR of `rhel_enabled_repos_found`,
                `rhel_product_certs_found`,
                `rhel_release_files_found` and
                `rhel_signed_packages_found` properties.

        """
        return self.rhel_enabled_repos_found or \
            self.rhel_product_certs_found or \
            self.rhel_release_files_found or \
            self.rhel_signed_packages_found

    @property
    def openshift(self):
        """
        Indicate if the image contains OpenShift.

        Returns:
            bool: XOR of `openshift_detected` and `openshift_challenged`
                properties.

        """
        return operator.xor(self.openshift_detected, self.openshift_challenged)

    @property
    def cloud_image_id(self):
        """
        Get the external cloud provider's ID for this image.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        raise NotImplementedError


class Instance(BasePolymorphicModel):
    """Base model for a compute/VM instance in a cloud."""

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )


class InstanceEvent(BasePolymorphicModel):
    """Base model for an event triggered by a Instance."""

    TYPE = model_utils.Choices(
        'power_on',
        'power_off',
        'attribute_change'
    )
    instance = models.ForeignKey(
        Instance,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    machineimage = models.ForeignKey(
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
    )
    event_type = models.CharField(
        max_length=32,
        choices=TYPE,
        null=False,
        blank=False,
    )
    occurred_at = models.DateTimeField(null=False)


class AwsAccount(Account):
    """Amazon Web Services customer account model."""

    aws_account_id = models.CharField(max_length=16, db_index=True)
    account_arn = models.CharField(max_length=256, unique=True)

    @property
    def cloud_account_id(self):
        """Get the AWS Account ID for this account."""
        return self.aws_account_id

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses AWS."""
        return AWS_PROVIDER_STRING

    def delete(self, **kwargs):
        """Delete an AWS Account and disable logging in its AWS cloudtrail."""
        try:
            with transaction.atomic():
                cloudtrial_name = '{0}{1}'.format(
                    settings.CLOUDTRAIL_NAME_PREFIX,
                    self.cloud_account_id
                )
                try:
                    super().delete(**kwargs)
                    session = get_session(str(self.account_arn))
                    cloudtrail_session = session.client('cloudtrail')
                    disable_cloudtrail(cloudtrail_session, cloudtrial_name)

                except ClientError as error:
                    error_code = error.response.get('Error', {}).get('Code')

                    # If cloudtrail does not exist, then delete the account.
                    if error_code == 'TrailNotFoundException':
                        pass

                    # If we're unable to access the account (because user
                    # deleted the role/account). Delete the cloudigrade account
                    # and log an error. This could result in an orphaned
                    # cloudtrail writing to our s3 bucket.
                    elif error_code == 'AccessDenied':
                        log_message = _(
                            'Cloudigrade account {} was deleted, but could '
                            'not access the AWS account to disable its '
                            'cloudtrail {}.'
                        ).format(self.cloud_account_id, cloudtrial_name)
                        logger.warning(log_message)
                        logger.info(error)

                    # If the user role does exist, but we can't stop the
                    # cloudtrail (because of insufficient permission), delete
                    # the cloudigrade account and log an error. This could
                    # result in an orphaned cloudtrail writing to our s3
                    # bucket.
                    elif error_code == 'AccessDeniedException':
                        log_message = _(
                            'Cloudigrade account {} was deleted, but we did '
                            'not have permission to perform cloudtrail:'
                            'StopLogging on cloudtrail {}.'
                        ).format(self.cloud_account_id, cloudtrial_name)
                        logger.warning(log_message)
                        logger.info(error)
                    else:
                        raise
        except ClientError as error:
            log_message = _(
                'Unexpected error occurred. The Cloud Meter account cannot be '
                'deleted. To resolve this issue, contact Cloud Meter support.'
            )
            logger.error(log_message)
            logger.exception(error)
            raise CloudTrailCannotStopLogging(
                detail=log_message
            )


class AwsInstance(Instance):
    """Amazon Web Services EC2 instance model."""

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


class AwsMachineImage(MachineImage):
    """MachineImage model for an AWS EC2 instance."""

    NONE = 'none'
    WINDOWS = 'windows'
    PLATFORM_CHOICES = (
        (NONE, 'None'),
        (WINDOWS, 'Windows'),
    )
    ec2_ami_id = models.CharField(
        max_length=256,
        unique=True,
        db_index=True,
        null=False,
        blank=False
    )
    platform = models.CharField(
        max_length=7,
        choices=PLATFORM_CHOICES,
        default=NONE
    )
    owner_aws_account_id = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        null=False
    )

    @property
    def cloud_image_id(self):
        """Get the AWS EC2 AMI ID."""
        return self.ec2_ami_id


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
        related_name='+'
    )


class AwsInstanceEvent(InstanceEvent):
    """Event model for an event triggered by an AwsInstance."""

    subnet = models.CharField(max_length=256, null=True, blank=True)
    instance_type = models.CharField(max_length=64, null=True, blank=True)


class AwsEC2InstanceDefinitions(models.Model):
    """
    Lookup table for AWS EC2 instance definitions.

    Data should be retrieved from this table using the helper function
    getInstanceDefinition.
    """

    instance_type = models.CharField(
        max_length=256,
        null=False,
        blank=False,
        db_index=True,
        unique=True
    )
    memory = models.FloatField(
        default=0,
    )
    vcpu = models.IntegerField(
        default=0
    )
