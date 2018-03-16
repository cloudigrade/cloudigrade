"""Cloudigrade Account Models."""
from abc import abstractmethod

import model_utils
from django.db import models

from util.models import BaseModel


class Account(BaseModel):
    """Base customer account model."""


class Instance(BaseModel):
    """Base model for a compute/VM instance in a cloud."""

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )


class InstanceEvent(BaseModel):
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

    aws_account_id = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        db_index=True,
    )
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


class AwsInstanceEvent(InstanceEvent):
    """Event model for an event triggered by an AwsInstance."""

    subnet = models.CharField(max_length=256, null=False, blank=False)
    ec2_ami_id = models.CharField(max_length=256, null=False, blank=False)
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
        return f'aws-{self.ec2_ami_id}-{self.instance_type}'
