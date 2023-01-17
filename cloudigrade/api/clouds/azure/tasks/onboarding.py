"""Celery tasks related to on-boarding new customer Azure cloud accounts."""
import logging

from azure.core.exceptions import ClientAuthenticationError
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.authentication import get_user_by_account
from api.clouds.azure.util import create_azure_cloud_account
from api.models import User
from util.celery import retriable_shared_task, shared_task

logger = logging.getLogger(__name__)


@retriable_shared_task(
    name="api.clouds.azure.tasks.check_azure_subscription_and_create_cloud_account",
)
def check_azure_subscription_and_create_cloud_account(
    username, org_id, subscription_id, authentication_id, application_id, source_id
):
    """
    Configure the customer's Azure account and create our CloudAccount.

    Args:
        username (string): Username of the user that will own the new cloud account
        subscription_id (str): customer's subscription id
        authentication_id (str): Platform Sources' Authentication object id
        application_id (str): Platform Sources' Application object id
        source_id (str): Platform Sources' Source object id
    """
    logger.info(
        _(
            "Starting check_azure_subscription_and_create_cloud_account for "
            "username='%(username)s' "
            "org_id='%(org_id)s' "
            "subscription_id='%(subscription_id)s' "
            "authentication_id='%(authentication_id)s' "
            "application_id='%(application_id)s' "
            "source_id='%(source_id)s'"
        ),
        {
            "username": username,
            "org_id": org_id,
            "subscription_id": subscription_id,
            "authentication_id": authentication_id,
            "application_id": application_id,
            "source_id": source_id,
        },
    )
    try:
        user = get_user_by_account(account_number=username, org_id=org_id)
    except User.DoesNotExist:
        logger.exception(
            _(
                "Missing user (account_number='%(username)s', org_id='%(org_id)s') "
                "for check_azure_subscription_and_create_cloud_account. "
                "This should never happen and may indicate a database failure!"
            ),
            {"username": username, "org_id": org_id},
        )
        error = error_codes.CG1000
        error.log_internal_message(
            logger, {"application_id": application_id, "username": username}
        )
        error.notify(username, org_id, application_id)
        return

    try:
        create_azure_cloud_account(
            user,
            subscription_id,
            authentication_id,
            application_id,
            source_id,
        )
    except ValidationError as e:
        logger.info(_("Unable to create cloud account: error %s"), e.detail)

    logger.info(
        _(
            "Finished check_azure_subscription_and_create_cloud_account for "
            "username='%(username)s' "
            "org_id='%(org_id)s' "
            "subscription_id='%(subscription_id)s' "
            "authentication_id='%(authentication_id)s' "
            "application_id='%(application_id)s' "
            "source_id='%(source_id)s'"
        ),
        {
            "username": username,
            "org_id": org_id,
            "subscription_id": subscription_id,
            "authentication_id": authentication_id,
            "application_id": application_id,
            "source_id": source_id,
        },
    )


@retriable_shared_task(
    name="api.clouds.azure.tasks.initial_azure_vm_discovery",
    autoretry_for=(ClientAuthenticationError,),
)
def initial_azure_vm_discovery(azure_cloud_account_id):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.clouds.azure.tasks.update_azure_instance_events")
def update_azure_instance_events():
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.clouds.azure.tasks.update_azure_instance_events_for_account")
def update_azure_instance_events_for_account(cloud_account_id):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
