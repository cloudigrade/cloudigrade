"""Cloudigrade report-building functionality."""
import collections
import functools
import itertools
import operator

from django.db import models

from account.models import InstanceEvent, Instance


def _calculate_instance_usage(instance_events, start, end):
    """
    Calculate instance usage based on events.

    Args:
        instance_events (list[InstanceEvent]): Events for calculating usage
        start (datetime.datetime): Start time for report filtering (inclusive)
        end (datetime.datetime): End time for report filtering (inclusive)

    Note: This assumes instance_events is already sorted appropriately.

    Returns:
        tuple(str, int): Product identifier and number of seconds it ran.

    """
    last_started = None
    product_identifier = None
    time_running = 0.0

    for event in instance_events:
        event_time = max(start, event.occurred_at)
        product_identifier = event.product_identifier

        if not last_started and \
                event.event_type == InstanceEvent.TYPE.power_on:
            last_started = event_time
        elif last_started and \
                event.event_type == InstanceEvent.TYPE.power_off:
            diff = event_time - last_started
            time_running += diff.total_seconds()
            last_started = None

    if product_identifier and last_started:
        diff = end - last_started
        time_running += diff.total_seconds()

    return product_identifier, time_running


def get_hourly_usage(start, end, account_id):
    """
    Build a data structure for reporting hourly Red Hat product usage.

    Args:
        start (datetime.datetime): Start time for report filtering (inclusive)
        end (datetime.datetime): End time for report filtering (inclusive)
        account_id (str): AWS account ID for report filtering

    Todo:
        - Include the actual Red Hat product versions when we know them.

    Returns:
        dict: Usage in seconds keyed by "product type" which is (for now) a
        magical combination of Red Hat product version and AWS instance type.

    """
    # Get the nearest event *before* the reporting period for each instance.
    instances_before = Instance.objects.filter(
        account__account_id=account_id,
        instanceevent__occurred_at__lt=start,
    ).annotate(
        occurred_at=models.Max('instanceevent__occurred_at')
    )

    # Build a filter list for the events found before the period.
    event_filters = [
        models.Q(instance__id=i.id, occurred_at=i.occurred_at)
        for i in list(instances_before)
    ]

    # Add a filter for the events *during* the reporting period.
    event_filters.append(models.Q(
        instance__account__account_id=account_id,
        occurred_at__gte=start,
        occurred_at__lte=end
    ))

    # Reduce all the filters with the "or" operator.
    event_filter = functools.reduce(operator.ior, event_filters)
    events = InstanceEvent.objects.filter(event_filter)\
        .select_related()\
        .order_by('instance__id', 'occurred_at')

    # Group the results by instance so we can sum things up.
    instance_product_events = {
        key: list(group) for key, group in
        itertools.groupby(
            events,
            lambda e: f'{e.instance.ec2_instance_id}:{e.product_identifier}'
        )
    }

    product_times = collections.defaultdict(float)
    for key, group in instance_product_events.items():
        calculated_usage = _calculate_instance_usage(group, start, end)
        product_identifier, time_running = calculated_usage
        product_times[product_identifier] += time_running

    return product_times
