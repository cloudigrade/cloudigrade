"""Cloudigrade Account Models."""
import model_utils
from django.db import models

from util.models import BaseModel


class Account(BaseModel):
    """Account model."""

    account_id = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        db_index=True
    )  # AWS Account ID
    account_arn = models.CharField(max_length=256, unique=True)  # AWS ARN


class Instance(BaseModel):
    """AWS EC2 Instance model."""

    account = models.ForeignKey(
        'Account',
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
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
        """Get repr of this Instance."""
        return f'<Instance {self.ec2_instance_id}>'


class InstanceEvent(BaseModel):
    """AWS EC2 Instance Event model."""

    TYPE = model_utils.Choices(
        'power_on',
        'power_off',
    )
    instance = models.ForeignKey(
        'Instance',
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
    subnet = models.CharField(max_length=16, null=False, blank=False)
    ec2_ami_id = models.CharField(max_length=256, null=False, blank=False)
