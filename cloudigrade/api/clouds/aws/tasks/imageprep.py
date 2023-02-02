"""Celery tasks related to preparing AWS images for inspection."""
import logging

from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@retriable_shared_task(name="api.clouds.aws.tasks.copy_ami_snapshot")
def copy_ami_snapshot(arn, ami_id, snapshot_region, reference_ami_id=None):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
