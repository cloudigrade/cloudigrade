"""
Tasks for synthesizing data for live service testing.

Many of these tasks return the exact same arguments they are given, assuming they
complete successfully, in order to facilitate task chaining or chording.
"""
import logging
import secrets
from datetime import date
from typing import Optional

from celery import shared_task

logger = logging.getLogger(__name__)
random = secrets.SystemRandom()


@shared_task(name="api.tasks.synthesize_user")
def synthesize_user(request_id: int) -> Optional[int]:
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.synthesize_cloud_accounts")
def synthesize_cloud_accounts(request_id: int) -> Optional[int]:
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.synthesize_images")
def synthesize_images(request_id: int) -> Optional[int]:
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.synthesize_instances")
def synthesize_instances(request_id: int) -> Optional[int]:
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.synthesize_instance_events")
def synthesize_instance_events(request_id: int) -> Optional[int]:
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.synthesize_runs_and_usage")
def synthesize_runs_and_usage(request_id: int) -> Optional[int]:
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.tasks.synthesize_concurrent_usage", serializer="pickle")
def synthesize_concurrent_usage(__: object, user_id: int, on_date: date) -> int:
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
