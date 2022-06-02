"""Tasks for various calculation operations."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from api.models import CloudAccount, ConcurrentUsage, InstanceEvent, Run
from api.models import User
from api.util import (
    calculate_max_concurrent_usage,
    get_runs_for_user_id_on_date,
    recalculate_runs,
    recalculate_runs_for_cloud_account_id as _recalculate_runs_for_cloud_account_id,
    recalculate_runs_for_instance_id as _recalculate_runs_for_instance_id,
)
from util.misc import get_today

logger = logging.getLogger(__name__)


@transaction.atomic()
def _fix_problematic_run(run_id):
    """
    Try to fix a problematic Run that should have an end_date but doesn't.

    This is the "fix it" half corresponding to find_problematic_runs.
    """
    try:
        run = Run.objects.get(id=run_id)
    except Run.DoesNotExist:
        # The run was already deleted or updated before we got to it. Moving on...
        logger.info(
            _("Run %(run_id)s does not exist and cannot be fixed"), {"run_id": run_id}
        )
        return

    oldest_power_off_event_since_run_start = (
        InstanceEvent.objects.filter(
            instance_id=run.instance_id,
            occurred_at__gte=run.start_time,
            event_type=InstanceEvent.TYPE.power_off,
        )
        .order_by("occurred_at")
        .first()
    )
    if not oldest_power_off_event_since_run_start:
        # There is no power_off event. Why are you even here? Moving on...
        logger.info(_("No relevant InstanceEvent exists for %(run)s"), {"run": run})
        return

    if run.end_time == oldest_power_off_event_since_run_start.occurred_at:
        # This run actually appears to be okay. Moving on...
        logger.info(
            _(
                "%(run)s does not appear to require fixing; "
                "oldest related power_off event is %(event)s"
            ),
            {"run": run, "event": oldest_power_off_event_since_run_start},
        )
        return

    # Note: recalculate_runs should fix the identified run above *and* (re)create any
    # subsequent runs that would exist for any events *after* this event occurred.
    logger.warning(
        _(
            "Attempting to fix problematic runs starting with "
            "%(run)s which should end with %(event)s"
        ),
        {"event": oldest_power_off_event_since_run_start, "run": run},
    )
    recalculate_runs(oldest_power_off_event_since_run_start)


@shared_task(name="api.tasks.fix_problematic_runs")
def fix_problematic_runs(run_ids):
    """Fix list of problematic runs in an async task."""
    for run_id in run_ids:
        _fix_problematic_run(run_id)


@shared_task(name="api.tasks.recalculate_runs_for_instance_id")
def recalculate_runs_for_instance_id(instance_id):
    """
    Recalculate recent Runs for the given cloud account id.

    This is simply a Celery task wrapper for recalculate_runs_for_instance_id.
    """
    _recalculate_runs_for_instance_id(instance_id)


@shared_task(name="api.tasks.recalculate_runs_for_cloud_account_id")
def recalculate_runs_for_cloud_account_id(cloud_account_id, since=None):
    """
    Recalculate recent Runs for the given cloud account id.

    This is simply a Celery task wrapper for recalculate_runs_for_cloud_account_id.
    """
    _recalculate_runs_for_cloud_account_id(cloud_account_id, since)


@shared_task(name="api.tasks.recalculate_runs_for_all_cloud_accounts")
def recalculate_runs_for_all_cloud_accounts(since=None):
    """
    Recalculate recent runs for all cloud accounts.

    Except synthetic accounts. All of their runs and concurrent usage are calculated
    once during initial synthesis and never need to be recalculated again after that.
    """
    cloud_accounts = CloudAccount.objects.filter(is_synthetic=False)
    for cloud_account in cloud_accounts:
        recalculate_runs_for_cloud_account_id.apply_async(
            args=(cloud_account.id, since), serializer="pickle"
        )


@shared_task(name="api.tasks.recalculate_concurrent_usage_for_user_id_on_date")
@transaction.atomic()
def recalculate_concurrent_usage_for_user_id_on_date(user_id, date):
    """
    Recalculate ConcurrentUsage for the given user id and date, but only if necessary.

    Before performing the actual calculations, this function checks any existing
    ConcurrentUsage and Run objects that may be relevant. Only perform the calculations
    if there is no saved ConcurrentUsage data or if we find Runs that should be counted.

    Args:
        user_id (int): user id
        date (datetime.date): date of the calculated concurrent usage
    """
    try:
        usage = ConcurrentUsage.objects.get(user_id=user_id, date=date)
        # **Django internal leaky abstraction warning!!**
        # The following querysets have a seemingly useless "order_by()" on their ends,
        # but these are important because Django's "difference" query builder refuses
        # to build a working query if the compound querysets are ordered. Applying the
        # empty "order_by()" forces those querysets *not* to have an ORDER BY clause.
        # If you don't explicitly clear the order, Django always orders as defined in
        # the model, and our BaseModel defines `ordering = ("created_at",)`.
        # See also django.db.utils.DatabaseError:
        # ORDER BY not allowed in subqueries of compound statements.
        runs_queryset = get_runs_for_user_id_on_date(user_id, date).order_by()
        difference = runs_queryset.difference(usage.potentially_related_runs.order_by())
        needs_calculation = difference.exists()
        logger.debug(
            _(
                "ConcurrentUsage needs calculation for user %(user_id)s on %(date)s "
                "because %(difference_count)s Runs are not in potentially_related_runs"
            ),
            {
                "difference_count": difference.count(),
                "user_id": user_id,
                "date": date,
            },
        )
    except ConcurrentUsage.DoesNotExist:
        logger.debug(
            _(
                "ConcurrentUsage needs calculation for user %(user_id)s on %(date)s "
                "because ConcurrentUsage.DoesNotExist"
            ),
            {
                "user_id": user_id,
                "date": date,
            },
        )
        needs_calculation = True

    if needs_calculation:
        calculate_max_concurrent_usage(date, user_id)


@shared_task(
    name="api.tasks.recalculate_concurrent_usage_for_user_id", serializer="pickle"
)
def recalculate_concurrent_usage_for_user_id(user_id, since=None):
    """
    Recalculate recent ConcurrentUsage for the given user id.

    Args:
        user_id (int): user id
        since (datetime.date): optional starting date to search for runs
    """
    today = get_today()
    if not since:
        days_ago = settings.RECALCULATE_CONCURRENT_USAGE_SINCE_DAYS_AGO
        since = today - timedelta(days=days_ago)
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        # The user may have been deleted before this task started.
        logger.info(
            _("User id %(user_id)s not found; skipping concurrent usage calculation"),
            {"user_id": user_id},
        )
        return
    date_joined = user.date_joined.date()
    one_day = timedelta(days=1)

    # Only calculate since the user joined. Older dates would always have empty data.
    target_day = max(date_joined, since)
    # Stop calculation on "today". Never project future dates because data will change.
    while target_day <= today:
        # Important note! apply_async with serializer="pickle" is required here because
        # the "target_day" object is a datetime.date which the default serializer
        # converts to a plain string like "2021-05-01T00:00:00".
        recalculate_concurrent_usage_for_user_id_on_date.apply_async(
            args=(user_id, target_day), serializer="pickle"
        )
        target_day += one_day


@shared_task(name="api.tasks.recalculate_concurrent_usage_for_all_users")
def recalculate_concurrent_usage_for_all_users(since=None):
    """
    Recalculate recent ConcurrentUsage for all Users.

    Args:
        since (datetime.date): optional starting date for calculating concurrent usage
    """
    for user in User.objects.all():
        # Important note! apply_async with serializer="pickle" is required here because
        # the "since" object is a datetime.date which the default serializer converts
        # to a plain string like "2021-05-01T00:00:00".
        recalculate_concurrent_usage_for_user_id.apply_async(
            args=(user.id, since), serializer="pickle"
        )
