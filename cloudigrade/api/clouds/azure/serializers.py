"""Cloudigrade API DRF Serializers for Azure."""
from rest_framework.fields import IntegerField
from rest_framework.serializers import ModelSerializer

from api.clouds.azure.models import AzureCloudAccount


class AzureCloudAccountSerializer(ModelSerializer):
    """Serialize a customer AWS CloudAccount for API v2."""

    azure_cloud_account_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = AzureCloudAccount
        fields = (
            "azure_cloud_account_id",
            "subscription_id",
            "created_at",
            "updated_at",
        )
