"""Utility functions."""
import collections
import itertools
import logging
from datetime import datetime, timedelta

from dateutil import tz
from django.db.models import Q
from django.utils.translation import gettext as _

from api.models import (AwsEC2InstanceDefinition, AwsInstanceEvent, Instance,
                        Run)

logger = logging.getLogger(__name__)


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
        AwsInstanceEvent.objects.filter(
            instance_event__instance=instance,
            instance_event__occurred_at__lte=before_date,
            instance_event__instance_type__isnull=False,
        )
        .order_by('-occurred_at')
        .first()
    )
    if event is None:
        logger.error(
            _('could not find any type for %(instance)s by %(before_date)s'),
            {'instance': instance, 'before_date': before_date},
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
            AwsEC2InstanceDefinition.objects.get(instance_type=instance_type)
            if instance_type
            else None
        )
    except AwsEC2InstanceDefinition.DoesNotExist:
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
        ].content_object.instance_type or get_last_known_instance_type(
            events[0].instance, events[0].occurred_at
        )
        type_definition = get_instance_type_definition(instance_type)
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
                    _(
                        'Instance %s does not have an associated '
                        'machine image.'
                    ),
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


def max_concurrent_usage(day, user_id=None, cloud_account_id=None):
    """
    Find maximum concurrent usage of RHEL instances in the given parameters.

    Args:
        day (datetime.date): the day during which we are measuring usage
        user_id (int): optional filter on user
        cloud_account_id (int): optional filter on cloud account

    Returns:
        dict containing the values of maximum concurrent number of instances,
        vcpu, and memory encountered at any point during the day.

    """
    queryset = Run.objects.all()
    if user_id:
        queryset = queryset.filter(instance__cloud_account__user__id=user_id)
    if cloud_account_id:
        queryset = queryset.filter(
            instance__cloud_account__id=cloud_account_id
        )
    start = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=tz.tzutc())
    end = start + timedelta(days=1)

    # We want to filter to Runs that have:
    # - started before (not inclusive) our end time
    # - ended at or after our start time (inclusive) or have never stopped
    runs = queryset.filter(
        Q(end_time__isnull=True) | Q(end_time__gte=start), start_time__lt=end,
    ).prefetch_related('machineimage')

    # Now that we have the Runs, we need to extract the start and stop times
    # from each Run, put them in a list, and order them chronologically. If we
    # ever want to know about concurrency for things other than RHEL, we would
    # repeat the following pattern for each other filter/condition.
    rhel_on_offs = []
    for run in runs:
        if not run.machineimage.rhel:
            continue
        rhel_on_offs.append((run.start_time, True, run.vcpu, run.memory))
        if run.end_time:
            rhel_on_offs.append((run.end_time, False, run.vcpu, run.memory))

    rhel_on_offs = sorted(rhel_on_offs, key=lambda r: r[0])

    # Now that we have the start and stop times ordered, we can easily find the
    # maximum concurrency by walking forward in time and counting up.
    current_instances, max_instances = 0, 0
    current_vcpu, max_vcpu = 0, 0
    current_memory, max_memory = 0.0, 0.0
    for __, is_start, vcpu, memory in rhel_on_offs:
        if is_start:
            current_instances += 1
            current_vcpu += vcpu if vcpu is not None else 0
            current_memory += memory if memory is not None else 0.0
        else:
            current_instances -= 1
            current_vcpu -= vcpu if vcpu is not None else 0
            current_memory -= memory if memory is not None else 0.0
        max_instances = max(current_instances, max_instances)
        max_vcpu = max(current_vcpu, max_vcpu)
        max_memory = max(current_memory, max_memory)

    return {
        'date': day,
        'instances': max_instances,
        'vcpu': max_vcpu,
        'memory': max_memory,
    }
