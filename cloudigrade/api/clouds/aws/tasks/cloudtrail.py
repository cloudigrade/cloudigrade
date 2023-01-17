"""Celery tasks related to interactions with AWS CloudTrail."""
from celery import shared_task


@shared_task(name="api.clouds.aws.tasks.analyze_log")
def analyze_log():
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
