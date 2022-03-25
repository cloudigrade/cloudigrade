"""DRF serializers for the cloudigrade internal API."""
from django.contrib.auth.models import User
from django_celery_beat.models import PeriodicTask
from rest_framework import serializers
from rest_framework.fields import BooleanField
from rest_framework.serializers import ModelSerializer

from api import models
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models


class InternalUserSerializer(ModelSerializer):
    """Serialize User for the internal API."""

    class Meta:
        model = User
        fields = (
            "date_joined",
            "id",
            "username",
        )


class InternalUserTaskLockSerializer(ModelSerializer):
    """Serialize UserTaskLock for the internal API."""

    class Meta:
        model = models.UserTaskLock
        fields = "__all__"


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
            "potentially_related_runs",
        )

    def __init__(self, *args, **kwargs):
        """
        Initialize the serializer with extra field filtering logic.

        If the incoming request is a GET with a True-like value in "include_runs",
        then include the detailed "potentially_related_runs" field. Else, drop it.
        """
        super().__init__(*args, **kwargs)

        try:
            request = self.context["request"]
            method = request.method
        except (AttributeError, TypeError, KeyError):
            # The serializer was not initialized with request context.
            return

        if method != "GET":
            return

        query_params = request.query_params
        include_runs = query_params.get("include_runs", default=False)
        include_runs = BooleanField().to_internal_value(include_runs)
        if not include_runs:
            self.fields.pop("potentially_related_runs")


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
            "product_codes",
            "platform_details",
            "usage_operation",
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


class InternalAzureCloudAccountSerializer(ModelSerializer):
    """Serialize AzureCloudAccount for the internal API."""

    class Meta:
        model = azure_models.AzureCloudAccount
        fields = "__all__"


class InternalAzureInstanceSerializer(ModelSerializer):
    """Serialize AzureInstance for the internal API."""

    class Meta:
        model = azure_models.AzureInstance
        fields = "__all__"


class InternalAzureInstanceEventSerializer(ModelSerializer):
    """Serialize AzureInstanceEvent for the internal API."""

    class Meta:
        model = azure_models.AzureInstanceEvent
        fields = "__all__"


class InternalAzureMachineImageSerializer(ModelSerializer):
    """Serialize AzureMachineImage for the internal API."""

    class Meta:
        model = azure_models.AzureMachineImage
        fields = (
            # from the model:
            "id",
            "created_at",
            "updated_at",
            "resource_id",
            "region",
            "azure_marketplace_image",
            # from property functions:
            "is_cloud_access",
            "is_marketplace",
        )


class InternalPeriodicTaskSerializer(ModelSerializer):
    """Serialize PeriodicTask for the internal API."""

    # Important note: last_run_at is redefined here because in the underlying model it
    # has "editable=False" which coerces DRF into making it a read-only field, but we
    # specifically want it writable from this serializer.
    last_run_at = serializers.DateTimeField()

    class Meta:
        model = PeriodicTask
        fields = "__all__"

        # For now, *all* of the fields *except* "last_run_at" are read-only.
        # We may relax this later as needed, but we want to minimize use of this API.
        # PeriodicTask objects should normally be updated by the beat's config directly
        # or by in-app model changes.
        read_only_fields = tuple(
            set(f.name for f in model._meta.get_fields()) - set(("last_run_at",))
        )


class InternalSyntheticDataRequestSerializer(ModelSerializer):
    """Serialize SyntheticDataRequest for the internal API."""

    class Meta:
        model = models.SyntheticDataRequest
        fields = (
            "id",
            "user",
            "machine_images",
            "expires_at",
            "created_at",
            "updated_at",
            "cloud_type",
            "since_days_ago",
            "account_count",
            "image_count",
            "image_ocp_chance",
            "image_rhel_chance",
            "image_other_owner_chance",
            "instance_count",
            "run_count_per_instance_min",
            "run_count_per_instance_mean",
            "hours_per_run_min",
            "hours_per_run_mean",
            "hours_between_runs_mean",
            "expires_at",
        )

        read_only_fields = (
            "id",
            "user",
            "machine_images",
            "expires_at",
            "created_at",
            "updated_at",
        )

        create_only_fields = (
            "cloud_type",
            "since_days_ago",
            "account_count",
            "image_count",
            "image_ocp_chance",
            "image_rhel_chance",
            "image_other_owner_chance",
            "instance_count",
            "run_count_per_instance_min",
            "run_count_per_instance_mean",
            "hours_per_run_min",
            "hours_per_run_mean",
            "hours_between_runs_mean",
            "expires_at",
        )
