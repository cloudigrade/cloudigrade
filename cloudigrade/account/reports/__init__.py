"""Cloud provider-agnostic report-building functionality."""
import collections
import datetime
import functools
import logging
import operator

from django.db import models
from django.utils.translation import gettext as _

from account import AWS_PROVIDER_STRING
from account.models import Account, AwsAccount, Instance, InstanceEvent

logger = logging.getLogger(__name__)


def get_daily_usage(user_id, start, end, name_pattern=None):
    """
    Calculate daily usage over the designated period.

    Args:
        user_id (int): user_id for filtering cloud accounts
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        name_pattern (str): pattern to filter against cloud account names

    Returns:
        dict: Data structure representing each day in the period and its
            constituent representative parts in terms of product usage.
    """

    if name_pattern is not None:
        names = set(
            [word for word in name_pattern.split(' ') if len(word) > 0]
        )
    else:
        names = None
    accounts = _filter_accounts(user_id, names)
    events = _get_relevant_events(start, end, accounts)

    instance_events = collections.defaultdict(list)
    for event in events:
        instance_events[event.instance].append(event)
    instance_events = dict(instance_events)

    usage = _calculate_daily_usage(start, end, instance_events)
    return usage


def _filter_accounts(user_id, names=None, account_ids=None):
    """
    Get accounts filtered by user_id and matching name.

    Args:
        user_id (int): required user_id to filter against
        names (list[str]): optional name patterns to filter against
        account_ids (list[int]): optional account ids to filter against

    Returns:
        PolymorphicQuerySet for the filtered Account objects.
    """
    account_filter = models.Q(
        user_id=user_id
    )

    if names:
        # Combine all the name matches with "ior" operators.
        account_name_filter = functools.reduce(
            operator.ior,
            [models.Q(name__icontains=name) for name in names]
        )
        account_filter &= account_name_filter

    if account_ids:
        account_ids_filter = models.Q(
            id__in=account_ids
        )
        account_filter &= account_ids_filter

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
    events = InstanceEvent.objects.filter(event_filter).select_related()\
        .order_by('instance__id')
    return events


def _calculate_daily_usage(start, end, instance_events):
    """
    Get all InstanceEvents relevant to the report parameters.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        instance_events (list[InstanceEvent]): events to use for calculations
    """
    periods = []
    for day_number in range((end - start).days):
        period_start = start + datetime.timedelta(days=day_number)
        period_end = period_start + datetime.timedelta(days=1)
        periods.append((period_start, period_end))

    image_ids_seen = set()
    image_ids_seen_with_rhel = set()
    image_ids_seen_with_openshift = set()
    instance_ids_seen_with_rhel = set()
    instance_ids_seen_with_openshift = set()

    daily_usage = []
    for period_start, period_end in periods:
        rhel_instance_count = 0
        openshift_instance_count = 0
        rhel_seconds = 0.0
        openshift_seconds = 0.0

        for instance, events in instance_events.items():
            runtime = _calculate_instance_usage(
                period_start,
                period_end,
                events,
            )

            if runtime == 0.0:
                # No runtime? No updates to counters.
                continue

            # Since all events for AWS have the same image, we can short-
            # circuit the logic here and look at only 1 event. We may need
            # to revisit this logic in the future if we add support for a
            # cloud provider that allows you to change the image on an
            # existing instance.
            image = events[0].machineimage
            if image.id not in image_ids_seen:
                image_ids_seen.add(image.id)
                if image.rhel:
                    image_ids_seen_with_rhel.add(image.id)
                if image.openshift:
                    image_ids_seen_with_openshift.add(image.id)
            if image.id in image_ids_seen_with_rhel:
                rhel_instance_count += 1
                instance_ids_seen_with_rhel.add(instance.id)
                rhel_seconds += runtime
            if image.id in image_ids_seen_with_openshift:
                openshift_instance_count += 1
                instance_ids_seen_with_openshift.add(instance.id)
                openshift_seconds += runtime

        daily_usage.append({
            'date': period_start,
            'rhel_instances': rhel_instance_count,
            'openshift_instances': openshift_instance_count,
            'rhel_runtime_seconds':rhel_seconds,
            'openshift_runtime_seconds': openshift_seconds,
        })

    return {
        'instances_seen_with_rhel': len(instance_ids_seen_with_rhel),
        'instances_seen_with_openshift': len(instance_ids_seen_with_openshift),
        'daily_usage': daily_usage,
    }


def _calculate_instance_usage(start, end, events):
    """
    Calculate instance usage based on events.

    Note:
        All given events should belong to the same instance.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        events (list[InstanceEvent]): Events for calculating usage

    Returns:
        float: The total seconds running.

    """
    last_started = None
    time_running = 0.0

    sorted_events = sorted(events, key=lambda e: e.occurred_at)

    before_start = [event for event in sorted_events
                    if event.occurred_at < start][-1:]
    after_start = [event for event in sorted_events
                   if event.occurred_at >= start and event.occurred_at < end]
    sorted_trimmed_events = before_start + after_start

    for event in sorted_trimmed_events:
        # whichever is later: the first event or the reported period start
        event_time = max(start, event.occurred_at)

        if not last_started and \
                event.event_type == InstanceEvent.TYPE.power_on:
            # hold the time only if new event is ON and was previously OFF
            last_started = event_time
        elif last_started and \
                event.event_type == InstanceEvent.TYPE.power_off:
            # add the time if new event is OFF and was previously ON
            diff = event_time - last_started
            time_running += diff.total_seconds()
            # drop the started time, implying that the instance is now OFF
            last_started = None

    if last_started:
        diff = end - last_started
        time_running += diff.total_seconds()

    return time_running

def validate_event(event, start):
    """
    Ensure that the event is relevant to our time frame.

    Args:
        event: (InstanceEvent): The event object to evaluate
        start (datetime.datetime): Start time (inclusive)

    Returns:
        bool: A boolean regarding whether or not we should inspect the event further.
    """
    valid_event = True
    # if the event occurred outside of our specified period (ie. before start) we should
    # only inspect it if it was a power on event
    if event.occurred_at < start:
        if event.event_type == InstanceEvent.TYPE.power_off:
            valid_event = False
    return valid_event

def get_account_overview(account, start, end):
    """
    Generate an overview of an account over a specified amount of time.

    Args:
        account (AwsAccount): AwsAccount object
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)

    Returns:
        dict: An overview of the instances/images/rhel & openshift images for the specified
        account during the specified time period."""
    instances = []
    images = []
    rhel = []
    openshift = []
    # if the account was created right at or after the end time, we cannot give meaningful
    # data about the instances/images seen during the period, therefore we need to make sure
    # that we return None for those values
    if end <= account.created_at:
        logger.info(_('Account "{0}" was created after "{1}", therefore there is no data on '
                      'its images/instances during the specified start and end dates.').format(
            account,
            end))
        total_images, total_instances, total_rhel, total_openshift = None, None, None, None
    else:
        # _get_relevant_events will return the events in between the start & end times & if
        # no events are present during this period, it will return the last event that occurred
        events = _get_relevant_events(start, end, [account.id])
        for event in events:
            valid_event = validate_event(event, start)
            if valid_event:
                instances.append(event.instance.id)
                images.append(event.machineimage.id)
                for tag in event.machineimage.tags.all():
                    if tag.description == 'rhel':
                        rhel.append(event.machineimage.id)
                    if tag.description == 'openshift':
                        openshift.append(event.machineimage.id)
        # grab the totals
        total_images = len(set(images))
        total_instances = len(set(instances))
        total_rhel = len(set(rhel))
        total_openshift = len(set(openshift))

    cloud_account = {'id': account.aws_account_id,
                     'user_id': account.user_id,
                     'type': AWS_PROVIDER_STRING,
                     'arn': account.account_arn,
                     'creation_date': account.created_at,
                     'name': account.name,
                     'images': total_images,
                     'instances': total_instances,
                     'rhel_instances': total_rhel,
                     'openshift_instances': total_openshift}

    return cloud_account
