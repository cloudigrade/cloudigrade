"""Cloudigrade API v2 Models."""
import json
import logging
import operator

import model_utils
from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from api import AWS_PROVIDER_STRING
from util.aws import disable_cloudtrail, get_session
from util.exceptions import CloudTrailCannotStopLogging
from util.models import BaseGenericModel, BaseModel

logger = logging.getLogger(__name__)


CLOUD_ACCESS_NAME_TOKEN = '-Access2'
MARKETPLACE_NAME_TOKEN = '-hourly2'


class CloudAccount(BaseGenericModel):
    """Base Customer Cloud Account Model."""

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
        return self.content_object.cloud_account_id

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_type

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f"name='{self.name}', "
            f'user_id={self.user_id}, '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )

    @transaction.atomic
    def delete(self, **kwargs):
        """
        Delete the generic clount, and the platform specific clount.

        Delete all instances belonging to the account.
        """
        # Note that we cannot use a bulk delete here since bulk delete
        # does not trigger the delete() method on individual instances.
        for instance in self.instance_set.all():
            instance.delete()
        super().delete(**kwargs)


class AwsCloudAccount(BaseModel):
    """AWS Customer Cloud Account Model."""

    cloud_account = GenericRelation(CloudAccount)
    aws_account_id = models.DecimalField(
        max_digits=12, decimal_places=0, db_index=True
    )
    aws_access_key_id = models.CharField(max_length=128, null=True, blank=True)
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
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'aws_account_id={self.aws_account_id}, '
            f"account_arn='{self.account_arn}', "
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )

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
                    logger.info(
                        'attempting to disable cloudtrail "%(name)s" via ARN '
                        '"%(arn)s"',
                        {'name': cloudtrial_name, 'arn': self.account_arn},
                    )
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


class MachineImage(BaseGenericModel):
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
    def rhel_version(self):
        """
        Get the detected version of RHEL.

        Returns:
            str of the detected version or None if not set.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get('rhel_version', None)
        return None

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
        Indicate if the image contains Red Hat product certs.

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
        return self.content_object.is_cloud_access or \
            self.rhel_enabled_repos_found or \
            self.rhel_product_certs_found or \
            self.rhel_release_files_found or \
            self.rhel_signed_packages_found

    @property
    def syspurpose(self):
        """
        Get the detected system purpose (syspurpose).

        Returns:
            str of the detected system purpose or None if not set.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get('syspurpose', None)
        return None

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
        """Get the external cloud provider's ID for this image."""
        return self.content_object.is_cloud_access

    @property
    def is_cloud_access(self):
        """Indicate if the image is from Cloud Access."""
        return self.content_object.is_cloud_access

    @property
    def is_marketplace(self):
        """Indicate if the image is from AWS Marketplace."""
        return self.content_object.is_marketplace

    @property
    def cloud_type(self):
        """Get the external cloud provider type."""
        return self.content_object.cloud_type

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        name = (
            str(repr(self.name))
            if self.name is not None
            else None
        )
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'name={name}, '
            f"status='{self.status}', "
            f'is_encrypted={self.is_encrypted}, '
            f'rhel_challenged={self.rhel_challenged}, '
            f'openshift_detected={self.openshift_detected}, '
            f'openshift_challenged={self.openshift_challenged}, '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )


class AwsMachineImage(BaseModel):
    """MachineImage model for an AWS EC2 instance."""

    NONE = 'none'
    WINDOWS = 'windows'
    PLATFORM_CHOICES = (
        (NONE, 'None'),
        (WINDOWS, 'Windows'),
    )
    machine_image = GenericRelation(MachineImage,
                                    related_query_name='aws_machine_image')
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
            self.machine_image.get().name is not None and
            CLOUD_ACCESS_NAME_TOKEN.lower() in
            self.machine_image.get().name.lower() and
            self.owner_aws_account_id in settings.RHEL_IMAGES_AWS_ACCOUNTS
        )

    @property
    def is_marketplace(self):
        """Indicate if the image is from AWS Marketplace."""
        return (
            self.machine_image.get().name is not None and
            MARKETPLACE_NAME_TOKEN.lower() in
            self.machine_image.get().name.lower() and
            self.owner_aws_account_id in settings.RHEL_IMAGES_AWS_ACCOUNTS
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
        platform = (
            str(repr(self.platform))
            if self.platform is not None
            else None
        )
        region = (
            str(repr(self.region))
            if self.region is not None
            else None
        )
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f"ec2_ami_id='{self.ec2_ami_id}', "
            f'platform={platform}, '
            f'owner_aws_account_id={self.owner_aws_account_id}, '
            f'region={region}, '
            f'aws_marketplace_image={self.aws_marketplace_image}, '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
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
        related_name='+'
    )

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        reference_awsmachineimage_id = self.reference_awsmachineimage_id
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'reference_awsmachineimage_id={reference_awsmachineimage_id}, '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )


class Instance(BaseGenericModel):
    """Base model for a compute/VM instance in a cloud."""

    cloud_account = models.ForeignKey(
        CloudAccount,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    machine_image = models.ForeignKey(
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
    )

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        machine_image_id = (
            str(repr(self.machine_image_id))
            if self.machine_image_id is not None
            else None
        )
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'cloud_account_id={self.cloud_account_id}, '
            f'machine_image_id={machine_image_id}, '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )

    @transaction.atomic
    def delete(self, **kwargs):
        """
        Delete the instance.

        Delete the instance's machine image if no other instances use it.
        Delete all instanceevents that reference this instance.
        """
        for event in self.instanceevent_set.all():
            event.delete()

        # Gotta delete the instance first, otherwise machine image deletion
        # will cascade delete the instance. and not trigger the awsinstance
        # clean up.
        super().delete(**kwargs)

        if (
            self.machine_image is not None and
            not Instance.objects.filter(machine_image=self.machine_image)
            .exclude(id=self.id)
            .exists()
        ):
            logger.info(
                _(
                    '%s is no longer used by any instances and will be deleted'
                ),
                self.machine_image,
            )
            self.machine_image.delete()

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_type

    @property
    def cloud_instance_id(self):
        """
        Get the external cloud instance id.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_instance_id


class AwsInstance(BaseModel):
    """Amazon Web Services EC2 instance model."""

    instance = GenericRelation(Instance, related_query_name='aws_instance')
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
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f"ec2_instance_id='{self.ec2_instance_id}', "
            f"region='{self.region}', "
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses AWS."""
        return AWS_PROVIDER_STRING

    @property
    def cloud_instance_id(self):
        """Get the cloud instance id."""
        return self.ec2_instance_id


class InstanceEvent(BaseGenericModel):
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
    event_type = models.CharField(
        max_length=32,
        choices=TYPE,
        null=False,
        blank=False,
    )
    occurred_at = models.DateTimeField(null=False)

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_type

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        occurred_at = (
            repr(self.occurred_at.isoformat())
            if self.occurred_at is not None
            else None
        )
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'instance_id={self.instance_id}, '
            f'event_type={self.event_type}, '
            f'occurred_at=parse({occurred_at}), '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )


class AwsInstanceEvent(BaseModel):
    """Event model for an event triggered by an AwsInstance."""

    instance_event = GenericRelation(InstanceEvent,
                                     related_query_name='aws_instance_event')
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
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'subnet={subnet}, '
            f'instance_type={instance_type}, '
            f'created_at=parse({created_at}), '
            f'updated_at=parse({updated_at})'
            f')'
        )


class AwsEC2InstanceDefinition(BaseModel):
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
    memory = models.DecimalField(
        default=0,
        decimal_places=2,
        max_digits=16,
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

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Save this run and delete any related ConcurrentUsage objects."""
        date_filter = Q(date__gte=self.start_time.date())
        if self.end_time:
            date_filter &= Q(date__lte=self.end_time.date())
        concurrent_usages = ConcurrentUsage.objects.filter(
            date_filter,
            user_id=self.instance.cloud_account.user_id,
        )
        concurrent_usages.delete()
        return super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        """Delete this run and any related ConcurrentUsage objects."""
        date_filter = Q(date__gte=self.start_time.date())
        if self.end_time:
            date_filter &= Q(date__lte=self.end_time.date())
        concurrent_usages = ConcurrentUsage.objects.filter(
            date_filter,
            user_id=self.instance.cloud_account.user_id,
        )
        concurrent_usages.delete()
        return super().delete(*args, **kwargs)


class MachineImageInspectionStart(BaseModel):
    """Model to track any time an image starts inspection."""

    machineimage = models.ForeignKey(
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )


class ConcurrentUsage(BaseModel):
    """Saved calculation of max concurrent usage for a date+user+account."""

    date = models.DateField()
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    cloud_account = models.ForeignKey(
        CloudAccount,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
    )
    instances = models.IntegerField()
    _instances_list = models.TextField(db_column='instances_list',
                                       null=True,
                                       blank=True)
    memory = models.FloatField()
    vcpu = models.IntegerField()

    @property
    def instances_list(self):
        """Get instance list."""
        return json.loads(self._instances_list)

    @instances_list.setter
    def instances_list(self, value):
        """Set instance list."""
        self._instances_list = json.dumps(value)

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        date = (
            repr(self.date.isoformat())
            if self.date is not None
            else None
        )
        created_at = (
            repr(self.created_at.isoformat())
            if self.created_at is not None
            else None
        )
        updated_at = (
            repr(self.updated_at.isoformat())
            if self.updated_at is not None
            else None
        )

        return (
            f'{self.__class__.__name__}('
            f'id={self.id}, '
            f'date={date}, '
            f'user_id={self.user_id}, '
            f'cloud_account_id={self.cloud_account_id}, '
            f'memory={self.memory}, '
            f'vcpu={self.vcpu}, '
            f'created_at={created_at}, '
            f'updated_at={updated_at}'
            f')'
        )
