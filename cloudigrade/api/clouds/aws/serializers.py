"""Cloudigrade API DRF Serializers for AWS."""

from rest_framework.fields import IntegerField
from rest_framework.serializers import ModelSerializer

from api.clouds.aws.models import AwsCloudAccount


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
