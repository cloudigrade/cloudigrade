"""Cloudigrade API DRF Serializers for AWS."""
from rest_framework.fields import IntegerField
from rest_framework.serializers import ModelSerializer

from api.clouds.aws.models import AwsCloudAccount, AwsInstance, AwsMachineImage


class AwsCloudAccountSerializer(ModelSerializer):
    """Serialize a customer AWS CloudAccount for API v2."""

    aws_cloud_account_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = AwsCloudAccount
        fields = (
            "account_arn",
            "aws_account_id",
            "aws_cloud_account_id",
            "created_at",
            "updated_at",
        )


class AwsMachineImageSerializer(ModelSerializer):
    """Serialize a customer AwsMachineImage for API v2."""

    aws_image_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = AwsMachineImage
        fields = (
            "aws_image_id",
            "created_at",
            "ec2_ami_id",
            "id",
            "owner_aws_account_id",
            "platform",
            "region",
            "updated_at",
            "is_cloud_access",
            "is_marketplace",
        )
        read_only_fields = (
            "created_at",
            "ec2_ami_id",
            "id",
            "owner_aws_account_id",
            "platform",
            "region",
            "updated_at",
            "is_cloud_access",
            "is_marketplace",
        )

    def create(self, validated_data):
        """Create an AwsMachineImage."""
        raise NotImplementedError

    def update(self, instance, validated_data):
        """Update an AwsMachineImage."""
        raise NotImplementedError


class AwsInstanceSerializer(ModelSerializer):
    """Serialize a customer AwsInstance for API v2."""

    aws_instance_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = AwsInstance
        fields = (
            "aws_instance_id",
            "created_at",
            "ec2_instance_id",
            "region",
            "updated_at",
        )
        read_only_fields = (
            "account",
            "created_at",
            "ec2_instance_id",
            "id",
            "region",
            "updated_at",
        )

    def create(self, validated_data):
        """Create a AwsInstance."""
        raise NotImplementedError

    def update(self, instance, validated_data):
        """Update a AwsInstance."""
        raise NotImplementedError
