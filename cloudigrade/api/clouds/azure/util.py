"""Utility functions for Azure models and use cases."""

import logging
import uuid

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.clouds.azure.models import AzureCloudAccount
from api.models import CloudAccount

logger = logging.getLogger(__name__)


def create_azure_cloud_account(
    user,
    subscription_id,
    platform_authentication_id,
    platform_application_id,
    platform_source_id,
):
    """
    Create AzureCloudAccount for the customer user.

    This function may raise ValidationError if certain verification steps fail.

    We call CloudAccount.enable after creating it, and that effectively verifies Azure
    permission. If that fails, we must abort this creation.
    That is why we put almost everything here in a transaction.atomic() context.

    Args:
        user (api.User): user to own the CloudAccount
        subscription_id (str): UUID of the customer subscription
        platform_authentication_id (str): Platform Sources' Authentication object id
        platform_application_id (str): Platform Sources' Application object id
        platform_source_id (str): Platform Sources' Source object id

    Returns:
        CloudAccount the created cloud account.

    """
    logger.info(
        _(
            "Creating an AzureCloudAccount. "
            "account_number=%(account_number)s, "
            "org_id=%(org_id)s, "
            "subscription_id=%(subscription_id)s, "
            "platform_authentication_id=%(platform_authentication_id)s, "
            "platform_application_id=%(platform_application_id)s, "
            "platform_source_id=%(platform_source_id)s"
        ),
        {
            "account_number": user.account_number,
            "org_id": user.org_id,
            "subscription_id": subscription_id,
            "platform_authentication_id": platform_authentication_id,
            "platform_application_id": platform_application_id,
            "platform_source_id": platform_source_id,
        },
    )

    with transaction.atomic():
        try:
            subscription_id_as_uuid = uuid.UUID(subscription_id)
        except ValueError:
            error_code = error_codes.CG1006
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"subscription_id": error_code.get_message()})
        try:
            azure_cloud_account = AzureCloudAccount.objects.create(
                subscription_id=subscription_id_as_uuid
            )
        except IntegrityError:
            # create can raise IntegrityError if the given
            # subscription_id already exists in an account
            error_code = error_codes.CG1005
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"subscription_id": error_code.get_message()})

        cloud_account = CloudAccount.objects.create(
            user=user,
            content_object=azure_cloud_account,
            platform_application_id=platform_application_id,
            platform_authentication_id=platform_authentication_id,
            platform_source_id=platform_source_id,
        )

        # This enable call *must* be inside the transaction because we need to
        # know to rollback the transaction if anything related to enabling fails.
        if not cloud_account.enable(disable_upon_failure=False):
            # Enabling of cloud account failed, rolling back.
            transaction.set_rollback(True)
            raise ValidationError(
                {
                    "is_enabled": "Could not enable cloud account. "
                    "Please check your credentials."
                }
            )

    return cloud_account
