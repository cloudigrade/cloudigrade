"""Custom permission classes for the rest of the application."""
from rest_framework import permissions


class IsSuperUser(permissions.BasePermission):
    """Allow access to only authenticated superusers."""

    def has_permission(self, request, view):
        """Check if OPTIONS call or superuser."""
        if request.method == 'OPTIONS':
            return True
        return request.user and request.user.is_superuser
