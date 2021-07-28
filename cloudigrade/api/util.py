"""Utility functions."""
import collections
import itertools
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from dateutil import tz
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from tqdm import tqdm

from api.models import (
    ConcurrentUsage,
    Instance,
    InstanceDefinition,
    InstanceEvent,
    Run,
)
from util.misc import get_now, get_today

logger = logging.getLogger(__name__)

cloud_account_name_pattern = "{cloud_name}-account-{external_cloud_account_id}"

ANY = "_ANY"

ConcurrentKey = collections.namedtuple(
    "ConcurrentKey", ["role", "sla", "arch", "usage", "service_type"]
)


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
        logger.warning(
            _("Could not find any type for %(instance)s by %(before_date)s"),
            {"instance": instance, "before_date": before_date},
        )
        return None
    return event.content_object.instance_type


DenormalizedRun = collections.namedtuple(
    "DenormalizedRun",
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


def denormalize_runs(events):  # noqa: C901
    """
    Create list of "runs" with denormalized event information.

    These runs should have all the relevant reporting information about when
    an instance ran for a period of time so we don't have to keep going back
    and forth through events to collect bits of information we need.

    Args:
        events (list[InstanceEvent]): list of relevant events

    Returns:
        list(DenormalizedRun).

    """
    sorted_events_by_instance = itertools.groupby(
        sorted(events, key=lambda e: f"{e.instance_id}_{e.occurred_at}"),
        key=lambda e: e.instance_id,
    )

    denormalized_runs = []
    for instance_id, events in sorted_events_by_instance:
        events = list(events)  # events is not subscriptable from the groupby.
        instance_type = events[
            0
        ].content_object.instance_type or get_last_known_instance_type(
            events[0].instance, events[0].occurred_at
        )
        cloud_type = events[0].cloud_type
        try:
            type_definition = InstanceDefinition.objects.get(
                instance_type=instance_type, cloud_type=cloud_type
            )
        except InstanceDefinition.DoesNotExist:
            type_definition = None
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
                run = DenormalizedRun(
                    start_time=start_run,
                    end_time=end_run,
                    image_id=image.id if image else None,
                    instance_id=instance_id,
                    instance_type=instance_type,
                    instance_memory=type_definition.memory_mib
                    if type_definition
                    else None,
                    instance_vcpu=type_definition.vcpu if type_definition else None,
                    is_cloud_access=image.is_cloud_access if image else False,
                    is_encrypted=image.is_encrypted if image else False,
                    is_marketplace=image.is_marketplace if image else False,
                    openshift=image.openshift if image else False,
                    openshift_detected=image.openshift_detected if image else False,
                    rhel=image.rhel if image else False,
                    rhel_detected=image.rhel_detected if image else False,
                )
                denormalized_runs.append(run)
                start_run = None
                end_run = None

        if start_run and not end_run:
            # When the instance was started but never stopped.
            run = DenormalizedRun(
                start_time=start_run,
                end_time=None,
                image_id=image.id if image else None,
                instance_id=instance_id,
                instance_type=instance_type,
                instance_memory=type_definition.memory_mib if type_definition else None,
                instance_vcpu=type_definition.vcpu if type_definition else None,
                is_cloud_access=image.is_cloud_access if image else False,
                is_encrypted=image.is_encrypted if image else False,
                is_marketplace=image.is_marketplace if image else False,
                openshift=image.openshift if image else False,
                openshift_detected=image.openshift_detected if image else False,
                rhel=image.rhel if image else False,
                rhel_detected=image.rhel_detected if image else False,
            )
            denormalized_runs.append(run)

    return denormalized_runs


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


def get_runs_for_user_id_on_date(user_id, date):
    """
    Get all of the Runs for the user ID that overlap with the given date.

    TODO Put this in a custom models.Manager for Run?

    Args:
        user_id (int): required filter on user
        date (datetime.date): the day during which we are measuring usage

    Returns:
        queryset
    """
    start_time = datetime(date.year, date.month, date.day, 0, 0, 0, tzinfo=tz.tzutc())
    end_time = start_time + timedelta(days=1)

    # We want to filter to Runs that:
    # - started before (not inclusive) our end time
    # - ended at or after our start time (inclusive) or have never stopped
    # - are for instances belonging to a cloud account for the given user
    time_filters = Q(start_time__lt=end_time) & (
        Q(end_time__isnull=True) | Q(end_time__gte=start_time)
    )
    user_filter = Q(instance__cloud_account__user__id=user_id)
    filters = user_filter & time_filters
    queryset = Run.objects.filter(filters)
    return queryset


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

    logger.info(
        _(
            "Starting calculate_max_concurrent_usage "
            "for user_id %(user_id)s and %(date)s"
        ),
        {"user_id": user_id, "date": date},
    )

    runs_queryset = get_runs_for_user_id_on_date(user_id, date)
    # This prefetch_related may generate a few large queries at first,
    # but that *should* result in better overall performance for large sets of runs.
    # Without it, each iteration step below generates 8 additional DB queries.
    # With it, each step generates only 1 additional DB queries.
    runs_queryset = runs_queryset.prefetch_related(
        "instance",
        "instance__cloud_account",
        "instance__content_object",
        "machineimage",
        "machineimage__content_object",
    )
    runs = runs_queryset.all()
    runs_count = runs.count()

    # Now that we have the Runs, we need to extract the start and stop times
    # from each Run, put them in a list, and order them chronologically. If we
    # ever want to know about concurrency for things other than RHEL, we would
    # repeat the following pattern for each other filter/condition.
    rhel_on_offs = []
    logger.info(
        _("Iterating through %(runs_count)s runs for user_id %(user_id)s and %(date)s"),
        {"user_id": user_id, "runs_count": runs_count, "date": date},
    )
    for number, run in enumerate(runs):
        if number % 100 == 0:
            # This is temporary to diagnose possible issues with large data sets.
            logger.info(
                _(
                    "ConcurrentUsage processed %(number)s/%(runs_count)s of runs "
                    "for user_id %(user_id)s and %(date)s"
                ),
                {
                    "number": number,
                    "runs_count": runs_count,
                    "user_id": user_id,
                    "date": date,
                },
            )
        if not run.machineimage or not run.machineimage.rhel:
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
                run.machineimage.rhel_version,
                run.machineimage.syspurpose,
                run.machineimage.architecture,
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
                    run.machineimage.rhel_version,
                    run.machineimage.syspurpose,
                    run.machineimage.architecture,
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
                "usage": key.usage,
                "service_type": key.service_type,
                "instances_count": value["max_count"],
            }
        )

    logger.info(
        _("Saving calculated ConcurrentUsage for user_id %(user_id)s and %(date)s"),
        {"user_id": user_id, "date": date},
    )
    ConcurrentUsage.objects.filter(date=date, user_id=user_id).delete()
    concurrent_usage = ConcurrentUsage.objects.create(
        date=date, user_id=user_id, maximum_counts=simplified_maximum_counts
    )
    concurrent_usage.potentially_related_runs.add(*runs)
    concurrent_usage.save()

    logger.info(
        _(
            "Finished calculate_max_concurrent_usage"
            " for user_id %(user_id)s and %(date)s"
        ),
        {"user_id": user_id, "date": date},
    )
    return concurrent_usage


def _record_results(results, is_start, syspurpose=None, arch=None):
    """
    Process data from the runs and tally up concurrent counts.

    Role and Arch independently map to different products within SWatch.
    This function should generate the combination of all other relevant syspurpose
    fields (sla, usage, etc.) and count the number of occurrences with
    respect to Role and Arch.

    Args:
        results (dict): The results dict that'll be populated with counts.
        is_start (bool): Is this a start event?
        syspurpose (dict): Optional. Dict representing the sypurpose.
        arch (str): Optional. Architecture of the image.

    Returns:
        Dict: The updated results dictionary.

    """
    arch = arch if arch is not None else ""
    role = syspurpose.get("role", "")[:64] if syspurpose is not None else ""

    sla = (
        syspurpose.get("service_level_agreement", "")[:64]
        if syspurpose is not None
        else ""
    )
    usage = syspurpose.get("usage", "")[:64] if syspurpose is not None else ""
    service_type = (
        syspurpose.get("service_type", "")[:64] if syspurpose is not None else ""
    )

    # This is a combination of the product categories we want.
    # Note that we don't care about the category (role, arch)
    product_categories = [(ANY, ANY), (ANY, arch), (role, ANY)]

    # Create the possible sla, usage, service_type categories this records belongs to.
    slas = [ANY, sla]
    usages = [ANY, usage]
    service_types = [ANY, service_type]

    # This generates all possible combinations of sla, usage, and
    # service_type in the form (sla, usage, service_type)
    # For example if sla, usage, and service_type are all known,
    # the filterable categories would be:
    #
    # (SLA=ANY, usage=ANY, service_type=ANY)
    # (SLA=ANY, usage=ANY, service_type=my_service_type)
    # (SLA=ANY, usage=my_usage, service_type=ANY)
    # (SLA=ANY, usage=my_usage, service_type=my_service_type)
    # (SLA=my_sla, usage=ANY, service_type=ANY)
    # (SLA=my_sla, usage=ANY, service_type=my_service_type)
    # (SLA=my_sla, usage=my_usage, service_type=ANY)
    # (SLA=my_sla, usage=my_usage, service_type=my_service_type)
    syspurpose_categories = list(itertools.product(slas, usages, service_types))

    for product in product_categories:
        for syspurpose_category in syspurpose_categories:
            key = ConcurrentKey(
                role=product[0],
                sla=syspurpose_category[0],
                arch=product[1],
                usage=syspurpose_category[1],
                service_type=syspurpose_category[2],
            )
            results = _record_concurrency_count(results, key, is_start)

    return results


def _record_concurrency_count(results, key, is_start):
    """Record the count."""
    entry = results.setdefault(
        key,
        {
            "current_count": 0,
            "max_count": 0,
        },
    )
    entry["current_count"] += 1 if is_start else -1
    entry["max_count"] = max(entry["current_count"], entry["max_count"])

    return results


def get_users_dates_from_runs(runs):
    """
    Build a list of user IDs and dates affected by the given list of Runs.

    Args:
        runs: list(models.Run)

    Returns:
        set(tuple[datetime.date, int])

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

    return date_user_cloud_accounts


def calculate_max_concurrent_usage_from_runs(runs):
    """
    Calculate maximum concurrent usage of RHEL instances from given Runs.

    We try to find the common intersection of the given runs across the dates,
    users, and cloud accounts referenced in the given Runs.

    Beware that this function may have an expensive run time. Use it sparingly.
    """
    date_user_cloud_accounts = get_users_dates_from_runs(runs)
    concurrent_usages = []
    for date, user_id in date_user_cloud_accounts:
        concurrent_usages.append(calculate_max_concurrent_usage(date, user_id))
    return concurrent_usages


def _runs_match_denormalized_runs(runs, denormalized_runs):
    """
    Compare list of Run objects to list of calculated DenormalizedRun objects.

    Note:
        This comparison function assumes the input lists are already sorted.

    Returns:
        bool: True if they are effectively equal. False if they are not.
    """
    if len(denormalized_runs) != len(runs):
        return False
    for run, denormalized_run in zip(runs, denormalized_runs):
        if (
            run.start_time != denormalized_run.start_time
            or run.end_time != denormalized_run.end_time
            or run.machineimage_id != denormalized_run.image_id
            or run.instance_id != denormalized_run.instance_id
            or run.instance_type != denormalized_run.instance_type
            or run.memory != denormalized_run.instance_memory
            or run.vcpu != denormalized_run.instance_vcpu
        ):
            return False
    return True


@transaction.atomic()
def recalculate_runs(event):
    """
    Take in an event and (re)calculate runs based on it.

    The simplest use case here is if the event is newer than any runs, and that
    means a new run may be created. The more complex use case is if the event
    occurred during or before existing runs, and that means any overlapping or
    future runs must be deleted and recreated.

    Returns:
        list(Run): the newly saved Runs
    """
    # Get all runs that occurred after or overlap with the event.
    after_run = Q(start_time__gt=event.occurred_at)
    during_run = Q(start_time__lte=event.occurred_at, end_time__gt=event.occurred_at)
    during_run_no_end = Q(start_time__lte=event.occurred_at, end_time=None)
    filters = after_run | during_run | during_run_no_end
    runs = Run.objects.filter(filters, instance_id=event.instance_id).order_by(
        "start_time"
    )

    # Determine the earliest time from which we should start recalculating runs.
    # We can use the earliest run as a baseline to fetch all relevant events.
    # If no runs exist, simply use the event's own occurred_at as the starting event.
    earliest_run = runs.first()
    earliest_time = earliest_run.start_time if earliest_run else event.occurred_at

    events = (
        # Note: If we ever start persisting data into the Run objects from events that
        # indicate instance type changes, we will need to include that event type here
        # or simply stop filtering on event type.
        InstanceEvent.objects.filter(
            instance_id=event.instance_id,
            occurred_at__gte=earliest_time,
            event_type__in=[InstanceEvent.TYPE.power_on, InstanceEvent.TYPE.power_off],
        )
        .select_related("instance")
        .order_by("occurred_at")
    )

    denormalized_runs = denormalize_runs(events)

    if _runs_match_denormalized_runs(runs.all(), denormalized_runs):
        # Compare the existing saved Runs with the newly calculated denormalized_runs.
        # If they are effectively the same, return early since we have nothing to do.
        return []

    runs.delete()
    saved_runs = []
    denormalized_runs_count = len(denormalized_runs)
    for index, denormalized_run in enumerate(denormalized_runs):
        logger.debug(
            "Processing run %(index)s of %(runs)s",
            {"index": index + 1, "runs": denormalized_runs_count},
        )
        run = Run(
            start_time=denormalized_run.start_time,
            end_time=denormalized_run.end_time,
            machineimage_id=denormalized_run.image_id,
            instance_id=denormalized_run.instance_id,
            instance_type=denormalized_run.instance_type,
            memory=denormalized_run.instance_memory,
            vcpu=denormalized_run.instance_vcpu,
        )
        run.save()
        saved_runs.append(run)

    return saved_runs


def recalculate_runs_for_instance_id(instance_id):
    """
    Ensure Run objects are up-to-date for the given instance id's recent events.

    If no Run exists, we just look for the oldest related InstanceEvent to process.
    If a Run does exist, find the most recent one, and look for the oldest related
    InstanceEvent that was recorded since that Run was created.
    """
    # Filter events to the given instance that are power-related.
    # Note: If we ever start persisting data into the Run objects from events that
    # indicate instance type changes, we will need to include that event type here or
    # simply stop filtering on event type.
    event_filters = Q(instance_id=instance_id) & Q(
        event_type__in=[InstanceEvent.TYPE.power_on, InstanceEvent.TYPE.power_off]
    )

    # If any Run exists, limit to InstanceEvents since the most recent Run was created.
    # Look for events created, updated, or occurred since then. This means if there are
    # any *past* runs that failed to calculate using some *older* events, they will not
    # be fixed here. This should be to safe use *going forward*. If we find past runs
    # that have missed past events, we may need to use some other process to recreate
    # the entire history of runs.
    if (
        latest_run := Run.objects.filter(instance_id=instance_id)
        .order_by("-created_at")
        .first()
    ):
        run_created_at = latest_run.created_at
        event_filters = event_filters & (
            Q(created_at__gte=run_created_at)
            | Q(updated_at__gte=run_created_at)
            | Q(occurred_at__gte=run_created_at)
        )
    recalculated_runs = []
    if oldest_relevant_event := (
        InstanceEvent.objects.filter(event_filters).order_by("created_at").first()
    ):
        recalculated_runs = recalculate_runs(oldest_relevant_event)
    if count := len(recalculated_runs):
        logger.debug(
            _("recalculated %(count)s runs for instance %(instance_id)s"),
            {"count": count, "instance_id": instance_id},
        )
    return recalculated_runs


def recalculate_runs_for_cloud_account_id(
    cloud_account_id, since=None, show_progress=False
):
    """
    Recalculate recent Runs for the given cloud account id.

    This searches for recently created, updated, or occurred events and finds the set
    of distinct instances referenced by those events. That list is a superset of
    instances that actually need recalculating; this simply gets all instances that have
    recent activity that *may* need recalculation. For each of those instances, we call
    recalculate_runs_for_instance_id which further determines if actual changes need to
    be made and then recalculates them accordingly.

    Args:
        cloud_account_id (int): CloudAccount id
        since (datetime.datetime): optional starting time to search for events
        show_progress (bool): optional show progress to stdout via tdqm

    """
    if not since:
        days_ago = settings.RECALCULATE_RUNS_SINCE_DAYS_AGO
        since = get_now() - timedelta(days=days_ago)
    logger.debug(
        _(
            "starting to recalculate runs "
            "for cloud account %(cloud_account_id)s since %(since)s"
        ),
        {"cloud_account_id": cloud_account_id, "since": since},
    )
    # Note: If we ever start persisting data into the Run objects from events that
    # indicate instance type changes, we will need to include that event type here
    # or simply stop filtering on event type.
    event_filters = (
        Q(instance__cloud_account_id=cloud_account_id)
        & Q(event_type__in=[InstanceEvent.TYPE.power_on, InstanceEvent.TYPE.power_off])
        & (
            Q(created_at__gte=since)
            | Q(updated_at__gte=since)
            | Q(occurred_at__gte=since)
        )
    )
    # Note: this query returns a list like [{'instance_id': 2288}, ...].
    relevant_instance_ids = (
        InstanceEvent.objects.filter(event_filters)
        .values("instance_id")
        .order_by("instance_id")
        .distinct()
    )
    instance_ids = (record["instance_id"] for record in relevant_instance_ids)
    instance_count = 0
    run_count = 0
    instance_ids = (
        tqdm(
            instance_ids,
            desc=f"Recalculating Runs for CloudAccount {cloud_account_id}'s Instances",
            total=len(relevant_instance_ids),
        )
        if show_progress
        else instance_ids
    )
    for instance_count, instance_id in enumerate(instance_ids):
        recalculated_runs = recalculate_runs_for_instance_id(instance_id)
        run_count += len(recalculated_runs)
    logger.debug(
        _(
            "recalculated %(run_count)s runs for %(instance_count)s instances "
            "for cloud account %(cloud_account_id)s"
        ),
        {
            "run_count": run_count,
            "instance_count": instance_count,
            "cloud_account_id": cloud_account_id,
        },
    )


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
        cloud_name=cloud_name,
        external_cloud_account_id=external_cloud_account_id,
    )


def find_problematic_runs(user_id=None):
    """
    Find any problematic Run objects that should have an end_time but don't.

    It's unclear how this can happen, but we have observed some cases where a Run was
    created, and a power_off InstanceEvent exists, but the Run's end_time was not set.

    Returns:
        list of Run objects that should have an end_time but don't
    """
    # Find all runs with no end date, optionally filtering on the user.
    user_filter = Q(instance__cloud_account__user__id=user_id) if user_id else Q()
    runs = Run.objects.filter(user_filter, end_time=None).order_by("id")

    # Find if any power_off event exists after each run's start.
    # Note: there's probably a more efficient way of doing this without O(N) queries.
    # In raw SQL, you could query the related events with an exists sub-select, but
    # I'm not sure how to coerce Django's ORM in that way here. Maybe try attaching an
    # annotation to the initial Run queryset that uses aggregation of InstanceEvent?
    problematic_runs = []
    for run in runs:
        if InstanceEvent.objects.filter(
            instance_id=run.instance_id,
            occurred_at__gte=run.start_time,
            event_type=InstanceEvent.TYPE.power_off,
        ).exists():
            problematic_runs.append(run)
    return problematic_runs


def save_instance_type_definitions(definitions, cloud_type):
    """
    Save instance type definitions to our database.

    Note:
        If an instance type name already exists in the DB, do NOT overwrite it.

    Args:
        definitions (dict): dict of dicts where the outer key is the instance
        type name and the inner dict has keys memory, vcpu and json_definition.
        For example: {'r5.large': {'memory': 24.0, 'vcpu': 1, 'json_definition': {...}}}

        cloud_type (str): str representing the source cloud of the definition.

    Returns:
        None

    """
    for name, attributes in definitions.items():
        try:
            obj, created = InstanceDefinition.objects.get_or_create(
                instance_type=name,
                cloud_type=cloud_type,
                defaults={
                    "memory_mib": attributes["memory"],
                    "vcpu": Decimal(attributes["vcpu"]),
                    "json_definition": attributes["json_definition"],
                },
            )
            if created:
                logger.info(_("Saving new instance type %s"), obj.instance_type)
            else:
                logger.info(_("Instance type %s already exists."), obj.instance_type)
        except IntegrityError as e:
            logger.exception(
                _(
                    "Failed to get_or_create an InstanceDefinition("
                    'name="%(name)s", memory_mib=%(memory_mib)s, vcpu=%(vcpu)s'
                    "); this should never happen."
                ),
                {
                    "name": name,
                    "memory_mib": attributes["memory"],
                    "vcpu": attributes["vcpu"],
                },
            )
            raise e
