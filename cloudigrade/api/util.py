"""Utility functions."""
import collections
import itertools
import logging
from datetime import datetime, timedelta
from uuid import uuid4

from dateutil import tz
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api.models import (
    ConcurrentUsage,
    ConcurrentUsageCalculationTask,
    Instance,
    InstanceDefinition,
    InstanceEvent,
    Run,
)
from util.exceptions import ResultsUnavailable
from util.misc import get_today

logger = logging.getLogger(__name__)

cloud_account_name_pattern = "{cloud_name}-account-{external_cloud_account_id}"

ANY = "_ANY"


def get_last_known_instance_type(instance, before_date):
    """
    Get the last known type for the given instance.

    Important note:
        This function assumes AWS is our only cloud, and this will require
        refactoring in order to determine the type from other cloud events.

    Args:
        instance (Instance): instance to check
        before_date (datetime.datetime): cutoff for checking events for type

    Returns:
        str: The last known instance type or None if no type is found.

    """
    # raise Exception
    event = (
        InstanceEvent.objects.filter(
            instance=instance,
            occurred_at__lte=before_date,
            aws_instance_event__instance_type__isnull=False,
        )
        .order_by("-occurred_at")
        .first()
    )
    if event is None:
        logger.error(
            _("Could not find any type for %(instance)s by %(before_date)s"),
            {"instance": instance, "before_date": before_date},
        )
        return None
    return event.content_object.instance_type


NormalizedRun = collections.namedtuple(
    "NormalizedRun",
    [
        "start_time",
        "end_time",
        "image_id",
        "instance_id",
        "instance_memory",
        "instance_type",
        "instance_vcpu",
        "is_cloud_access",
        "is_encrypted",
        "is_marketplace",
        "openshift",
        "openshift_detected",
        "rhel",
        "rhel_detected",
    ],
)


def get_instance_type_definition(instance_type, cloud_type):
    """Gracefully get the definition for the instance type."""
    try:
        type_definition = (
            InstanceDefinition.objects.get(
                instance_type=instance_type, cloud_type=cloud_type
            )
            if instance_type
            else None
        )
    except InstanceDefinition.DoesNotExist:
        type_definition = None
    return type_definition


def normalize_runs(events):  # noqa: C901
    """
    Create list of "runs" with normalized event information.

    These runs should have all the relevant reporting information about when
    an instance ran for a period of time so we don't have to keep going back
    and forth through events to collect bits of information we need.

    Args:
        events (list[InstanceEvent]): list of relevant events

    Returns:
        list(NormalizedRun).

    """
    sorted_events_by_instance = itertools.groupby(
        sorted(events, key=lambda e: f"{e.instance_id}_{e.occurred_at}"),
        key=lambda e: e.instance_id,
    )

    normalized_runs = []
    for instance_id, events in sorted_events_by_instance:
        events = list(events)  # events is not subscriptable from the groupby.
        instance_type = events[
            0
        ].content_object.instance_type or get_last_known_instance_type(
            events[0].instance, events[0].occurred_at
        )
        cloud_type = events[0].cloud_type
        type_definition = get_instance_type_definition(instance_type, cloud_type)
        start_run = None
        end_run = None
        image = Instance.objects.get(id=instance_id).machine_image

        for event in events:
            if event.event_type == event.TYPE.power_on:
                if start_run is None:
                    # Only set if not already set. Why? This allows us to
                    # handle spurious start events, as if the event sequence we
                    # receive is: "start start stop"
                    start_run = event.occurred_at
                    end_run = None
            elif event.event_type == event.TYPE.power_off:
                end_run = event.occurred_at

            if start_run and image is None:
                logger.warning(
                    _("Instance %s does not have an associated machine image."),
                    instance_id,
                )

            if start_run and end_run:
                # The instance completed a start-stop cycle.
                run = NormalizedRun(
                    start_time=start_run,
                    end_time=end_run,
                    image_id=image.id if image else None,
                    instance_id=instance_id,
                    instance_type=instance_type,
                    instance_memory=type_definition.memory if type_definition else None,
                    instance_vcpu=type_definition.vcpu if type_definition else None,
                    is_cloud_access=image.is_cloud_access if image else False,
                    is_encrypted=image.is_encrypted if image else False,
                    is_marketplace=image.is_marketplace if image else False,
                    openshift=image.openshift if image else False,
                    openshift_detected=image.openshift_detected if image else False,
                    rhel=image.rhel if image else False,
                    rhel_detected=image.rhel_detected if image else False,
                )
                normalized_runs.append(run)
                start_run = None
                end_run = None

        if start_run and not end_run:
            # When the instance was started but never stopped.
            run = NormalizedRun(
                start_time=start_run,
                end_time=None,
                image_id=image.id if image else None,
                instance_id=instance_id,
                instance_type=instance_type,
                instance_memory=type_definition.memory if type_definition else None,
                instance_vcpu=type_definition.vcpu if type_definition else None,
                is_cloud_access=image.is_cloud_access if image else False,
                is_encrypted=image.is_encrypted if image else False,
                is_marketplace=image.is_marketplace if image else False,
                openshift=image.openshift if image else False,
                openshift_detected=image.openshift_detected if image else False,
                rhel=image.rhel if image else False,
                rhel_detected=image.rhel_detected if image else False,
            )
            normalized_runs.append(run)

    return normalized_runs


def get_max_concurrent_usage(date, user_id):
    """
    Get maximum concurrent usage of RHEL instances in given parameters.

    This may get a pre-calculated version of the results from ConcurrentUsage. We
    attempt to load stored results from the database; we only perform the underlying
    calculation (and save results for future requests) if the result does not yet exist.

    Args:
        date (datetime.date): the day during which we are measuring usage
        user_id (int): required filter on user

    Returns:
        ConcurrentUsage for the give date and user_id.

    """
    today = get_today()
    if date > today:
        # Early return stub values; we never project future calculations.
        return ConcurrentUsage(date=date, user_id=user_id)

    try:
        concurrent_usage = ConcurrentUsage.objects.get(date=date, user_id=user_id)
        return concurrent_usage
    except ConcurrentUsage.DoesNotExist:
        # If it does not exist, we will create it after this exception handler.
        pass

    last_calculation_task = get_last_scheduled_concurrent_usage_calculation_task(
        user_id, date
    )
    if last_calculation_task is not None:
        if last_calculation_task.status == ConcurrentUsageCalculationTask.SCHEDULED:
            last_calculation_task.cancel()
        elif last_calculation_task.status == ConcurrentUsageCalculationTask.RUNNING:
            raise ResultsUnavailable()

    concurrent_usage_data = calculate_max_concurrent_usage(date=date, user_id=user_id)
    return concurrent_usage_data


def calculate_max_concurrent_usage(date, user_id):
    """
    Calculate maximum concurrent usage of RHEL instances in given parameters.

    This always performs a new calculation of the results based on Runs.
    Results are saved to the database before returning as a ConcurrentUsage object.
    Any preexisting saved results will be replaced with newly calculated results.

    Args:
        date (datetime.date): the day during which we are measuring usage
        user_id (int): required filter on user

    Returns:
        ConcurrentUsage for the given date and user ID.

    """
    if not User.objects.filter(id=user_id).exists():
        # Return empty stub object if user doesn't exist.
        # TODO Is this even possible to reach via the API?
        return ConcurrentUsage(date=date, user_id=user_id)

    queryset = Run.objects.filter(instance__cloud_account__user__id=user_id)

    start = datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=tz.tzutc())
    end = start + timedelta(days=1)

    # We want to filter to Runs that have:
    # - started before (not inclusive) our end time
    # - ended at or after our start time (inclusive) or have never stopped
    runs = queryset.filter(
        Q(end_time__isnull=True) | Q(end_time__gte=start), start_time__lt=end,
    ).prefetch_related("machineimage")

    # Now that we have the Runs, we need to extract the start and stop times
    # from each Run, put them in a list, and order them chronologically. If we
    # ever want to know about concurrency for things other than RHEL, we would
    # repeat the following pattern for each other filter/condition.
    rhel_on_offs = []
    for run in runs:
        if not run.machineimage.rhel:
            continue
        rhel_on_offs.append(
            (
                run.start_time,
                True,
                run.vcpu,
                run.memory,
                run.instance.cloud_account.cloud_account_id,
                run.instance.cloud_type,
                run.instance.cloud_instance_id,
                run.instance.machine_image.rhel_version,
                run.instance.machine_image.syspurpose,
                run.instance.machine_image.architecture,
            )
        )

        if run.end_time:
            rhel_on_offs.append(
                (
                    run.end_time,
                    False,
                    run.vcpu,
                    run.memory,
                    run.instance.cloud_account.cloud_account_id,
                    run.instance.cloud_type,
                    run.instance.cloud_instance_id,
                    run.instance.machine_image.rhel_version,
                    run.instance.machine_image.syspurpose,
                    run.instance.machine_image.architecture,
                )
            )

    rhel_on_offs = sorted(rhel_on_offs, key=lambda r: r[0])

    # Now that we have the start and stop times ordered, we can easily find the
    # maximum concurrency by walking forward in time and counting up.
    complex_maximum_counts = {}
    for (
        __,
        is_start,
        vcpu,
        memory,
        instance_cloud_account_id,
        cloud_type,
        instance_id,
        rhel_version,
        syspurpose,
        architecture,
    ) in rhel_on_offs:
        complex_maximum_counts = _record_results(
            complex_maximum_counts, is_start, syspurpose, architecture
        )

    # complex_maximum_counts is a dict with objects for keys that cannot natively
    # convert to JSON for storage and eventual API output. So, we simplify it here.
    simplified_maximum_counts = []
    for key, value in complex_maximum_counts.items():
        simplified_maximum_counts.append(
            {
                "arch": key.arch,
                "role": key.role,
                "sla": key.sla,
                "instances_count": value["max_count"],
            }
        )

    with transaction.atomic():
        ConcurrentUsage.objects.select_for_update().filter(
            date=date, user_id=user_id
        ).delete()
        concurrent_usage = ConcurrentUsage.objects.create(
            date=date, user_id=user_id, maximum_counts=simplified_maximum_counts
        )
        concurrent_usage.potentially_related_runs.add(*runs)
        concurrent_usage.save()

    return concurrent_usage


def _record_results(results, is_start, syspurpose=None, arch=None):
    """
    Process data from the runs and tally up concurrent counts.

    Args:
        results (dict): The results dict that'll be populated with counts.
        is_start (bool): Is this a start event?
        syspurpose (dict): Optional. Dict representing the sypurpose.
        arch (str): Optional. Architecture of the image.

    Returns:
        Dict: The updated results dictionary.

    """
    role = syspurpose.get("role", "")[:64] if syspurpose is not None else ""
    sla = (
        syspurpose.get("service_level_agreement", "")[:64]
        if syspurpose is not None
        else ""
    )
    arch = arch if arch is not None else ""

    ConcurrentKey = collections.namedtuple("ConcurrentKey", ["role", "sla", "arch"])

    # first, get the main _ANY count recorded
    key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY)
    results = _record_concurrency_count(results, key, is_start)

    # Do we have an sla? Let's file that next
    if sla:
        key = ConcurrentKey(role=ANY, sla=sla, arch=ANY)
        results = _record_concurrency_count(results, key, is_start)

    # Unknown SLA?
    if sla == "":
        key = ConcurrentKey(role=ANY, sla=sla, arch=ANY)
        results = _record_concurrency_count(results, key, is_start)

    # Do we have a role and an sla?
    if sla and role:
        key = ConcurrentKey(role=role, sla=sla, arch=ANY)
        results = _record_concurrency_count(results, key, is_start)

    # How about known role and unknown sla?
    if role and sla == "":
        key = ConcurrentKey(role=role, sla=sla, arch=ANY)
        results = _record_concurrency_count(results, key, is_start)

    # Known arch and known sla
    if arch and sla:
        key = ConcurrentKey(role=ANY, sla=sla, arch=arch)
        results = _record_concurrency_count(results, key, is_start)

    # Finally, arch and unknown sla
    if arch and sla == "":
        key = ConcurrentKey(role=ANY, sla=sla, arch=arch)
        results = _record_concurrency_count(results, key, is_start)

    return results


def _record_concurrency_count(results, key, is_start):
    """Record the count."""
    entry = results.setdefault(key, {"current_count": 0, "max_count": 0,})
    entry["current_count"] += 1 if is_start else -1
    entry["max_count"] = max(entry["current_count"], entry["max_count"])

    return results


def calculate_max_concurrent_usage_from_runs(runs):
    """
    Calculate maximum concurrent usage of RHEL instances from given Runs.

    We try to find the common intersection of the given runs across the dates,
    users, and cloud accounts referenced in the given Runs.
    """
    date_user_cloud_accounts = set()

    # This nested set of for loops should find the set of all days, user_ids,
    # and cloud_account_ids that may be affected by the given Runs. All of
    # those combinations need to have their max concurrent usage calculated.
    for run in runs:
        start_date = run.start_time.date()
        if run.end_time is not None:
            end_date = run.end_time.date()
        else:
            # No end time on the run? Act like the run ends "today".
            end_date = get_today()
        # But really the end is *tomorrow* since the end is exclusive.
        end_date = end_date + timedelta(days=1)
        user_id = run.instance.cloud_account.user.id
        delta_days = (end_date - start_date).days
        for offset in range(delta_days):
            date = start_date + timedelta(days=offset)
            date_user_cloud_account = (date, user_id)
            date_user_cloud_accounts.add(date_user_cloud_account)
            date_user_no_cloud_account = (date, user_id)
            date_user_cloud_accounts.add(date_user_no_cloud_account)

    for date, user_id in date_user_cloud_accounts:

        # If we already have a concurrent usage calculation task with the same userid
        # same date, and status=SCHEDULED, then we do not run this

        last_calculate_task = get_last_scheduled_concurrent_usage_calculation_task(
            user_id=user_id, date=date
        )

        # If no such task exists, then schedule one
        if last_calculate_task is None:
            schedule_concurrent_calculation_task(date, user_id)
        # If this task is already complete or is in the process of running,
        # then we schedule a new task.
        elif last_calculate_task.status != ConcurrentUsageCalculationTask.SCHEDULED:
            schedule_concurrent_calculation_task(date, user_id)

        # If the task is scheduled (but has not started running) and it has been
        # in the queue for too long, then we revoke it and schedule a new task.
        elif last_calculate_task.created_at < datetime.now(tz=tz.tzutc()) - timedelta(
            seconds=settings.CONCURRENT_USAGE_CALCULATION_DELAY
        ):
            logger.info(
                "Previous scheduled task to calculate concurrent usage for "
                "user_id: %(user_id)s and date: %(date)s has expired. "
                "Scheduling new calculation task." % {"user_id": user_id, "date": date}
            )
            last_calculate_task.cancel()
            schedule_concurrent_calculation_task(date, user_id)
        logger.info(
            "Task to calculate concurrent usage for user_id: %(user_id)s and "
            "date: %(date)s already exists." % {"user_id": user_id, "date": date}
        )


def schedule_concurrent_calculation_task(date, user_id):
    """
    Start a task to calculate the concurrent usage calculation.

    This is needed because we always want a ConcurrentUsageCalculationTask
    object created to track the task.

    Args:
        user_id (int): id of the user
        date (date): date to calculate the concurrent usage.
    """
    logger.info(
        "Scheduling Task to calculate concurrent usage for user_id: "
        "%(user_id)s and date: %(date)s." % {"user_id": user_id, "date": date}
    )

    from api.tasks import calculate_max_concurrent_usage_task

    task_id = f"calculate-concurrent-usage-{uuid4()}"

    ConcurrentUsageCalculationTask.objects.create(
        user_id=user_id, date=date, task_id=task_id
    )
    calculate_max_concurrent_usage_task.apply_async(
        kwargs={"date": date, "user_id": user_id},
        countdown=settings.CONCURRENT_USAGE_CALCULATION_DELAY,
        task_id=task_id,
    )


def recalculate_runs(event):
    """
    Take in an event and (re)calculate runs based on it.

    The simplest use case here is if the event is newer than any runs, and that
    means a new run may be created. The more complex use case is if the event
    occurred during or before existing runs, and that means any overlapping or
    future runs must be deleted and recreated.
    """
    # Get all runs that occurred after event or occurred during event.
    after_run = Q(start_time__gt=event.occurred_at)
    during_run = Q(start_time__lte=event.occurred_at, end_time__gt=event.occurred_at)
    during_run_no_end = Q(start_time__lte=event.occurred_at, end_time=None)
    filters = after_run | during_run | during_run_no_end
    runs = Run.objects.filter(filters, instance_id=event.instance_id)

    # Get the earliest time of relevant runs.
    # We can use this as a baseline to fetch all relevant events.
    # All of these runs get torched, since we recalculate them based
    # on the newest event.
    # If no runs exist in this query, this event is the start of a new run
    try:
        earliest_run = (
            runs.earliest("start_time").start_time
            if runs.earliest("start_time").start_time < event.occurred_at
            else event.occurred_at
        )
    except Run.DoesNotExist:
        if event.event_type == event.TYPE.power_on:
            normalized_runs = normalize_runs([event])
            saved_runs = []
            for index, normalized_run in enumerate(normalized_runs):
                logger.info(
                    "Processing run %(index)s of %(runs)s",
                    {"index": index + 1, "runs": len(normalized_runs)},
                )
                run = Run(
                    start_time=normalized_run.start_time,
                    end_time=normalized_run.end_time,
                    machineimage_id=normalized_run.image_id,
                    instance_id=normalized_run.instance_id,
                    instance_type=normalized_run.instance_type,
                    memory=normalized_run.instance_memory,
                    vcpu=normalized_run.instance_vcpu,
                )
                run.save()
                saved_runs.append(run)
            calculate_max_concurrent_usage_from_runs(runs)
        return

    events = (
        InstanceEvent.objects.filter(
            instance_id=event.instance_id, occurred_at__gte=earliest_run
        )
        .select_related("instance")
        .order_by("occurred_at")
    )

    normalized_runs = normalize_runs(events)
    with transaction.atomic():
        runs.delete()
        saved_runs = []
        for index, normalized_run in enumerate(normalized_runs):
            logger.info(
                "Processing run %(index)s of %(runs)s",
                {"index": index + 1, "runs": len(normalized_runs)},
            )
            run = Run(
                start_time=normalized_run.start_time,
                end_time=normalized_run.end_time,
                machineimage_id=normalized_run.image_id,
                instance_id=normalized_run.instance_id,
                instance_type=normalized_run.instance_type,
                memory=normalized_run.instance_memory,
                vcpu=normalized_run.instance_vcpu,
            )
            run.save()
            saved_runs.append(run)
        calculate_max_concurrent_usage_from_runs(runs)


def convert_param_to_int(name, value):
    """Check if a value is convertible to int.

    Args:
        name (str): The field name being validated
        value: The value to convert to int

    Returns:
        int: The int value
    Raises:
        ValidationError if value not convertable to an int

    """
    try:
        return int(value)
    except ValueError:
        error = {name: [_("{} must be an integer.".format(name))]}
        raise ValidationError(error)


def get_standard_cloud_account_name(cloud_name, external_cloud_account_id):
    """
    Get cloudigrade's standard CloudAccount name for a given account ID.

    Args:
        cloud_name (str): cloud name (e.g. 'aws')
        external_cloud_account_id (str): customer's external cloud account id

    Returns:
        str of cloudigrade's standard CloudAccount name

    """
    return cloud_account_name_pattern.format(
        cloud_name=cloud_name, external_cloud_account_id=external_cloud_account_id,
    )


def get_last_scheduled_concurrent_usage_calculation_task(user_id, date):
    """Get the last created concurrent usage calculation task."""
    if ConcurrentUsageCalculationTask.objects.filter(
        user__id=user_id, date=date
    ).exists():
        return ConcurrentUsageCalculationTask.objects.filter(
            user__id=user_id, date=date
        ).latest("created_at")
    return None
