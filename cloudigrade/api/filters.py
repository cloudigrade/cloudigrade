"""Filter querysets for various operations."""
from django.db.models import Max
from django_filters import fields
from django_filters import rest_framework as django_filters
from rest_framework import filters as drf_filters


class CloudAccountRequestIsUserFilterBackend(drf_filters.BaseFilterBackend):
    """Filter that allows users to see only their CloudAccounts."""

    def filter_queryset(self, request, queryset, view):
        """Filter so the request's user sees only their CloudAccounts."""
        return queryset.filter(user=request.user)


class InstanceRequestIsUserFilterBackend(drf_filters.BaseFilterBackend):
    """Filter that only allows users to see only their Instances."""

    def filter_queryset(self, request, queryset, view):
        """Filter so the request's user sees only their Instances."""
        return queryset.filter(cloud_account__user=request.user)


class InstanceRunningSinceFilter(django_filters.IsoDateTimeFilter):
    """Filter that only allows Instances running since the given datetime."""

    def filter(self, qs, value):
        """
        Filter the queryset for the given value.

        Note that most of this implementation is a direct copy of the code from
        django_filters.filters.Filter.filter because there doesn't appear to be
        sufficient isolation of functionality to override *just* the query-building
        piece.
        """
        if value in fields.EMPTY_VALUES:
            return qs
        if self.distinct:
            qs = qs.distinct()
        if self.exclude:
            # Note that we always "filter"; we do not yet support "exclude".
            raise RuntimeError("Cannot exclude using InstanceRunningSinceFilter")

        qs = (
            qs.prefetch_related("run_set")
            .filter(run__start_time__isnull=False, run__end_time__isnull=True)
            .annotate(Max("run__start_time"))
            .filter(run__start_time__max__lte=value)
        )
        return qs


class InstanceFilterSet(django_filters.FilterSet):
    """FilterSet for limiting Instances."""

    running_since = InstanceRunningSinceFilter()


class MachineImageRequestIsUserFilterBackend(drf_filters.BaseFilterBackend):
    """Filter that only allows users to see MachineImages for only their Instances."""

    def filter_queryset(self, request, queryset, view):
        """Filter so the request's user sees MachineImages for only their Instances."""
        return (
            queryset.filter(instance__cloud_account__user=request.user)
            .order_by("id")
            .distinct()
        )
