"""Celery tasks related to maintenance functions around Azure."""

from util.celery import retriable_shared_task


@retriable_shared_task(name="api.clouds.azure.tasks.repopulate_azure_instance_mapping")
def repopulate_azure_instance_mapping():
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
