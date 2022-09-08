"""Celery tasks related to on-boarding new customer Azure cloud accounts."""
import logging

from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.authentication import get_user_by_account
from api.clouds.azure.models import AzureCloudAccount
from api.clouds.azure.util import (
    create_azure_cloud_account,
    create_initial_azure_instance_events,
    create_new_machine_images,
)
from api.models import User
from util.azure.vm import get_vms_for_subscription
from util.celery import retriable_shared_task
from util.misc import lock_task_for_user_ids

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


@retriable_shared_task(name="api.clouds.azure.tasks.initial_azure_vm_discovery")
def initial_azure_vm_discovery(azure_cloud_account_id):
    """
    Fetch and save instances data found upon enabling an AzureCloudAccount.

    Args:
        azure_cloud_account_id (int): the AzureCloudAccount id
    """
    try:
        azure_cloud_account = AzureCloudAccount.objects.get(pk=azure_cloud_account_id)
    except AzureCloudAccount.DoesNotExist:
        logger.warning(
            _("AzureCloudAccount id %s could not be found for initial vm discovery"),
            azure_cloud_account_id,
        )
        return

    cloud_account = azure_cloud_account.cloud_account.get()
    if not cloud_account.is_enabled:
        logger.warning(
            _("AzureCloudAccount id %s is not enabled; skipping initial vm discovery"),
            azure_cloud_account_id,
        )
        return

    if cloud_account.platform_application_is_paused:
        logger.warning(
            _("AzureCloudAccount id %s is paused; skipping initial vm discovery"),
            azure_cloud_account_id,
        )
        return

    account_subscription_id = azure_cloud_account.subscription_id
    vms_data = get_vms_for_subscription(account_subscription_id)

    try:
        user_id = cloud_account.user.id
    except User.DoesNotExist:
        logger.info(
            _(
                "User for account id %s has already been deleted; "
                "skipping initial vm discovery."
            ),
            azure_cloud_account_id,
        )
        return

    # Lock the task at a user level. A user can only run one task at a time.
    with lock_task_for_user_ids([user_id]):
        AzureCloudAccount.objects.get(pk=azure_cloud_account_id)
        logger.info(
            _(
                "Initiating an Initial VM Discovery for the "
                "Azure cloud account id %(azure_cloud_account_id)s "
                "with the Azure subscription id %(subscription_id)s."
            ),
            {
                "azure_cloud_account_id": azure_cloud_account_id,
                "subscription_id": account_subscription_id,
            },
        )
        new_vm_skus = create_new_machine_images(vms_data)
        logger.info(
            _("New machine image skus created: %(new_vm_skus)s"),
            {"new_vm_skus": new_vm_skus},
        )
        create_initial_azure_instance_events(cloud_account, vms_data)
        return
