"""Celery tasks related to on-boarding new customer Azure cloud accounts."""
import logging

from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.clouds.azure.util import create_azure_cloud_account
from util.celery import retriable_shared_task

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
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
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
