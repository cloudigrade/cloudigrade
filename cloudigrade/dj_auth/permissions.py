"""Collection of tests for custom DRF permissions in the account app."""
from rest_framework import permissions


class IsAuthenticated(permissions.IsAuthenticated):
    """Allow access to only authenticated users, unless its an OPTIONS call."""

    def has_permission(self, request, view):
        """Allow access if OPTIONS call."""
        if request.method == 'OPTIONS':
            return True
        return super(IsAuthenticated, self).has_permission(request, view)
