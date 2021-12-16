"""Cloudigrade API v2 Models for Azure."""
import logging

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from api import AZURE_PROVIDER_STRING
from api.models import CloudAccount, Instance, InstanceEvent, MachineImage
from util.models import BaseModel

logger = logging.getLogger(__name__)


class AzureCloudAccount(BaseModel):
    """Azure Customer Cloud Account Model."""

    cloud_account = GenericRelation(
        CloudAccount, related_query_name="azure_cloud_account"
    )
    subscription_id = models.UUIDField(unique=True)

    @property
    def cloud_account_id(self):
        """Get the Azure Subscription ID for this account."""
        return str(self.subscription_id)

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses Azure."""
        return AZURE_PROVIDER_STRING

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
            f"subscription_id={self.subscription_id}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    def enable(self):
        """
        Enable this AzureCloudAccount.

        This method only handles the Azure-specific piece of enabling a cloud account.
        If you want to completely enable a cloud account, use CloudAccount.enable().

        TODO: add logic to verify permissions, do an initial describe instances,
              and schedule a verification task
        """
        return True

    def disable(self):
        """
        Disable this AzureCloudAccount.

        This method only handles the Azure-specific piece of disabling a cloud account.
        If you want to completely disable a cloud account, use CloudAccount.disable().
        """
        pass


class AzureMachineImage(BaseModel):
    """MachineImage model for an Azure Image."""

    machine_image = GenericRelation(
        MachineImage, related_query_name="azure_machine_image"
    )
    region = models.CharField(
        max_length=256,
        null=True,
        blank=True,
    )
    resource_id = models.CharField(
        max_length=256,
        unique=True,
        null=True,
        blank=True,
    )
    azure_marketplace_image = models.BooleanField(default=False)

    @property
    def is_marketplace(self):
        """Indicate if the image is from Azure Marketplace."""
        return self.azure_marketplace_image

    @property
    def is_cloud_access(self):
        """
        Indicate if the image is from Cloud Access.

        TODO: determine if Azure has a concept of cloud access.
        """
        return False

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses Azure."""
        return AZURE_PROVIDER_STRING

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
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
            f"resource_id={self.resource_id},"
            f"region={region}, "
            f"azure_marketplace_image={self.azure_marketplace_image}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )


class AzureInstance(BaseModel):
    """Azure instance model."""

    instance = GenericRelation(Instance, related_query_name="azure_instance")
    resource_id = models.CharField(
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
            f"resource_id='{self.resource_id}', "
            f"region='{self.region}', "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses Azure."""
        return AZURE_PROVIDER_STRING

    @property
    def cloud_instance_id(self):
        """Get the cloud instance id."""
        return self.resource_id


class AzureInstanceEvent(BaseModel):
    """Event model for an event triggered by an AzureInstance."""

    instance_event = GenericRelation(
        InstanceEvent, related_query_name="azure_instance_event"
    )
    instance_type = models.CharField(max_length=256, null=True, blank=True)

    @property
    def cloud_type(self):
        """Get the cloud type to indicate this account uses Azure."""
        return AZURE_PROVIDER_STRING

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
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
            f"instance_type={instance_type}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )
