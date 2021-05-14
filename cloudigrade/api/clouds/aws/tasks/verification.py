"""Celery tasks related to verifying data and customer accounts for AWS."""
import logging

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils.translation import gettext as _
from django_celery_beat.models import PeriodicTask

from api.clouds.aws.models import AwsCloudAccount
from api.clouds.aws.util import verify_permissions
from api.models import CloudAccount
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@shared_task(name="api.clouds.aws.tasks.verify_account_permissions")
def verify_account_permissions(account_arn):
    """
    Periodic task that verifies the account arn is still valid.

    Args:
        account_arn: The ARN for the account to check

    Returns:
        bool: True if the ARN is still valid.

    """
    valid = verify_permissions(account_arn)
    logger.debug(
        _("%(account_arn)s verified permissions? %(valid)s"),
        {"account_arn": account_arn, "valid": valid},
    )

    if not valid:
        # Disable the cloud account.
        logger.info(
            _("ARN %s failed validation. Disabling the cloud account."), account_arn
        )
        with transaction.atomic():
            try:
                aws_cloud_account = AwsCloudAccount.objects.get(account_arn=account_arn)
                cloud_account = aws_cloud_account.cloud_account.get()
                if cloud_account:
                    # We do *not* need to notify sources here because verify_permissions
                    # should have just done that with a more specific error message.
                    cloud_account.disable(notify_sources=False)
                else:
                    raise CloudAccount.DoesNotExist

            except (
                AwsCloudAccount.DoesNotExist,
                CloudAccount.DoesNotExist,
                ObjectDoesNotExist,
            ) as exception:
                # If the account was deleted before or during our check, log and return.
                logger.info(
                    "Cannot disable: cloud account object does not exist for "
                    "ARN %(arn)s (%(exception)s)",
                    {"arn": account_arn, "exception": exception},
                )

    return valid


@retriable_shared_task(name="api.clouds.aws.tasks.verify_verify_tasks")
def verify_verify_tasks():
    """
    Periodic task that maintains periodic verify permissions tasks.

    It checks for Cloud Accounts that are enabled, but have
    no verify task, and adds one. It also checks for any orphaned
    verify tasks, and cleans those up to.

    Returns:
        None: runs as an async task.

    """
    # Check for enabled accounts without a verify task.
    cloud_accounts = CloudAccount.objects.filter(
        is_enabled=True, aws_cloud_account__verify_task=None
    )
    for cloud_account in cloud_accounts:
        logger.error(
            _(
                "Cloud Account ID %(cloud_account_id)s is enabled, "
                "but missing verification task. Creating."
            ),
            {
                "cloud_account_id": cloud_account.id,
            },
        )
        aws_cloud_account = cloud_account.content_object
        aws_cloud_account._enable_verify_task()

    # Check for orphaned verify tasks
    linked_task_ids = AwsCloudAccount.objects.exclude(
        verify_task_id__isnull=True
    ).values_list("verify_task_id", flat=True)
    verify_tasks = PeriodicTask.objects.filter(
        task="api.clouds.aws.tasks.verify_account_permissions",
    ).exclude(pk__in=linked_task_ids)
    for verify_task in verify_tasks:
        logger.error(
            _("Found orphaned verify task '%(verify_task)s', deleting."),
            {
                "verify_task": verify_task,
            },
        )
        verify_task.delete()
