"""DRF API serializers for the account app."""
from rest_framework import serializers

from account.models import Account


class AccountSerializer(serializers.HyperlinkedModelSerializer):
    """Serialize a customer Account for the API."""

    class Meta:
        model = Account
        fields = ('id', 'url', 'account_id', 'account_arn')
