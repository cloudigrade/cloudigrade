"""Cloud provider-agnostic report-building functionality."""
import collections
import datetime
import functools
import itertools
import logging
import operator

from django.db import models
from django.utils.translation import gettext as _

from account.models import (Account, AwsEC2InstanceDefinitions,
                            AwsInstanceEvent, Instance, InstanceEvent,
                            MachineImage)
from util.exceptions import NormalizeRunException

logger = logging.getLogger(__name__)


def get_daily_usage(user_id, start, end, name_pattern=None, account_id=None):
    """
    Calculate daily usage over the designated period.

    Args:
        user_id (int): user_id for filtering cloud accounts
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        name_pattern (str): pattern to filter against cloud account names
        account_id (int): account_id for filtering cloud accounts

    Returns:
        dict: Data structure representing each day in the period and its
            constituent representative parts in terms of product usage.

    """
    accounts = _filter_accounts(user_id, name_pattern, account_id)
    events = _get_relevant_events(start, end, accounts)
    usage = _calculate_daily_usage(start, end, events)
    return usage


def _filter_accounts(user_id, name_pattern=None, account_id=None):
    """
    Get accounts filtered by user_id and matching name.

    Args:
        user_id (int): required user_id to filter against
        name_pattern (str): optional cloud name pattern to filter against
        account_id (int): optional account_id to filter against

    Returns:
        PolymorphicQuerySet for the filtered Account objects.

    """
    account_filter = models.Q(user_id=user_id)

    if account_id:
        account_filter &= models.Q(id=account_id)

    if name_pattern is not None and len(name_pattern.strip()):
        # Build a set of unique words to use in the query.
        words = set(
            [word.lower() for word in name_pattern.split(' ') if len(word) > 0]
        )

        # Combine each the words with "ior" operators.
        account_name_filter = functools.reduce(
            operator.ior,
            [models.Q(name__icontains=word) for word in words]
        )
        account_filter &= account_name_filter

    accounts = Account.objects.filter(account_filter)
    return accounts


def _get_relevant_events(start, end, account_ids):
    """
    Get all InstanceEvents relevant to the report parameters.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        account_ids (list[int]): the relevant account ids

    Returns:
        list(InstanceEvent): All events relevant to the report parameters.

    """
    # Get the nearest event before the reporting period for each instance.
    account_filter = models.Q(account__id__in=account_ids)
    instances_before = Instance.objects.filter(
        account_filter & models.Q(instanceevent__occurred_at__lt=start)
    ).annotate(occurred_at=models.Max('instanceevent__occurred_at'))

    # Build a filter list for the events found before the period.
    event_filters = [
        models.Q(instance__id=i.id, occurred_at=i.occurred_at)
        for i in list(instances_before)
    ]

    # Add a filter for the events *during* the reporting period.
    event_filters.append(
        models.Q(instance__account__id__in=account_ids) &
        models.Q(occurred_at__gte=start, occurred_at__lt=end)
    )

    # Reduce all the filters with the "or" operator.
    event_filter = functools.reduce(operator.ior, event_filters)
    events = InstanceEvent.objects.filter(event_filter) \
        .select_related('instance') \
        .prefetch_related('machineimage') \
        .order_by('instance__id')
    return events


def _generate_daily_periods(start, end):
    """
    Generate a list of whole-day "reporting periods" spanning start and end.

    This is a little tricky because of time zones and the start and end values
    being date-times not just dates. The resulting list must be inclusive of
    both the start and end times.

    Args:
        start (datetime.datetime): Start time
        end (datetime.datetime): End time

    Returns:
        list(tuple): Each tuple has a start and end datetime, of which the
            start should be interpreted as inclusive and the end as exclusive.

    """
    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = end.replace(hour=0, minute=0, second=0, microsecond=0)
    number_of_days = (day_end - day_start).days
    if day_start + datetime.timedelta(days=number_of_days) < end:
        number_of_days += 1

    periods = []
    for day_number in range(number_of_days):
        period_start = start + datetime.timedelta(days=day_number)
        period_end = period_start + datetime.timedelta(days=1)
        periods.append((period_start, min(period_end, end)))
    return periods


def get_last_known_instance_type(instance, before_date):
    """
    Get the last known type for the given instance.

    Args:
        instance (Instance): instance to check
        before_date (datetime.datetime): cutoff for checking events for type

    Returns:
        str: The last known instance type or None if no type is found.

    """
    event = (
        AwsInstanceEvent.objects.filter(
            instance=instance,
            occurred_at__lte=before_date,
            instance_type__isnull=False,
        )
        .order_by('-occurred_at')
        .first()
    )
    if event is None:
        logger.error(
            _(
                'could not find any type for {instance} by {before_date}'
            ).format(instance=instance, before_date=before_date)
        )
        return None
    return event.instance_type


NormalizedRun = collections.namedtuple(
    'NormalizedRun',
    [
        'start_time',
        'end_time',
        'image_id',
        'instance_id',
        'instance_memory',
        'instance_type',
        'instance_vcpu',
        'is_cloud_access',
        'is_encrypted',
        'is_marketplace',
        'openshift',
        'openshift_challenged',
        'openshift_detected',
        'rhel',
        'rhel_challenged',
        'rhel_detected',
    ],
)


def get_instance_type_definition(instance_type):
    """Gracefully get the definition for the instance type."""
    try:
        type_definition = (
            AwsEC2InstanceDefinitions.objects.get(instance_type=instance_type)
            if instance_type
            else None
        )
    except AwsEC2InstanceDefinitions.DoesNotExist:
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
        sorted(events, key=lambda e: f'{e.instance_id}_{e.occurred_at}'),
        key=lambda e: e.instance_id,
    )

    normalized_runs = []
    for instance_id, events in sorted_events_by_instance:
        events = list(events)  # events is not subscriptable from the groupby.
        instance_type = events[
            0
        ].instance_type or get_last_known_instance_type(
            events[0].instance, events[0].occurred_at
        )
        type_definition = get_instance_type_definition(instance_type)
        start_run = None
        end_run = None
        image = Instance.objects.get(id=instance_id).machineimage

        for event in events:
            if event.instance_type and event.instance_type != instance_type:
                if start_run:
                    message = _(
                        'instance {instance_id} changed type from {old_type} '
                        'to {new_type} while is was running; this should not '
                        'be possible! (event {event})'
                    ).format(
                        instance_id=instance_id,
                        old_type=instance_type,
                        new_type=event.instance_type,
                        event=event,
                    )
                    raise NormalizeRunException(message)
                instance_type = event.instance_type

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
                    _(
                        'Instance {instance_id} does not have an associated '
                        'machine image.'
                    ).format(instance_id=instance_id)
                )

            if start_run and end_run:
                # The instance completed a start-stop cycle.
                run = NormalizedRun(
                    start_time=start_run,
                    end_time=end_run,
                    image_id=image.id if image else None,
                    instance_id=instance_id,
                    instance_type=instance_type,
                    instance_memory=type_definition.memory
                    if type_definition
                    else None,
                    instance_vcpu=type_definition.vcpu
                    if type_definition
                    else None,
                    is_cloud_access=image.is_cloud_access if image else False,
                    is_encrypted=image.is_encrypted if image else False,
                    is_marketplace=image.is_marketplace if image else False,
                    openshift=image.openshift if image else False,
                    openshift_challenged=image.openshift_challenged
                    if image
                    else False,
                    openshift_detected=image.openshift_detected
                    if image
                    else False,
                    rhel=image.rhel if image else False,
                    rhel_challenged=image.rhel_challenged if image else False,
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
                instance_memory=type_definition.memory
                if type_definition
                else None,
                instance_vcpu=type_definition.vcpu
                if type_definition
                else None,
                is_cloud_access=image.is_cloud_access if image else False,
                is_encrypted=image.is_encrypted if image else False,
                is_marketplace=image.is_marketplace if image else False,
                openshift=image.openshift if image else False,
                openshift_challenged=image.openshift_challenged
                if image
                else False,
                openshift_detected=image.openshift_detected
                if image
                else False,
                rhel=image.rhel if image else False,
                rhel_challenged=image.rhel_challenged if image else False,
                rhel_detected=image.rhel_detected if image else False,
            )
            normalized_runs.append(run)

    return normalized_runs


def calculate_runs_in_periods(periods, events):
    """
    Calculate image usage runs for each period.

    Args:
        periods (list[tuple[datetime, datetime]]): periods of time for which
            usage activity should be counted
        events (list[InstanceEvent]): list of relevant events to use for
            determining what instances and images were used across the periods

    Returns:
        list(dict).

    """
    normalized_runs = normalize_runs(events)

    # Next, walk through the periods and runs to further split the runs into
    # the periods. This process will break a run into multiple run along period
    # boundaries as necessary.
    periodic_runs = collections.defaultdict(list)
    # Since periods and normalized_runs are both already sorted, this *could*
    # be optimized from O(n**2) to O(n) by cleverly iterating them together...
    for period_start, period_end in periods:
        for run in normalized_runs:
            # There are four cases when we want to keep a run:
            # 1. whole run is within the period
            # 2. run started before the period and ended during it
            # 3. run started during the period and ended after it (or never)
            # 4. run started before the period and ended after it (or never)

            if (
                period_start <= run.start_time < period_end and
                run.end_time is not None and
                period_start < run.end_time <= period_end
            ):
                # Use case #1:
                # If the whole run fits inside the period, simply include it.
                logger.debug(
                    'case 1 match: period %(period_start)s to %(period_end)s '
                    'overlap with run %(run_start_time)s to %(run_end_time)s '
                    '(%(run)s)',
                    {
                        'period_start': period_start,
                        'period_end': period_end,
                        'run_start_time': run.start_time,
                        'run_end_time': run.end_time,
                        'run': run,
                    },
                )
                periodic_runs[period_start, period_end].append(run)
            elif (
                run.start_time < period_start and
                run.end_time is not None and
                period_start < run.end_time <= period_end
            ):
                # Use case #2:
                # If the run started before the period and ended during the
                # period, we set the start_time to the period_start.
                logger.debug(
                    'case 2 match: period %(period_start)s to %(period_end)s '
                    'overlap with run %(run_start_time)s to %(run_end_time)s '
                    '(%(run)s)',
                    {
                        'period_start': period_start,
                        'period_end': period_end,
                        'run_start_time': run.start_time,
                        'run_end_time': run.end_time,
                        'run': run,
                    },
                )
                periodic_runs[period_start, period_end].append(
                    NormalizedRun(
                        start_time=period_start,
                        end_time=run.end_time,
                        image_id=run.image_id,
                        instance_id=run.instance_id,
                        instance_memory=run.instance_memory,
                        instance_type=run.instance_type,
                        instance_vcpu=run.instance_vcpu,
                        is_cloud_access=run.is_cloud_access,
                        is_encrypted=run.is_encrypted,
                        is_marketplace=run.is_marketplace,
                        rhel=run.rhel,
                        rhel_challenged=run.rhel_challenged,
                        rhel_detected=run.rhel_detected,
                        openshift=run.openshift,
                        openshift_challenged=run.openshift_challenged,
                        openshift_detected=run.openshift_detected,
                    )
                )
            elif period_start <= run.start_time < period_end and (
                run.end_time is None or period_end < run.end_time
            ):
                # Use case #3:
                # If the run started during period and ended after the period
                # or never ended, we set the end_time to the period_end.
                logger.debug(
                    'case 3 match: period %(period_start)s to %(period_end)s '
                    'overlap with run %(run_start_time)s to %(run_end_time)s '
                    '(%(run)s)',
                    {
                        'period_start': period_start,
                        'period_end': period_end,
                        'run_start_time': run.start_time,
                        'run_end_time': run.end_time,
                        'run': run,
                    },
                )
                periodic_runs[period_start, period_end].append(
                    NormalizedRun(
                        start_time=run.start_time,
                        end_time=period_end,
                        image_id=run.image_id,
                        instance_id=run.instance_id,
                        instance_memory=run.instance_memory,
                        instance_type=run.instance_type,
                        instance_vcpu=run.instance_vcpu,
                        is_cloud_access=run.is_cloud_access,
                        is_encrypted=run.is_encrypted,
                        is_marketplace=run.is_marketplace,
                        rhel=run.rhel,
                        rhel_challenged=run.rhel_challenged,
                        rhel_detected=run.rhel_detected,
                        openshift=run.openshift,
                        openshift_challenged=run.openshift_challenged,
                        openshift_detected=run.openshift_detected,
                    )
                )
            elif run.start_time < period_start and (
                run.end_time is None or period_end < run.end_time
            ):
                # Use case #4:
                # If the run started before the period and ended after the
                # period or never ended, we set the start_time to period_start
                # and the end_time to period_end.
                logger.debug(
                    'case 4 match: period %(period_start)s to %(period_end)s '
                    'overlap with run %(run_start_time)s to %(run_end_time)s '
                    '(%(run)s)',
                    {
                        'period_start': period_start,
                        'period_end': period_end,
                        'run_start_time': run.start_time,
                        'run_end_time': run.end_time,
                        'run': run,
                    },
                )
                periodic_runs[period_start, period_end].append(
                    NormalizedRun(
                        start_time=period_start,
                        end_time=period_end,
                        image_id=run.image_id,
                        instance_id=run.instance_id,
                        instance_memory=run.instance_memory,
                        instance_type=run.instance_type,
                        instance_vcpu=run.instance_vcpu,
                        is_cloud_access=run.is_cloud_access,
                        is_encrypted=run.is_encrypted,
                        is_marketplace=run.is_marketplace,
                        rhel=run.rhel,
                        rhel_challenged=run.rhel_challenged,
                        rhel_detected=run.rhel_detected,
                        openshift=run.openshift,
                        openshift_challenged=run.openshift_challenged,
                        openshift_detected=run.openshift_detected,
                    )
                )
            else:
                logger.debug(
                    'period %(period_start)s to %(period_end)s does not '
                    'overlap with run %(run_start_time)s to %(run_end_time)s '
                    '(%(run)s)',
                    {
                        'period_start': period_start,
                        'period_end': period_end,
                        'run_start_time': run.start_time,
                        'run_end_time': run.end_time,
                        'run': run,
                    },
                )

    return periodic_runs


def _calculate_daily_usage(start, end, events, extended=False):
    """
    Calculate the daily usage of RHEL and OCP for the given parameters.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        events (list[InstanceEvent]): events to use for calculations
        extended (bool): should include extended output

    Returns:
        dict: Structure with some overall totals and list of daily totals.

    """
    all_instance_ids = set()
    rhel_instance_ids = set()
    openshift_instance_ids = set()
    rhel_challenged_instance_ids = set()
    openshift_challenged_instance_ids = set()

    all_image_ids = set()
    rhel_image_ids = set()
    openshift_image_ids = set()
    rhel_challenged_image_ids = set()
    openshift_challenged_image_ids = set()

    periods = _generate_daily_periods(start, end)
    periodic_runs = calculate_runs_in_periods(periods, events)

    period_usages = []
    for period in periods:
        # Instances
        period_all_instance_ids = set()
        period_rhel_instance_ids = set()
        period_openshift_instance_ids = set()
        period_rhel_challenged_instance_ids = set()
        period_openshift_challenged_instance_ids = set()

        # Images
        period_all_image_ids = set()
        period_rhel_image_ids = set()
        period_openshift_image_ids = set()
        period_rhel_challenged_image_ids = set()
        period_openshift_challenged_image_ids = set()

        # Instance runtime seconds
        period_all_seconds = 0.0
        period_rhel_seconds = 0.0
        period_openshift_seconds = 0.0

        # Instance seconds * memory in GBs
        period_all_memory_seconds = 0.0
        period_rhel_memory_seconds = 0.0
        period_openshift_memory_seconds = 0.0

        # Instance seconds * vcpu count
        period_all_vcpu_seconds = 0.0
        period_rhel_vcpu_seconds = 0.0
        period_openshift_vcpu_seconds = 0.0

        for run in periodic_runs[period]:
            if run.image_id:
                period_all_image_ids.add(run.image_id)

            period_all_instance_ids.add(run.instance_id)

            seconds = (run.end_time - run.start_time).total_seconds()
            memory_seconds = (
                seconds * run.instance_memory if run.instance_memory else 0.0
            )
            vcpu_seconds = (
                seconds * run.instance_vcpu if run.instance_vcpu else 0.0
            )

            period_all_seconds += seconds
            period_all_memory_seconds += memory_seconds
            period_all_vcpu_seconds += vcpu_seconds

            if run.rhel:
                period_rhel_instance_ids.add(run.instance_id)
                period_rhel_image_ids.add(run.image_id)
                period_rhel_seconds += seconds
                period_rhel_memory_seconds += memory_seconds
                period_rhel_vcpu_seconds += vcpu_seconds

            if run.openshift:
                period_openshift_instance_ids.add(run.instance_id)
                period_openshift_image_ids.add(run.image_id)
                period_openshift_seconds += seconds
                period_openshift_memory_seconds += memory_seconds
                period_openshift_vcpu_seconds += vcpu_seconds

            if run.rhel_challenged:
                period_rhel_challenged_image_ids.add(run.image_id)
                period_rhel_challenged_instance_ids.add(run.instance_id)

            if run.openshift_challenged:
                period_openshift_challenged_image_ids.add(run.image_id)
                period_openshift_challenged_instance_ids.add(run.instance_id)

        period_start, __ = period
        period_usage = {
            'date': period_start,
            'rhel_instances': len(period_rhel_instance_ids),
            'openshift_instances': len(period_openshift_instance_ids),
            'rhel_images': len(period_rhel_image_ids),
            'openshift_images': len(period_openshift_image_ids),
            'rhel_runtime_seconds': period_rhel_seconds,
            'openshift_runtime_seconds': period_openshift_seconds,
            'rhel_vcpu_seconds': period_rhel_vcpu_seconds,
            'openshift_vcpu_seconds': period_openshift_vcpu_seconds,
            'rhel_memory_seconds': period_rhel_memory_seconds,
            'openshift_memory_seconds': period_openshift_memory_seconds,
        }
        if extended:
            period_usage.update(
                {
                    'all_instances': len(period_all_instance_ids),
                    'all_images': len(period_all_image_ids),
                    'all_runtime_seconds': period_all_seconds,
                }
            )
        period_usages.append(period_usage)

        all_instance_ids |= period_all_instance_ids
        rhel_instance_ids |= period_rhel_instance_ids
        openshift_instance_ids |= period_openshift_instance_ids
        rhel_challenged_instance_ids |= period_rhel_challenged_instance_ids
        openshift_challenged_instance_ids |= (
            period_openshift_challenged_instance_ids
        )
        all_image_ids |= period_all_image_ids
        rhel_image_ids |= period_rhel_image_ids
        openshift_image_ids |= period_openshift_image_ids
        rhel_challenged_image_ids |= period_rhel_challenged_image_ids
        openshift_challenged_image_ids |= period_openshift_challenged_image_ids

    overall_usage = {
        'instances_seen_with_rhel': len(rhel_instance_ids),
        'instances_seen_with_openshift': len(openshift_instance_ids),
        'instances_seen_with_rhel_challenged': len(
            rhel_challenged_instance_ids
        ),
        'instances_seen_with_openshift_challenged': len(
            openshift_challenged_instance_ids
        ),
        'daily_usage': period_usages,
    }
    if extended:
        overall_usage.update(
            {
                'instances_seen': len(all_instance_ids),
                'images_seen': len(all_image_ids),
                'images_seen_with_rhel': len(rhel_image_ids),
                'images_seen_with_openshift': len(openshift_image_ids),
                'images_seen_with_rhel_challenged': len(
                    rhel_challenged_image_ids
                ),
                'images_seen_with_openshift_challenged': len(
                    openshift_challenged_image_ids
                ),
            }
        )
    return overall_usage


def validate_event(event, start):
    """
    Ensure that the event is relevant to our time frame.

    Args:
        event: (InstanceEvent): The event object to evaluate
        start (datetime.datetime): Start time (inclusive)

    Returns:
        bool: A boolean regarding whether or not we should inspect the event
            further.

    """
    valid_event = True
    # if the event occurred outside of our specified period (ie. before start)
    # we should only inspect it if it was a power on event
    if event.occurred_at < start:
        if event.event_type == InstanceEvent.TYPE.power_off:
            valid_event = False
    return valid_event


def get_account_overviews(user_id, start, end, name_pattern=None,
                          account_id=None):
    """
    Generate overviews for accounts belonging to user_id in a specified time.

    This is effectively a simple wrapper to iterate `get_account_overview` for
    all of the matching accounts under the target user.

    Args:
        user_id (int): user_id for filtering cloud accounts
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        name_pattern (str): pattern to filter against cloud account names
        account_id (int): account_id for filtering cloud accounts

    Returns:

    """
    accounts = _filter_accounts(user_id, name_pattern=name_pattern,
                                account_id=account_id)
    overviews = [
        get_account_overview(account, start, end)
        for account in accounts
    ]
    return {'cloud_account_overviews': overviews}


def get_account_overview(account, start, end):
    """
    Generate an overview of an account over a specified amount of time.

    Args:
        account (Account): Account object
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)

    Returns:
        dict: An overview of the instances/images/rhel & openshift images for
            the specified account during the specified time period.

    """
    # If the start time is in the future, we cannot give any meaningful data
    if start > datetime.datetime.now(datetime.timezone.utc):
        logger.info(_(
            'Start time {0} is after the current time, therefore '
            'there is no meaningful data we can provide.'
        ).format(start))

        total_images = None
        total_challenged_images_rhel = None
        total_challenged_images_openshift = None
        total_instances = None
        total_instances_rhel = None
        total_instances_openshift = None
        total_runtime_rhel = None
        total_runtime_openshift = None
        total_memory_rhel = None
        total_memory_openshift = None
        total_vcpu_rhel = None
        total_vcpu_openshift = None

    # if the account was created right at or after the end time, we cannot give
    # meaningful data about the instances/images seen during the period,
    # therefore we need to make sure that we return None for those values
    elif end <= account.created_at:
        logger.info(_(
            'Account "{0}" was created after "{1}", therefore there is no '
            'data on its images/instances during the specified start and end '
            ' dates.'
        ).format(account, end))
        total_images = None
        total_challenged_images_rhel = None
        total_challenged_images_openshift = None
        total_instances = None
        total_instances_rhel = None
        total_instances_openshift = None
        total_runtime_rhel = None
        total_runtime_openshift = None
        total_memory_rhel = None
        total_memory_openshift = None
        total_vcpu_rhel = None
        total_vcpu_openshift = None
    else:
        events = _get_relevant_events(start, end, [account.id])
        usage = _calculate_daily_usage(start, end, events, extended=True)

        total_images = usage['images_seen']
        total_challenged_images_rhel = usage[
            'instances_seen_with_rhel_challenged'
        ]
        total_challenged_images_openshift = usage[
            'instances_seen_with_openshift_challenged'
        ]
        total_instances = usage['instances_seen']
        total_instances_rhel = usage['instances_seen_with_rhel']
        total_instances_openshift = usage['instances_seen_with_openshift']

        total_runtime_rhel = 0
        total_runtime_openshift = 0
        total_memory_rhel = 0
        total_memory_openshift = 0
        total_vcpu_rhel = 0
        total_vcpu_openshift = 0

        for day in usage['daily_usage']:
            total_runtime_rhel += day['rhel_runtime_seconds']
            total_runtime_openshift += day['openshift_runtime_seconds']
            total_memory_rhel += day['rhel_memory_seconds']
            total_memory_openshift += day['openshift_memory_seconds']
            total_vcpu_rhel += day['rhel_vcpu_seconds']
            total_vcpu_openshift += day['openshift_vcpu_seconds']

    cloud_account = {
        'id': account.id,
        'cloud_account_id': account.cloud_account_id,
        'user_id': account.user_id,
        'type': account.cloud_type,
        'arn': account.account_arn,
        'creation_date': account.created_at,
        'name': account.name,
        'images': total_images,
        'instances': total_instances,
        'rhel_instances': total_instances_rhel,
        'openshift_instances': total_instances_openshift,
        'rhel_runtime_seconds': total_runtime_rhel,
        'openshift_runtime_seconds': total_runtime_openshift,
        'rhel_images_challenged': total_challenged_images_rhel,
        'openshift_images_challenged': total_challenged_images_openshift,
        'rhel_memory_seconds': total_memory_rhel,
        'openshift_memory_seconds': total_memory_openshift,
        'rhel_vcpu_seconds': total_vcpu_rhel,
        'openshift_vcpu_seconds': total_vcpu_openshift,
    }

    return cloud_account


class ImageActivityData(object):
    """Helper data structure for counting image activity."""

    _machine_image_iterable_keys = (
        'id',
        'cloud_image_id',
        'name',
        'status',
        'is_cloud_access',
        'is_encrypted',
        'is_marketplace',
        'rhel',
        'rhel_detected',
        'rhel_challenged',
        'openshift',
        'openshift_detected',
        'openshift_challenged',
    )
    _self_iterable_keys = (
        'instances_seen',
        'runtime_seconds',
        'memory_seconds',
        'vcpu_seconds',
    )

    def __init__(self):
        """Initialize an empty instance."""
        self.machine_image = None
        self.instance_ids = set()
        self.runtime_seconds = 0.0
        self.memory_seconds = 0.0
        self.vcpu_seconds = 0.0

    def __iter__(self):
        """Generate iterable to convert self to a dict."""
        for key in self._machine_image_iterable_keys:
            yield key, getattr(self.machine_image, key)
        for key in self._self_iterable_keys:
            yield key, getattr(self, key)

    @property
    def instances_seen(self):
        """Get number of instances seen."""
        return len(self.instance_ids)


def get_image_usages_for_account(start, end, account_id):
    """
    Calculate usage data for images in a specified time in the account.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        account_id (int): account_id for filtering image activity

    Returns:
        dict: ImageActivityData objects keyed by machine image ID.

    """
    events = _get_relevant_events(start, end, [account_id])
    period = start, end
    periods = [period]
    runs = calculate_runs_in_periods(periods, events)

    images = collections.defaultdict(ImageActivityData)
    for run in runs[period]:
        if run.image_id is None:
            continue
        seconds = (run.end_time - run.start_time).total_seconds()
        vcpu_seconds = (
            seconds * run.instance_vcpu if run.instance_vcpu else 0.0
        )
        memory_seconds = (
            seconds * run.instance_memory if run.instance_memory else 0.0
        )
        if images[run.image_id].machine_image is None:
            images[run.image_id].machine_image = MachineImage.objects.get(
                id=run.image_id
            )
        images[run.image_id].instance_ids.add(run.instance_id)
        images[run.image_id].runtime_seconds += seconds
        images[run.image_id].memory_seconds += memory_seconds
        images[run.image_id].vcpu_seconds += vcpu_seconds

    return dict(images)


def get_images_overviews(user_id, start, end, account_id):
    """
    Generate overviews for images belonging to account_id in a specified time.

    This is effectively a simple wrapper to call `get_image_usages_for_account`
    after verifying that the account_id is actually valid for the user_id.

    Args:
        user_id (int): user_id for filtering cloud accounts
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        account_id (int): account_id for filtering cloud accounts

    Returns:
        dict: Data structure representing each found image with the image's
            own metadata, the number of instances seen, and the cumulative
            elapsed time that instances were seen running.

    """
    images = {}
    if _filter_accounts(user_id, account_id=account_id):
        images = get_image_usages_for_account(start, end, account_id)
    return {'images': [dict(image) for image in images.values()]}
