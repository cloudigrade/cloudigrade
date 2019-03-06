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
from util.models import BaseModel, BasePolymorphicModel

logger = logging.getLogger(__name__)


CLOUD_ACCESS_NAME_TOKEN = '-Access2'
MARKETPLACE_NAME_TOKEN = '-hourly2'


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
        null=False,
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
    UNAVAILABLE = 'unavailable'  # images we can't access but know must exist
    STATUS_CHOICES = (
        (PENDING, 'Pending Inspection'),
        (PREPARING, 'Preparing for Inspection'),
        (INSPECTING, 'Being Inspected'),
        (INSPECTED, 'Inspected'),
        (ERROR, 'Error'),
        (UNAVAILABLE, 'Unavailable for Inspection'),
    )
    inspection_json = models.TextField(null=True,
                                       blank=True)
    is_encrypted = models.BooleanField(default=False)
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default=PENDING
    )
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
            bool: combination of various image properties that results in our
                canonical definition of whether the image is marked for RHEL.

        """
        return self.is_cloud_access or \
            self.rhel_enabled_repos_found or \
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

    @property
    def is_cloud_access(self):
        """
        Indicate if the image is from Cloud Access.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        raise NotImplementedError

    @property
    def is_marketplace(self):
        """
        Indicate if the image is from AWS Marketplace.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        raise NotImplementedError


class MachineImageInspectionStart(BaseModel):
    """Model to track any time an image starts inspection."""

    machineimage = models.ForeignKey(
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    occurred_at = models.DateTimeField(auto_now_add=True, null=False)


class Instance(BasePolymorphicModel):
    """Base model for a compute/VM instance in a cloud."""

    account = models.ForeignKey(
        Account,
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

    aws_account_id = models.DecimalField(
        max_digits=12, decimal_places=0, db_index=True
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
                        logger.warning(
                            _('Cloudigrade account %(account_id)s was deleted,'
                              ' but could not access the AWS account to '
                              'disable its cloudtrail %(cloudtrail_name)s.'),
                            {'account_id': self.cloud_account_id,
                             'cloudtrail_name': cloudtrial_name}
                        )
                        logger.info(error)

                    # If the user role does exist, but we can't stop the
                    # cloudtrail (because of insufficient permission), delete
                    # the cloudigrade account and log an error. This could
                    # result in an orphaned cloudtrail writing to our s3
                    # bucket.
                    elif error_code == 'AccessDeniedException':
                        logger.warning(
                            _('Cloudigrade account %(account_id)s was deleted,'
                              ' but we did not have permission to perform '
                              'cloudtrail: StopLogging on cloudtrail '
                              '%(cloudtrail_name)s.'),
                            {'account_id': self.cloud_account_id,
                             'cloudtrail_name': cloudtrial_name}
                        )
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
    aws_marketplace_image = models.BooleanField(
        default=False
    )

    @property
    def is_cloud_access(self):
        """Indicate if the image is from Cloud Access."""
        return (
            self.name is not None and
            CLOUD_ACCESS_NAME_TOKEN.lower() in self.name.lower() and
            self.owner_aws_account_id in settings.RHEL_IMAGES_AWS_ACCOUNTS
        )

    @property
    def is_marketplace(self):
        """Indicate if the image is from AWS Marketplace."""
        return (
            self.name is not None and
            MARKETPLACE_NAME_TOKEN.lower() in self.name.lower() and
            self.owner_aws_account_id in settings.RHEL_IMAGES_AWS_ACCOUNTS
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

    def __repr__(self):
        """
        Get an unambiguous string representation of this event.

        Returned string should be clean enough to pass into eval to instantiate
        a proper model object that could be saved if desired. For example:

            from account.models import AwsInstanceEvent
            from account.tests import helper
            a = helper.generate_aws_account()
            i = helper.generate_aws_instance(a)
            e = helper.generate_single_aws_instance_event(i, datetime.now())

            from dateutil.parser import parse
            e2 = eval(repr(e))

            e.delete()
            e2.save()

        The pk/id will not actually be preserved if saved after deleting the
        original instance, but that's okay because nothing should reference it.
        The updated_date will always be overridden as "now" when saving.
        """
        subnet = (
            str(repr(self.subnet))
            if self.subnet is not None
            else None
        )
        instance_type = (
            str(repr(self.instance_type))
            if self.instance_type is not None
            else None
        )
        machineimage_id = (
            self.machineimage_id
            if self.machineimage_id is not None
            else None
        )
        occurred_at = repr(self.occurred_at.isoformat())
        created_at = repr(self.created_at.isoformat())
        updated_at = repr(self.updated_at.isoformat())

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'subnet={subnet}, '
            f'instance_type={instance_type}, '
            f'instance_id={self.instance_id}, '
            f'machineimage_id={machineimage_id}, '
            f'event_type={repr(self.event_type)}, '
            f'occurred_at=parse({occurred_at}), '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )


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


class Run(BaseModel):
    """Base model for a Run object."""

    start_time = models.DateTimeField(
        null=False
    )
    end_time = models.DateTimeField(
        blank=True,
        null=True
    )
    machineimage = models.ForeignKey(
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
    )
    instance = models.ForeignKey(
        Instance,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    instance_type = models.CharField(
        max_length=64,
        null=True,
        blank=True
    )
    memory = models.FloatField(
        default=0,
        blank=True,
        null=True
    )
    vcpu = models.IntegerField(
        default=0,
        blank=True,
        null=True
    )
