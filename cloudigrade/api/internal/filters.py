"""Filter querysets for various internal operations."""
from django_filters import rest_framework as django_filters

from api import models
from api.clouds.aws import models as aws_models
from api.filters import InstanceRunningSinceFilter


class InternalCloudAccountFilterSet(django_filters.FilterSet):
    """FilterSet for limiting Instances for the internal API."""

    username = django_filters.CharFilter(field_name="user__username")

    class Meta:
        model = models.CloudAccount
        fields = {
            "is_enabled": ["exact"],
            "name": ["exact"],
            "platform_application_id": ["exact"],
            "platform_authentication_id": ["exact"],
            "platform_source_id": ["exact"],
            "user": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalInstanceFilterSet(django_filters.FilterSet):
    """FilterSet for limiting Instances for the internal API."""

    running_since = InstanceRunningSinceFilter()
    username = django_filters.CharFilter(field_name="cloud_account__user__username")

    class Meta:
        model = models.Instance
        fields = {
            "cloud_account": ["exact"],
            "machine_image": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalInstanceEventFilterSet(django_filters.FilterSet):
    """FilterSet for limiting InstanceEvents for the internal API."""

    class Meta:
        model = models.InstanceEvent
        fields = {
            "event_type": ["exact"],
            "instance_id": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalMachineImageFilterSet(django_filters.FilterSet):
    """FilterSet for limiting MachineImages for the internal API."""

    class Meta:
        model = models.MachineImage
        fields = {
            "architecture": ["exact"],
            "name": ["exact"],
            "status": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalRunFilterSet(django_filters.FilterSet):
    """FilterSet for limiting Runs for the internal API."""

    username = django_filters.CharFilter(
        field_name="instance__cloud_account__user__username"
    )

    class Meta:
        model = models.Run
        fields = {
            "instance": ["exact"],
            "instance_type": ["exact"],
            "machineimage": ["exact"],
            "memory": ["exact"],
            "vcpu": ["exact"],
            "start_time": ["lt", "exact", "gt"],
            "end_time": ["lt", "exact", "gt"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalMachineImageInspectionStartFilterSet(django_filters.FilterSet):
    """FilterSet for limiting MachineImages for the internal API."""

    class Meta:
        model = models.MachineImageInspectionStart
        fields = {
            "machineimage": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalConcurrentUsageFilterSet(django_filters.FilterSet):
    """FilterSet for limiting ConcurrentUsages for the internal API."""

    username = django_filters.CharFilter(field_name="user__username")
    run = django_filters.NumberFilter(field_name="potentially_related_runs")

    class Meta:
        model = models.ConcurrentUsage
        fields = {
            "date": ["lt", "exact", "gt"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalAwsCloudAccountFilterSet(django_filters.FilterSet):
    """FilterSet for limiting AwsCloudAccounts for the internal API."""

    username = django_filters.CharFilter(field_name="cloud_account__user__username")

    class Meta:
        model = aws_models.AwsCloudAccount
        fields = {
            "aws_account_id": ["exact"],
            "account_arn": ["exact"],
            "verify_task": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalAwsInstanceFilterSet(django_filters.FilterSet):
    """FilterSet for limiting AwsInstances for the internal API."""

    class Meta:
        model = aws_models.AwsInstance
        fields = {
            "ec2_instance_id": ["exact"],
            "region": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalAwsMachineImageFilterSet(django_filters.FilterSet):
    """FilterSet for limiting AwsMachineImages for the internal API."""

    class Meta:
        model = aws_models.AwsMachineImage
        fields = {
            "ec2_ami_id": ["exact"],
            "platform": ["exact"],
            "owner_aws_account_id": ["exact"],
            "region": ["exact"],
            "aws_marketplace_image": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalAwsMachineImageCopyFilterSet(django_filters.FilterSet):
    """FilterSet for limiting AwsMachineImageCopies for the internal API."""

    class Meta:
        model = aws_models.AwsMachineImageCopy
        fields = {
            "reference_awsmachineimage": ["exact"],
            "ec2_ami_id": ["exact"],
            "platform": ["exact"],
            "owner_aws_account_id": ["exact"],
            "region": ["exact"],
            "aws_marketplace_image": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalAwsInstanceEventFilterSet(django_filters.FilterSet):
    """FilterSet for limiting AwsInstanceEvents for the internal API."""

    class Meta:
        model = aws_models.AwsInstanceEvent
        fields = {
            "subnet": ["exact"],
            "instance_type": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }
