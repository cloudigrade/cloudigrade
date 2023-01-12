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


@retriable_shared_task(name="api.clouds.aws.tasks.copy_ami_to_customer_account")
def copy_ami_to_customer_account(arn, reference_ami_id, snapshot_region):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@retriable_shared_task(name="api.clouds.aws.tasks.remove_snapshot_ownership")
def remove_snapshot_ownership(
    arn, customer_snapshot_id, customer_snapshot_region, snapshot_copy_id
):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@retriable_shared_task(name="api.clouds.aws.tasks.delete_snapshot")
def delete_snapshot(snapshot_copy_id, ami_id, snapshot_region):
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
