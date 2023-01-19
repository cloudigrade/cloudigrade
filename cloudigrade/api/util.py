"""Utility functions."""
import logging

from django.utils.translation import gettext as _

from api.models import (
    ConcurrentUsage,
)
from util.misc import get_today

logger = logging.getLogger(__name__)


def get_max_concurrent_usage(date, user_id):
    """
    Get maximum concurrent usage of RHEL instances in given parameters.

    This only gets a pre-calculated version of the results from ConcurrentUsage.
    We never perform the underlying calculation as a side-effect of this function.

    Args:
        date (datetime.date): the day during which we are measuring usage
        user_id (int): required filter on user

    Returns:
        ConcurrentUsage for the give date and user_id, or None if not found.

    """
    logger.debug(
        "Getting Concurrent usage for user_id: %(user_id)s, date: %(date)s"
        % {"user_id": user_id, "date": date}
    )

    today = get_today()
    if date > today:
        # Early return because we never attempt to project future calculations.
        return None

    try:
        logger.info(
            _("Fetching ConcurrentUsage(date=%(date)s, user_id=%(user_id)s)"),
            {"date": date, "user_id": user_id},
        )
        concurrent_usage = ConcurrentUsage.objects.get(date=date, user_id=user_id)
        return concurrent_usage
    except ConcurrentUsage.DoesNotExist:
        logger.info(
            _("Could not find ConcurrentUsage(date=%(date)s, user_id=%(user_id)s)"),
            {"date": date, "user_id": user_id},
        )

    return None
