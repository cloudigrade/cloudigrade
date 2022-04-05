"""Filter querysets for various internal operations."""
from django_filters import rest_framework as django_filters

from api import models
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.filters import InstanceRunningSinceFilter


class InternalCloudAccountFilterSet(django_filters.FilterSet):
    """FilterSet for limiting CloudAccounts for the internal API."""

    username = django_filters.CharFilter(field_name="user__username")

    class Meta:
        model = models.CloudAccount
        fields = {
            "is_enabled": ["exact"],
            "is_synthetic": ["exact"],
            "object_id": ["exact"],
            "platform_application_id": ["exact"],
            "platform_application_is_paused": ["exact"],
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
            "object_id": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalInstanceEventFilterSet(django_filters.FilterSet):
    """FilterSet for limiting InstanceEvents for the internal API."""

    username = django_filters.CharFilter(
        field_name="instance__cloud_account__user__username"
    )
    cloud_account = django_filters.NumberFilter(field_name="instance__cloud_account")

    class Meta:
        model = models.InstanceEvent
        fields = {
            "event_type": ["exact"],
            "instance": ["exact"],
            "object_id": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalRunFilterSet(django_filters.FilterSet):
    """FilterSet for limiting Runs for the internal API."""

    username = django_filters.CharFilter(
        field_name="instance__cloud_account__user__username"
    )
    cloud_account = django_filters.NumberFilter(field_name="instance__cloud_account")

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
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalAzureCloudAccountFilterSet(django_filters.FilterSet):
    """FilterSet for limiting AzureCloudAccounts for the internal API."""

    username = django_filters.CharFilter(field_name="cloud_account__user__username")

    class Meta:
        model = azure_models.AzureCloudAccount
        fields = {
            "subscription_id": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }
