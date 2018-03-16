"""Cloud provider-agnostic report-building functionality."""
import collections
import functools
import operator

from django.db import models

from account.models import Instance, InstanceEvent
from account.reports import helper


def get_time_usage(start, end, cloud_provider, cloud_account_id):
    """
    Calculate total time any products have run for the given cloud account.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        cloud_provider (str): The cloud provider for the account
        cloud_account_id (object): The cloud-specific account ID. The type for
            cloud_account_id is dynamic and will vary according to which
            cloud_provider was found in validate_cloud_provider_account_id.

    Returns:
        dict: Total running time in seconds keyed by product type.

    """
    cloud_helper = helper.get_report_helper(cloud_provider, cloud_account_id)

    # Verify that we can get the requested account before proceeding.
    cloud_helper.assert_account_exists()

    # Retrieve all relevant events and group into reporting-relevant buckets.
    events = _get_relevant_events(start, end, cloud_helper)
    grouped_events = _group_related_events(events, cloud_helper)

    # Sum the calculated usage by product.
    product_times = collections.defaultdict(float)
    for product_identifier, instance_events in grouped_events.items():
        run_time = sum(
            map(
                functools.partial(_calculate_instance_usage, start, end),
                instance_events.values()
            )
        )
        product_times[product_identifier] += run_time

    return dict(product_times)


def _get_relevant_events(start, end, cloud_helper):
    """
    Get all InstanceEvents relevant to the report parameters.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        cloud_helper (helper.ReportHelper): Helper for cloud-specific things

    Returns:
        list(InstanceEvent): All events relevant to the report parameters.
    """
    # Get the nearest event before the reporting period for each instance.
    account_filter = cloud_helper.instance_account_filter()
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
        cloud_helper.event_account_filter() &
        models.Q(occurred_at__gte=start, occurred_at__lt=end)
    )

    # Reduce all the filters with the "or" operator.
    event_filter = functools.reduce(operator.ior, event_filters)
    events = InstanceEvent.objects.filter(event_filter).select_related()\
        .order_by('instance__id')
    return events


def _group_related_events(events, cloud_helper):
    """
    Group the events by multiple dimensions in nested dicts.

    At the outer later, the keys are "product type" strings. These are a
    combination of (virtual) hardware definition and found software product
    that ultimately each needs to be reported with a sum total of running time.
    At the next layer, the keys are the instance IDs. Finally, each of those
    instance ID keys points to a list of InstanceEvents that belong to it.

    This "double nesting" of product+instance is necessary because instance IDs
    alone would not be sufficient for grouping because some cloud providers
    allow resizing of an existing instance without changing/replacing its ID.

    For example, a returned structure might look like:

        {
            'aws-t2.micro-rhel7': {
                'i-05f78714782d7979b': [
                    <InstanceEvent object>
                ]
            },
            'aws-t2.nano-rhel7': {
                'i-05f64764381d6970a': [
                    <InstanceEvent object>
                ],
                'i-05f78714782d7979b': [
                    <InstanceEvent object>,
                    <InstanceEvent object>,
                    <InstanceEvent object>
                ]
            }
        }

    Args:
        events (list(InstanceEvent)): Events to group
        cloud_helper (helper.ReportHelper): Helper for cloud-specific things

    Returns:
        dict: Results as a dict-of-dicts-of-lists as described above.
    """
    grouped_events = collections.defaultdict(
        functools.partial(collections.defaultdict, list)
    )

    for event in events:
        product_key = cloud_helper.get_event_product_identifier(event)
        instance_key = cloud_helper.get_event_instance_identifier(event)
        grouped_events[product_key][instance_key].append(event)

    return grouped_events


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
    for event in sorted_events:
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
