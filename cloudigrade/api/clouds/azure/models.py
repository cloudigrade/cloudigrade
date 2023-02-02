"""Cloudigrade API v2 Models for Azure."""
import logging

from azure.core.exceptions import ClientAuthenticationError
from azure.mgmt.managedservices import ManagedServicesClient
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError

from api import AZURE_PROVIDER_STRING
from api.models import CloudAccount
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

        logger.info(_("Finished enabling %(account)s"), {"account": self})
        return True

    def disable(self):
        """
        Disable this AzureCloudAccount.

        This method only handles the Azure-specific piece of disabling a cloud account.
        If you want to completely disable a cloud account, use CloudAccount.disable().
        """
        pass


@receiver(post_delete, sender=AzureCloudAccount)
def delete_lighthouse_registration(*args, **kwargs):
    """Delete the lighthouse registration assignment for the Azure cloud tenant."""
    azure_cloud_account = kwargs["instance"]
    tenant_subscription_id = azure_cloud_account.subscription_id
    logger.info(
        _(
            "Attempting to delete the Azure lighthouse registration"
            " for tenant subscription %s"
        ),
        tenant_subscription_id,
    )

    tenant_scope = f"subscriptions/{tenant_subscription_id}"
    registration_name = None

    try:
        ms_client = ManagedServicesClient(
            credential=azure.get_cloudigrade_credentials()
        )
        ra_list = ms_client.registration_assignments.list(scope=tenant_scope)
        for reg_assignment in ra_list:
            state = reg_assignment.properties.provisioning_state
            id_list = reg_assignment.id.split("/")
            if state == "Succeeded" and "/".join(id_list[1:3]) == tenant_scope:
                if registration_name:
                    logger.warning(
                        _(
                            "Found multiple lighthouse registrations for"
                            " tenant subscription %s, skipping deleting the"
                            " lighthouse registration."
                        ),
                        tenant_subscription_id,
                    )
                    return

                registration_name = reg_assignment.name
                logger.info(
                    _(
                        "Found a lighthouse registration assignment"
                        " for tenant subscription %(subscription)s,"
                        " name %(name)s, id %(assignment_id)s"
                    ),
                    {
                        "subscription": tenant_subscription_id,
                        "name": registration_name,
                        "assignment_id": reg_assignment.id,
                    },
                )
    except ClientAuthenticationError as e:
        logger.warning(
            _(
                "ClientAuthenticationError while trying to find the lighthouse"
                " registration assignment for tenant subscription %s - %s"
            ),
            tenant_subscription_id,
            e,
        )
        return
    except Exception as e:
        logger.error(
            _(
                "Unexpected error while trying to find the lighthouse"
                " registration assignment for tenant subscription %s - %s"
            ),
            tenant_subscription_id,
            e,
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

    logger.info(
        _(
            "Deleting the lighthouse registration assignment"
            " for tenant subscription %s, name %s"
        ),
        tenant_subscription_id,
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
                " the lighthouse registration assignment"
                " for tenant subscription %s, name %s - %s"
            ),
            tenant_subscription_id,
            registration_name,
            e,
        )
        return
