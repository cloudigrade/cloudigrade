"""Utility functions for AWS models and use cases."""
import logging

from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api.clouds.azure.models import AzureCloudAccount
from api.models import CloudAccount


logger = logging.getLogger(__name__)


def create_azure_cloud_account(
    user,
    cloud_account_name,
    subscription_id,
    tenant_id,
    platform_authentication_id,
    platform_application_id,
    platform_endpoint_id,
    platform_source_id,
):
    """
    Create AzureCloudAccount for the customer user.

    This function may raise ValidationError if certain verification steps fail.

    We call CloudAccount.enable after creating it, and that effectively verifies Azure
    permission. If that fails, we must abort this creation.
    That is why we put almost everything here in a transaction.atomic() context.

    Args:
        user (django.contrib.auth.models.User): user to own the CloudAccount
        subscription_id (str): UUID of the customer subscription
        tenant_id (str): UUID of the customer tenant
        platform_authentication_id (str): Platform Sources' Authentication object id
        platform_application_id (str): Platform Sources' Application object id
        platform_endpoint_id (str): Platform Sources' Endpoint object id
        platform_source_id (str): Platform Sources' Source object id

    Returns:
        CloudAccount the created cloud account.

    """
    logger.info(
        _(
            "Creating an AzureCloudAccount. "
            "user=%(user)s, "
            "subscription_id=%(subscription_id)s, "
            "tenant_id=%(tenant_id)s, "
            "platform_authentication_id=%(platform_authentication_id)s, "
            "platform_application_id=%(platform_application_id)s, "
            "platform_endpoint_id=%(platform_endpoint_id)s, "
            "platform_source_id=%(platform_source_id)s"
        ),
        {
            "user": user.username,
            "subscription_id": subscription_id,
            "tenant_id": tenant_id,
            "platform_authentication_id": platform_authentication_id,
            "platform_application_id": platform_application_id,
            "platform_endpoint_id": platform_endpoint_id,
            "platform_source_id": platform_source_id,
        },
    )

    with transaction.atomic():
        azure_cloud_account = AzureCloudAccount.objects.create(
            subscription_id=subscription_id, tenant_id=tenant_id
        )
        cloud_account = CloudAccount.objects.create(
            user=user,
            name=cloud_account_name,
            content_object=azure_cloud_account,
            platform_application_id=platform_application_id,
            platform_authentication_id=platform_authentication_id,
            platform_endpoint_id=platform_endpoint_id,
            platform_source_id=platform_source_id,
        )

        # This enable call *must* be inside the transaction because we need to
        # know to rollback the transaction if anything related to enabling fails.
        if cloud_account.enable() is False:
            # Enabling of cloud account failed, rolling back.
            transaction.set_rollback(True)
            raise ValidationError(
                {
                    "is_enabled": "Could not enable cloud account. "
                    "Please check your credentials."
                }
            )

    return cloud_account
