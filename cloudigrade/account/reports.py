"""Cloud provider-agnostic report-building functionality."""
import collections
import datetime
import functools
import logging
import operator

from django.db import models
from django.utils.translation import gettext as _

from account.models import (Account, AwsEC2InstanceDefinitions, Instance,
                            InstanceEvent, MachineImage)

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

    instance_events = collections.defaultdict(list)
    for event in events:
        instance_events[event.instance].append(event)
    instance_events = dict(instance_events)

    usage = _calculate_daily_usage(start, end, instance_events)
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


def _get_image_from_instance_events(events):
    """
    Get the first MachineImage from a set of InstanceEvents.

    Args:
        events (list[InstanceEvent]): The events being checked

    Returns:
        MachineImage: the first image found or None if none is found.

    """
    image = None
    for event in events:
        if event.machineimage:
            image = event.machineimage
            break
    return image


def _calculate_daily_usage(start, end, instance_events):
    """
    Get all InstanceEvents relevant to the report parameters.

    Args:
        start (datetime.datetime): Start time (inclusive)
        end (datetime.datetime): End time (exclusive)
        instance_events (list[InstanceEvent]): events to use for calculations
    """
    periods = _generate_daily_periods(start, end)
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

        rhel_vcpu = 0.0
        openshift_vcpu = 0.0
        rhel_mem = 0.0
        openshift_mem = 0.0

        for instance, events in instance_events.items():
            usage = _calculate_instance_usage(
                period_start,
                period_end,
                events,
            )
            runtime = usage['runtime']

            if runtime == 0.0 or runtime is None:
                # No runtime? No updates to counters.
                continue

            # Since all events for AWS have the same image, we can short-
            # circuit the logic here and find any event's image. We may need
            # to revisit this logic in the future if we add support for a
            # cloud provider that allows you to change the image on an
            # existing instance.
            image = _get_image_from_instance_events(events)
            if image is None:
                logger.debug(_(
                    'Instance {0} has no known machine image. Therefore '
                    'we do not know to report it as RHEL or OpenShift.'
                ).format(instance))
                continue
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
                rhel_mem += usage['memory']
                rhel_vcpu += usage['vcpu']

            if image.id in image_ids_seen_with_openshift:
                openshift_instance_count += 1
                instance_ids_seen_with_openshift.add(instance.id)
                openshift_seconds += runtime
                openshift_mem += usage['memory']
                openshift_vcpu += usage['vcpu']

        daily_usage.append({
            'date': period_start,
            'rhel_instances': rhel_instance_count,
            'openshift_instances': openshift_instance_count,
            'rhel_runtime_seconds': rhel_seconds,
            'openshift_runtime_seconds': openshift_seconds,
            'rhel_vcpu_seconds': rhel_vcpu,
            'openshift_vcpu_seconds': openshift_vcpu,
            'rhel_memory_seconds': rhel_mem,
            'openshift_memory_seconds': openshift_mem
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
    vcpu_usage = 0.0
    mem_usage = 0.0

    # If start is after the current time, we cannot make any
    # meaningful assumptions about the runtime.
    if start > datetime.datetime.now(datetime.timezone.utc):
        usage = {
            'runtime': None,
            'memory': None,
            'vcpu': None
        }
        return usage

    sorted_events = sorted(events, key=lambda e: e.occurred_at)

    # Get the last event before the start date only if that event is power_on.
    before_start = list(
        filter(
            lambda event: event.event_type == InstanceEvent.TYPE.power_on,
            list(
                filter(lambda event: event.occurred_at < start, sorted_events)
            )[-1:]
        )
    )

    # find out what the instance type is at the start of the time period
    instance_events = list(filter(
        lambda event: event.instance_type is not None,
        list(
            filter(lambda event: event.occurred_at < start, sorted_events)
        )
    ))
    if instance_events == []:
        instance_type = None
    else:
        instance_type = instance_events[-1].instance_type

    after_start = [event for event in sorted_events
                   if start <= event.occurred_at < end]
    sorted_trimmed_events = before_start + after_start

    for event in sorted_trimmed_events:
        # whichever is later: the first event or the reported period start
        event_time = max(start, event.occurred_at)

        if not last_started and \
                event.event_type == InstanceEvent.TYPE.power_on:
            # hold the time only if new event is ON and was previously OFF
            last_started = event_time
            if event.instance_type is not None:
                instance_type = event.instance_type

        elif event.event_type == InstanceEvent.TYPE.attribute_change:
            instance_type = event.instance_type

        elif last_started and \
                event.event_type == InstanceEvent.TYPE.power_off:
            # add the time if new event is OFF and was previously ON
            diff = event_time - last_started
            time_running += diff.total_seconds()

            vcpu, mem = _get_vcpu_memory_usage(
                diff.total_seconds(),
                instance_type
            )
            vcpu_usage += vcpu
            mem_usage += mem

            # drop the started time, implying that the instance is now OFF
            last_started = None

    if last_started:
        diff = end - last_started
        time_running += diff.total_seconds()
        vcpu, mem = _get_vcpu_memory_usage(diff.total_seconds(), instance_type)
        vcpu_usage += vcpu
        mem_usage += mem

    usage = {
        'runtime': time_running,
        'memory': mem_usage,
        'vcpu': vcpu_usage
    }

    return usage


def _get_vcpu_memory_usage(time_running, instance_type):
    """
    Calculate Vcpu and memory usage for some instance type and runtime.

    If the AwsEC2InstanceDefinitions for the given instance_type cannot be
    found, log an error and return 0 for vcpu and memory usage. N

    Args:
        time_running (int): Time that the instance has ran, in seconds
        instance_type (str): Type of the running instance

    Returns:
        (float, float): A tuple of vcpu usage (in seconds),
                        and memory usage (in seconds)

    """
    if time_running == 0.0 or instance_type is None:
        return (0, 0)

    try:
        instance_definition = AwsEC2InstanceDefinitions.objects.get(
            instance_type=instance_type
        )
        vcpu_usage = time_running * instance_definition.vcpu
        mem_usage = time_running * instance_definition.memory

        return (vcpu_usage, mem_usage)

    except AwsEC2InstanceDefinitions.DoesNotExist:
        logger.error(
            _(
                'Could not find instance type {} in mapping table.'
            ).format(instance_type)
        )
        return (0, 0)


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
    image_ids = []
    instance_events = collections.defaultdict(list)

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
    else:
        # _get_relevant_events will return the events in between the start &
        # end times & if no events are present during this period, it will
        # return the last event that occurred.
        events = _get_relevant_events(start, end, [account.id])
        for event in events:
            valid_event = validate_event(event, start)
            if valid_event:
                if event.machineimage:
                    image_ids.append(event.machineimage.id)
                    instance_events[event.instance].append(event)
                else:
                    logger.debug(_(
                        'Instance event {0} has no machine image. Therefore '
                        'we do not know to report it as RHEL or OpenShift.'
                    ).format(event))

        # Calculate usage
        usage = _calculate_daily_usage(start, end, instance_events)

        total_images = len(set(image_ids))
        total_challenged_images_rhel, total_challenged_images_openshift = 0, 0
        images = MachineImage.objects.filter(pk__in=set(image_ids))
        for image in images:
            if image.rhel_challenged:
                total_challenged_images_rhel += 1
            if image.openshift_challenged:
                total_challenged_images_openshift += 1
        total_instances = len(instance_events.keys())
        total_instances_rhel = usage['instances_seen_with_rhel']
        total_instances_openshift = usage['instances_seen_with_openshift']
        # sum the total rhel runtime across instances
        total_runtime_rhel = functools.reduce(
            lambda x, y: x + y['rhel_runtime_seconds'], usage['daily_usage'], 0
        )
        # sum the total openshift runtime across instances
        total_runtime_openshift = functools.reduce(
            lambda x, y: x + y['openshift_runtime_seconds'],
            usage['daily_usage'], 0
        )

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
    }

    return cloud_account


class ImageActivityData():
    """Helper data structure for counting image activity."""

    _machine_image_iterable_keys = (
        'id',
        'cloud_image_id',
        'name',
        'status',
        'is_encrypted',
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
    )

    def __init__(self):
        """Initialize an empty instance."""
        self.machine_image = None
        self.instance_ids = set()
        self.runtime_seconds = 0.0

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

    instance_events = collections.defaultdict(list)
    for event in events:
        instance_events[event.instance].append(event)
    instance_events = dict(instance_events)

    images = collections.defaultdict(ImageActivityData)
    for instance, events in instance_events.items():
        runtime = _calculate_instance_usage(start, end, events)['runtime']
        if not runtime:
            continue
        image = _get_image_from_instance_events(events)
        if image:
            image_id = image.id
            images[image_id].machine_image = image
            images[image_id].instance_ids.add(instance.id)
            images[image_id].runtime_seconds += runtime

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
