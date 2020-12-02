"""Filter querysets for various operations."""

from django.db.models import Max


def cloudaccounts(queryset, user):
    """Filter CloudAccount queryset."""
    return queryset.filter(user=user)


def instances(queryset, user, running_since=None):
    """Filter Instance queryset."""
    queryset = queryset.filter(cloud_account__user__id=user.id)
    # Filter based on the instance running
    if running_since is not None:
        queryset = (
            queryset.prefetch_related("run_set")
            .filter(run__start_time__isnull=False, run__end_time__isnull=True)
            .annotate(Max("run__start_time"))
            .filter(run__start_time__max__lte=running_since)
        )
    return queryset


def machineimages(queryset, user, architecture=None, status=None):
    """Filter MachineImage queryset."""
    if architecture is not None:
        queryset = queryset.filter(architecture=architecture)
    if status is not None:
        queryset = queryset.filter(status=status)
    return (
        queryset.filter(instance__cloud_account__user_id=user.id)
        .order_by("id")
        .distinct()
    )
    return queryset.order_by("id")
