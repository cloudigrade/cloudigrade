"""Filter querysets for various operations."""

from django.db.models import Max


def cloudaccounts(queryset, user_id=None, user=None):
    """Filter CloudAccount queryset."""
    if not user.is_superuser:
        return queryset.filter(user=user)
    if user_id is not None:
        return queryset.filter(user__id=user_id)
    return queryset


def instances(queryset, user_id=None, running_since=None, user=None):
    """Filter Instance queryset."""
    if not user.is_superuser:
        queryset = queryset.filter(cloud_account__user__id=user.id)
    if user_id is not None:
        queryset = queryset.filter(cloud_account__user__id=user_id)
    # Filter based on the instance running
    if running_since is not None:
        queryset = (
            queryset.prefetch_related("run_set")
            .filter(run__start_time__isnull=False, run__end_time__isnull=True)
            .annotate(Max("run__start_time"))
            .filter(run__start_time__max__lte=running_since)
        )
    return queryset


def machineimages(queryset, architecture=None, status=None, user_id=None, user=None):
    """Filter MachineImage queryset."""
    if architecture is not None:
        queryset = queryset.filter(architecture=architecture)
    if status is not None:
        queryset = queryset.filter(status=status)

    if not user.is_superuser:
        return (
            queryset.filter(instance__cloud_account__user_id=user.id)
            .order_by("id")
            .distinct()
        )

    if user_id is not None:
        return (
            queryset.filter(instance__cloud_account__user_id=user_id)
            .order_by("id")
            .distinct()
        )
    return queryset.order_by("id")
