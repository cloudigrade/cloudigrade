"""Tasks for various calculation operations."""
from celery import shared_task


@shared_task(name="api.tasks.fix_problematic_runs")
def fix_problematic_runs(run_ids):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.recalculate_runs_for_cloud_account_id")
def recalculate_runs_for_cloud_account_id(cloud_account_id, since=None):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.recalculate_runs_for_all_cloud_accounts")
def recalculate_runs_for_all_cloud_accounts(since=None):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(
    name="api.tasks.recalculate_concurrent_usage_for_user_id", serializer="pickle"
)
def recalculate_concurrent_usage_for_user_id(user_id, since=None):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
