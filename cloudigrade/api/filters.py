"""Filter querysets for various operations."""
from rest_framework import filters as drf_filters


class CloudAccountRequestIsUserFilterBackend(drf_filters.BaseFilterBackend):
    """Filter that allows users to see only their CloudAccounts."""

    def filter_queryset(self, request, queryset, view):
        """Filter so the request's user sees only their CloudAccounts."""
        return queryset.filter(user=request.user)
