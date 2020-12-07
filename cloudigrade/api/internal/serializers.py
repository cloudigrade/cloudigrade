"""DRF serializers for the cloudigrade internal API."""
from django.contrib.auth.models import User
from rest_framework.serializers import ModelSerializer

from api import models
from api.clouds.aws import models as aws_models


class InternalUserSerializer(ModelSerializer):
    """Serialize User for the internal API."""

    class Meta:
        model = User
        fields = (
            "date_joined",
            "id",
            "username",
        )


class InternalCloudAccountSerializer(ModelSerializer):
    """Serialize CloudAccount for the internal API."""

    class Meta:
        model = models.CloudAccount
        fields = "__all__"


class InternalMachineImageSerializer(ModelSerializer):
    """Serialize MachineImage for the internal API."""

    class Meta:
        model = models.MachineImage
        fields = "__all__"


class InternalInstanceSerializer(ModelSerializer):
    """Serialize Instance for the internal API."""

    class Meta:
        model = models.Instance
        fields = "__all__"


class InternalInstanceEventSerializer(ModelSerializer):
    """Serialize InstanceEvent for the internal API."""

    class Meta:
        model = models.InstanceEvent
        fields = "__all__"


class InternalRunSerializer(ModelSerializer):
    """Serialize Run for the internal API."""

    class Meta:
        model = models.Run
        fields = "__all__"


class InternalMachineImageInspectionStartSerializer(ModelSerializer):
    """Serialize MachineImageInspectionStart for the internal API."""

    class Meta:
        model = models.MachineImageInspectionStart
        fields = "__all__"


class InternalConcurrentUsageSerializer(ModelSerializer):
    """Serialize ConcurrentUsage for the internal API."""

    class Meta:
        model = models.ConcurrentUsage
        fields = (
            "id",
            "created_at",
            "updated_at",
            "date",
            "user",
            "maximum_counts",
        )


class InternalConcurrentUsageCalculationTaskSerializer(ModelSerializer):
    """Serialize ConcurrentUsageCalculationTask for the internal API."""

    class Meta:
        model = models.ConcurrentUsageCalculationTask
        fields = "__all__"


class InternalInstanceDefinitionSerializer(ModelSerializer):
    """Serialize InstanceDefinition for the internal API."""

    class Meta:
        model = models.InstanceDefinition
        fields = "__all__"


class InternalAwsCloudAccountSerializer(ModelSerializer):
    """Serialize AwsCloudAccount for the internal API."""

    class Meta:
        model = aws_models.AwsCloudAccount
        fields = "__all__"


class InternalAwsInstanceSerializer(ModelSerializer):
    """Serialize AwsInstance for the internal API."""

    class Meta:
        model = aws_models.AwsInstance
        fields = "__all__"


class InternalAwsMachineImageSerializer(ModelSerializer):
    """Serialize AwsMachineImage for the internal API."""

    class Meta:
        model = aws_models.AwsMachineImage
        fields = (
            # from the model:
            "id",
            "created_at",
            "updated_at",
            "ec2_ami_id",
            "platform",
            "owner_aws_account_id",
            "region",
            "aws_marketplace_image",
            # from property functions:
            "is_cloud_access",
            "is_marketplace",
        )


class InternalAwsMachineImageCopySerializer(ModelSerializer):
    """Serialize AwsMachineImageCopy for the internal API."""

    class Meta:
        model = aws_models.AwsMachineImageCopy
        fields = (
            # from the model:
            "id",
            "created_at",
            "updated_at",
            "ec2_ami_id",
            "platform",
            "owner_aws_account_id",
            "region",
            "aws_marketplace_image",
            "reference_awsmachineimage_id",
            # from property functions:
            "is_cloud_access",
            "is_marketplace",
        )


class InternalAwsInstanceEventSerializer(ModelSerializer):
    """Serialize AwsInstanceEvent for the internal API."""

    class Meta:
        model = aws_models.AwsInstanceEvent
        fields = "__all__"
