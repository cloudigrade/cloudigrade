"""Tasks for various data maintenance, activation, and upkeep operations."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.translation import gettext as _

from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.models import (
    CloudAccount,
    ConcurrentUsage,
    Instance,
    InstanceEvent,
    MachineImage,
    Run,
)
from util import aws
from util.celery import retriable_shared_task
from util.exceptions import AwsThrottlingException
from util.misc import get_now, lock_task_for_user_ids

logger = logging.getLogger(__name__)


@transaction.atomic()
def _delete_user(user):
    """Delete given User if it has no related CloudAccount objects."""
    if CloudAccount.objects.filter(user_id=user.id).exists():
        return False

    count, __ = user.delete()
    return count > 0


@shared_task(name="api.tasks.delete_inactive_users")
def delete_inactive_users():
    """
    Delete all inactive User objects.

    A User is considered to be inactive if all of the following are true:
    - the User has no related CloudAccount objects
    - the User is not a superuser
    - the User's date joined is more than MINIMUM_USER_AGE_SECONDS old
    """
    oldest_allowed_date_joined = get_now() - timedelta(
        seconds=settings.DELETE_INACTIVE_USERS_MIN_AGE
    )
    users = User.objects.filter(
        is_superuser=False, date_joined__lt=oldest_allowed_date_joined
    )
    total_user_count = users.count()
    deleted_user_count = 0
    logger.info(
        _(
            "Found %(total_user_count)s not-superuser Users joined before "
            "%(date_joined)s."
        ),
        {
            "total_user_count": total_user_count,
            "date_joined": oldest_allowed_date_joined,
        },
    )
    for user in users:
        if _delete_user(user):
            deleted_user_count += 1
    logger.info(
        _(
            "Successfully deleted %(deleted_user_count)s of %(total_user_count)s "
            "users."
        ),
        {
            "deleted_user_count": deleted_user_count,
            "total_user_count": total_user_count,
        },
    )


@shared_task(name="api.tasks.enable_account")
def enable_account(cloud_account_id):
    """
    Task to enable a cloud account.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    try:
        cloud_account = CloudAccount.objects.get(id=cloud_account_id)
    except CloudAccount.DoesNotExist:
        logger.warning(
            "Cloud Account with ID %(cloud_account_id)s does not exist. "
            "No cloud account to enable, exiting.",
            {"cloud_account_id": cloud_account_id},
        )
        return

    cloud_account.enable()


@retriable_shared_task(
    autoretry_for=(RuntimeError, AwsThrottlingException),
    name="api.tasks.delete_cloud_account",
)
@aws.rewrap_aws_errors
def delete_cloud_account(cloud_account_id):
    """
    Delete the CloudAccount with the given ID.

    This task function exists to support an internal API for deleting a CloudAccount.
    Unfortunately, deletion may be a time-consuming operation and needs to be done
    asynchronously to avoid http request handling timeouts.

    Args:
        cloud_account_id (int): the cloud account ID

    """
    logger.info(_("Deleting CloudAccount with ID %s"), cloud_account_id)
    cloud_accounts = CloudAccount.objects.filter(id=cloud_account_id)
    _delete_cloud_accounts(cloud_accounts)


def _delete_cloud_accounts(cloud_accounts):
    """
    Delete the given list of CloudAccount objects.

    Args:
        cloud_accounts (list[CloudAccount]): cloud accounts to delete

    """
    for cloud_account in cloud_accounts:
        # Lock on the user level, so that a single user can only have one task
        # running at a time.
        #
        # The select_for_update() lock has been moved from the CloudAccount to the
        # UserTaskLock. We should release the UserTaskLock with each
        # cloud_account.delete action.
        #
        # Using the UserTaskLock *should* fix the issue of Django not getting a
        # row-level lock in the DB for each CloudAccount we want to delete until
        # after all of the pre_delete logic completes
        with lock_task_for_user_ids([cloud_account.user.id]):
            # Call delete on the CloudAccount queryset instead of the specific
            # cloud_account. Why? A queryset delete does not raise DoesNotExist
            # exceptions if the cloud_account has already been deleted.
            # If we call delete on a nonexistent cloud_account, we run into trouble
            # with Django rollback and our task lock.
            # See https://gitlab.com/cloudigrade/cloudigrade/-/merge_requests/811
            try:
                cloud_account.refresh_from_db()
                _delete_cloud_account_related_objects(cloud_account)
                CloudAccount.objects.filter(id=cloud_account.id).delete()
            except CloudAccount.DoesNotExist:
                logger.info(
                    _("Cloud Account %s has already been deleted"), cloud_account
                )


def _delete_cloud_account_related_objects(cloud_account):
    """
    Quickly delete most objects related to a CloudAccount.

    This function deliberately bypasses the normal Django model delete calls and signals
    in an effort to improve performance with very large data sets. The tradeoff is that
    this function now has much greater knowledge of all potentially related models that
    would normally be resolved through generic relations.

    In practice, deleting a CloudAccount with ~290,000 related InstanceEvents previously
    took about 12 minutes to complete using normal Django model deletes with a local DB.
    This "optimized" function completes the same operation in about 2 seconds.

    Since we use generic relations and there is no direct relationship between some of
    our models' underlying tables, some of the operations here effectively build queries
    like "DELETE FROM table WHERE id IN (SELECT FROM other_table)" with the inner query
    retrieving the ids that we want to delete in the outer query.

    To further complicate this function, since deleting an Instance would normally also
    delete its MachineImage if no other related Instances use it, we have to recreate
    that logic here because we do not emit Instance.delete signals.

    Todo:
        A future iteration of this code could move it into a pre-delete signal for the
        actual CloudAccount model (and its related AwsCloudAccount, etc. models).
        If we do that, then there are additional changes we should make, such as
        dropping the pre- and post-delete signals from other models like Instance.

    Args:
        cloud_account (CloudAccount): the cloud account being deleted

    """
    # Delete ConcurrentUsages via Runs, but use the normal Django model "delete" since
    # these models have a many-to-many relationship that isn't defined with an explicit
    # "through" model. This means it's "slow" and iterates through each one, but that's
    # not as problematic performance-wise as the related Instances and InstanceEvents.
    concurrent_usages = ConcurrentUsage.objects.filter(
        potentially_related_runs__instance__cloud_account=cloud_account
    )
    concurrent_usages.delete()

    # Delete Runs via related Instances.
    runs = Run.objects.filter(instance__cloud_account=cloud_account)
    runs._raw_delete(runs.db)

    # define cloud-specific related classes to remove
    if isinstance(cloud_account.content_object, aws_models.AwsCloudAccount):
        instance_event_cloud_class = aws_models.AwsInstanceEvent
        instance_cloud_class = aws_models.AwsInstance
    elif isinstance(cloud_account.content_object, azure_models.AzureCloudAccount):
        instance_event_cloud_class = azure_models.AzureInstanceEvent
        instance_cloud_class = azure_models.AzureInstance
    else:
        # future-proofing...
        raise NotImplementedError(
            f"Unexpected cloud_account.content_object "
            f"{type(cloud_account.content_object)}"
        )

    # Delete {cloud}InstanceEvent by constructing a list of ids from InstanceEvent.
    cloud_instance_event_ids = InstanceEvent.objects.filter(
        content_type=ContentType.objects.get_for_model(instance_event_cloud_class),
        instance__cloud_account=cloud_account,
    ).values_list("object_id", flat=True)
    cloud_instance_events = instance_event_cloud_class.objects.filter(
        id__in=cloud_instance_event_ids
    )
    cloud_instance_events._raw_delete(cloud_instance_events.db)

    # Delete {cloud}Instance by constructing a list of ids from Instance.
    cloud_instance_ids = Instance.objects.filter(
        content_type=ContentType.objects.get_for_model(instance_cloud_class),
        cloud_account=cloud_account,
    ).values_list("object_id", flat=True)
    cloud_instances = instance_cloud_class.objects.filter(id__in=cloud_instance_ids)
    cloud_instances._raw_delete(cloud_instances.db)

    # Delete InstanceEvents via related Instances.
    instance_events = InstanceEvent.objects.filter(
        instance__cloud_account=cloud_account
    )
    instance_events._raw_delete(instance_events.db)

    # Before deleting the Instances, fetch the list of related MachineImage ids that are
    # being used by any Instances belonging to this cloud account. Note that we wrap the
    # queryset with set() to force it to evaluate *now* since lazy evaluation later may
    # not work after we delete this CloudAccount's Instances.
    machine_image_ids = set(
        Instance.objects.filter(cloud_account=cloud_account).values_list(
            "machine_image_id", flat=True
        )
    )

    # Delete Instances.
    instances = Instance.objects.filter(cloud_account=cloud_account)
    instances._raw_delete(instances.db)

    # Using that list of MachineImage ids used by this CloudAccount's Instances, find
    # and delete (using normal Django delete) any MachineImages that are no longer being
    # used by other Instances (belonging to other CloudAccounts).
    active_machine_image_ids = (
        Instance.objects.filter(machine_image_id__in=machine_image_ids)
        .exclude(cloud_account=cloud_account)
        .values_list("machine_image_id", flat=True)
    )
    delete_machine_image_ids = set(machine_image_ids) - set(active_machine_image_ids)
    MachineImage.objects.filter(id__in=delete_machine_image_ids).delete()
