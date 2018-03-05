"""DRF API views for the account app."""
from rest_framework import viewsets

from account import serializers
from account.models import Account


class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    """List all or retrieve a single customer Account."""

    queryset = Account.objects.all()
    serializer_class = serializers.AccountSerializer
