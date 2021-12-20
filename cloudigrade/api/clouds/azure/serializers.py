"""Cloudigrade API DRF Serializers for Azure."""
from rest_framework.fields import IntegerField
from rest_framework.serializers import ModelSerializer

from api.clouds.azure.models import AzureCloudAccount, AzureInstance, AzureMachineImage


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


class AzureMachineImageSerializer(ModelSerializer):
    """Serialize a customer AzureMachineImage for API v2."""

    azure_image_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = AzureMachineImage
        fields = (
            "azure_image_id",
            "created_at",
            "resource_id",
            "id",
            "region",
            "updated_at",
            "is_marketplace",
        )
        read_only_fields = (
            "created_at",
            "resource_id",
            "id",
            "region",
            "updated_at",
            "is_cloud_access",
            "is_marketplace",
        )

    def create(self, validated_data):
        """Create an AzureMachineImage."""
        raise NotImplementedError

    def update(self, instance, validated_data):
        """Update an AzureMachineImage."""
        raise NotImplementedError


class AzureInstanceSerializer(ModelSerializer):
    """Serialize a customer AzureInstance for API v2."""

    azure_instance_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = AzureInstance
        fields = (
            "azure_instance_id",
            "created_at",
            "resource_id",
            "region",
            "updated_at",
        )
        read_only_fields = (
            "account",
            "created_at",
            "resource_id",
            "id",
            "region",
            "updated_at",
        )

    def create(self, validated_data):
        """Create a AzureInstance."""
        raise NotImplementedError

    def update(self, instance, validated_data):
        """Update a AzureInstance."""
        raise NotImplementedError
