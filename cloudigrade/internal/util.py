"""Utility module for the internal API."""
from django.apps import apps
from django.db.models import Q


def find_unending_runs_power_off_events(user_id=None):
    """
    Find any Run objects that appear to have no end set but should have.

    It's unclear how this can happen, but we have observed some cases where a Run was
    created, and a power_off InstanceEvent exists, but the Run's end_time was not set.

    Returns:
        list of (Run, InstanceEvent) where the InstanceEvent should have ended the Run
    """
    Run = apps.get_model("api", "Run")
    InstanceEvent = apps.get_model("api", "InstanceEvent")

    # find all runs with no end date, optionally filtering on the user
    user_filter = Q(instance__cloud_account__user__id=user_id) if user_id else Q()
    runs = Run.objects.filter(user_filter, end_time=None)

    # find the earliest power_off event after each run's start
    run_events = []
    for run in runs:
        event = (
            InstanceEvent.objects.filter(
                instance_id=run.instance_id,
                occurred_at__gte=run.start_time,
                event_type=InstanceEvent.TYPE.power_off,
            )
            .order_by("occurred_at")
            .first()
        )
        if event:
            run_events.append((run, event))
    return run_events
