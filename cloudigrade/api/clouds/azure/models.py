"""Cloudigrade API v2 Models for Azure."""
import logging

from azure.core.exceptions import ClientAuthenticationError
from azure.mgmt.managedservices import ManagedServicesClient
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from api import AZURE_PROVIDER_STRING
from api.models import CloudAccount, Instance, InstanceEvent, MachineImage
from util import azure
from util.azure.identity import get_cloudigrade_available_subscriptions
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

        TODO: add logic to verify permissions, and schedule a verification task
        """
        logger.info(_("Enabling %(account)s"), {"account": self})
        if self.subscription_id not in get_cloudigrade_available_subscriptions():
            message = (
                f"Could not enable {repr(self)}; subscription not present in "
                f"list of available subscriptions."
            )
            logger.info(message)
            raise ValidationError({"subscription_id": message})

        from api.clouds.azure import tasks  # Avoid circular import.

        cloud_account = self.cloud_account.get()
        if not cloud_account.platform_application_is_paused:
            # Only do the vm discovery if the application is *not* paused.
            transaction.on_commit(
                lambda: tasks.initial_azure_vm_discovery.delay(self.id)
            )

        logger.info(_("Finished enabling %(account)s"), {"account": self})
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


@receiver(post_delete, sender=AzureCloudAccount)
def delete_lighthouse_registration(*args, **kwargs):
    """Delete the lighthouse registration upon deleting an Azure cloud account."""
    logger.info(
        _(
            "Attempting delete_lighthouse_registration "
            "for args=%(args)s kwargs=%(kwargs)s "
        ),
        {"args": args, "kwargs": kwargs},
    )
    azure_cloud_account = kwargs["instance"]
    azure_subscription_id = azure_cloud_account.subscription_id
    logger.info(
        _("Attempting delete_lighthouse_registration for %(account)s"),
        {"account": azure_cloud_account},
    )
    logger.info(
        _("settings.AZURE_SUBSCRIPTION_ID %(subscription_id)s"),
        {"subscription_id": settings.AZURE_SUBSCRIPTION_ID},
    )
    logger.info(
        _("Azure Cloud Account subscription_id %(subscription_id)s"),
        {"subscription_id": azure_subscription_id},
    )

    _delete_lighthouse_registration_assignment(azure_subscription_id)


def _delete_lighthouse_registration_assignment(tenant_subscription_id):
    """Delete the lighthouse registration assignment for tenant."""
    ms_client = ManagedServicesClient(credential=azure.get_cloudigrade_credentials())
    tenant_scope = f"subscriptions/{tenant_subscription_id}"
    registration_name = None

    try:
        ra_list = ms_client.registration_assignments.list(scope=tenant_scope)
        for reg_assignment in ra_list:
            state = reg_assignment.properties.provisioning_state
            id_list = reg_assignment.id.split("/")
            if (
                state == "Succeeded"
                and id_list[1] == "subscriptions"
                and id_list[2] == tenant_subscription_id
            ):
                registration_name = reg_assignment.name
                logger.info(
                    _(
                        "Found a lighthouse registration assignment name=%(name)s "
                        "for tenant subscripion %(subscription)s, "
                        "id=%(assignment_id)s"
                    ),
                    {
                        "name": registration_name,
                        "subscription": tenant_subscription_id,
                        "assignment_id": reg_assignment.id,
                    },
                )
                break
    except ClientAuthenticationError as e:
        logger.warn(
            _(
                "ClientAuthenticationError while trying to find the lighthouse "
                "registration assignment for tenant subscription %s: %s"
            ),
            {
                tenant_subscription_id,
                e,
            },
        )
        return
    except Exception as e:
        logger.error(
            _(
                "Unexpected error while trying to find the lighthouse "
                "registration assignment for tenant subscription %s: %s"
            ),
            {
                tenant_subscription_id,
                e,
            },
        )
        return

    if not registration_name:
        logger.info(
            _(
                "Could not find a matching lighthouse registration"
                " for tenant subscription %s"
            ),
            tenant_subscription_id,
        )
        return

    _delete_registration_assignment(ms_client, tenant_scope, registration_name)


def _delete_registration_assignment(ms_client, tenant_scope, registration_name):
    """Delete the lighthouse registration assignment."""
    logger.info(
        _(
            "Attempting to delete the lighthouse registration %s",
        ),
        registration_name,
    )

    try:
        ms_client.registration_assignments.begin_delete(
            scope=tenant_scope, registration_assignment_id=registration_name
        ).wait()
    except Exception as e:
        logger.info(
            _(
                "Unexpected error while deleting"
                " the lighthouse registration assignment: %s"
            ),
            e,
        )
        return
