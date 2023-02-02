"""Tasks for various calculation operations."""
from celery import shared_task


@shared_task(name="api.tasks.fix_problematic_runs")
def fix_problematic_runs(run_ids):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
