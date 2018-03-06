"""DRF API views for the account app."""
from rest_framework import viewsets, mixins

from account import serializers
from account.models import Account


class AccountViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """
    List all, retrieve a single, or create a customer Account.

    Do not allow to update, replace, or delete an Account.
    """

    queryset = Account.objects.all()
    serializer_class = serializers.AccountSerializer
