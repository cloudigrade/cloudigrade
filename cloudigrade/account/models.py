"""Cloudigrade Account Models."""
from abc import abstractmethod

import model_utils
from django.contrib.auth.models import User
from django.db import models

from util.models import (BaseModel,
                         BasePolymorphicModel)


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


class ImageTag(BaseModel):
    """Tag types for images."""

    description = models.CharField(
        max_length=32,
        null=False,
        blank=False
    )


class MachineImage(BasePolymorphicModel):
    """Base model for a cloud VM image."""

    PENDING = 'pending'
    PREPARING = 'preparing'
    INSPECTING = 'inspecting'
    INSPECTED = 'inspected'
    STATUS_CHOICES = (
        (PENDING, 'Pending Inspection'),
        (PREPARING, 'Preparing for Inspection'),
        (INSPECTING, 'Being Inspected'),
        (INSPECTED, 'Inspected'),
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    tags = models.ManyToManyField(ImageTag, blank=True)
    inspection_json = models.TextField(null=True,
                                       blank=True)
    is_encrypted = models.NullBooleanField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=PENDING)

    @property
    def rhel(self):
        """
        Indicate if the image is tagged for RHEL.

        Returns:
            bool: True if a 'rhel' tag exists for this image, else False.

        """
        return self.tags.filter(description='rhel').exists()

    @property
    def openshift(self):
        """
        Indicate if the image is tagged for OpenShift.

        Returns:
            bool: True if an 'openshift' tag exists for this image, else False.

        """
        return self.tags.filter(description='openshift').exists()


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
    @abstractmethod
    def product_identifier(self):
        """
        Get a relatively unique product identifier.

        This may be implementation-specific to particular cloud providers.
        """


class AwsAccount(Account):
    """Amazon Web Services customer account model."""

    aws_account_id = models.CharField(max_length=16, db_index=True)
    account_arn = models.CharField(max_length=256, unique=True)


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

    def __repr__(self):
        """Get repr of this AwsInstance."""
        return f'<AwsInstance {self.ec2_instance_id}>'


class AwsMachineImage(MachineImage):
    """MachineImage model for an AWS EC2 instance."""

    ec2_ami_id = models.CharField(
        max_length=256,
        unique=True,
        db_index=True,
        null=False,
        blank=False
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


class AwsInstanceEvent(InstanceEvent):
    """Event model for an event triggered by an AwsInstance."""

    subnet = models.CharField(max_length=256, null=False, blank=False)
    instance_type = models.CharField(max_length=64, null=False, blank=False)

    @property
    def product_identifier(self):
        """Get a relatively unique product identifier.

        This should be unique enough for product usage reporting purposes. For
        now, this means it's a combination of:

            - AMI ID (until we know what RHEL version it has)
            - EC2 instance type

        Todo:
            - use an actual RHEL version

        Returns:
            str: the computed product identifier

        """
        return f'aws-{self.machineimage.id}-{self.instance_type}'
