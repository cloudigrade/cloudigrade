"""Celery tasks related to the AWS image inspection process."""
import logging

from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@retriable_shared_task(name="api.clouds.aws.tasks.launch_inspection_instance")
def launch_inspection_instance(ami_id, snapshot_copy_id):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
    return False
