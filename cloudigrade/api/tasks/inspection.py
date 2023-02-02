"""Tasks for various inspection operations."""
from celery import shared_task


@shared_task(name="api.tasks.inspect_pending_images")
def inspect_pending_images():
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
