"""Miscellaneous utility functions."""
import datetime
import logging
from contextlib import contextmanager

from django.db import transaction

logger = logging.getLogger(__name__)


def generate_device_name(index, prefix="/dev/xvd"):
    """
    Generate a linux device name based on provided index and prefix.

    Args:
        index (int): Index of the device to generate the name for.
        prefix (str): Prefix for the device name.

    Returns (str): Generated device name.

    """
    return f"{prefix}" f'{chr(ord("b") + int(index / 26)) + chr(ord("a") + index % 26)}'


def truncate_date(original):
    """
    Ensure the date is in the past or present, not the future.

    Args:
        original (datetime): some datetime to optionally truncate

    Returns:
        datetime: original or "now" if base is in the future

    """
    now = datetime.datetime.now(tz=original.tzinfo)
    return min(original, now)


def get_today():
    """
    Get the date from the current time in UTC.

    This function exists so we don't proliferate many different ways of getting
    the current UTC date. It also provides a convenient single place to patch
    in unit tests.

    Returns:
        datetime.date the current date in UTC.

    """
    return get_now().date()


def get_now():
    """
    Get the current time in UTC.

    This function exists so we don't proliferate many different ways of getting
    the current UTC time. It also provides a convenient single place to patch
    in unit tests.

    Returns:
        datetime.datetime the current datetime in UTC.

    """
    return datetime.datetime.now(datetime.timezone.utc)


@contextmanager
def lock_task_for_user_ids(user_ids):
    """
    Create and hold open a UserTaskLock for the duration of a transaction.

    For many of our tasks, we only want run one for a user at a time.
    This context manager is a way for us to "lock" tasks for a user_id for
    an atomic transaction.

    Args:
        user_ids (list[str]): A list of user_ids to lock

    """
    from api.models import UserTaskLock

    logger.info(
        "Locking user_ids %(user_ids)s until transaction is committed.",
        {"user_ids": user_ids},
    )
    with transaction.atomic():
        for user_id in user_ids:
            UserTaskLock.objects.get_or_create(user_id=user_id)
        locks = UserTaskLock.objects.select_for_update().filter(user__id__in=user_ids)
        locks.update(locked=True)
        yield locks
        locks.update(locked=False)
        logger.info("Unlocking user_ids %(user_ids)s.", {"user_ids": user_ids})
