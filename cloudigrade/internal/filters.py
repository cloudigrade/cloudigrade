"""Filter querysets for various internal operations."""
from django_filters import rest_framework as django_filters

from api import models
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models


class InternalCloudAccountFilterSet(django_filters.FilterSet):
    """FilterSet for limiting CloudAccounts for the internal API."""

    account_number = django_filters.CharFilter(field_name="user__account_number")
    org_id = django_filters.CharFilter(field_name="user__org_id")
    username = django_filters.CharFilter(field_name="user__account_number")

    class Meta:
        model = models.CloudAccount
        fields = {
            "is_enabled": ["exact"],
            "object_id": ["exact"],
            "platform_application_id": ["exact"],
            "platform_application_is_paused": ["exact"],
            "platform_authentication_id": ["exact"],
            "platform_source_id": ["exact"],
            "user": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }


class InternalUserFilterSet(django_filters.FilterSet):
    """FilterSet for limiting api.User for the internal API."""

    username = django_filters.CharFilter(field_name="account_number")

    class Meta:
        model = models.User
        fields = {
            "account_number": ["exact"],
            "date_joined": ["lt", "exact", "gt"],
            "org_id": ["exact"],
            "uuid": ["exact"],
        }


class InternalAwsCloudAccountFilterSet(django_filters.FilterSet):
    """FilterSet for limiting AwsCloudAccounts for the internal API."""

    account_number = django_filters.CharFilter(
        field_name="cloud_account__user__account_number"
    )
    org_id = django_filters.CharFilter(field_name="cloud_account__user__org_id")
    username = django_filters.CharFilter(
        field_name="cloud_account__user__account_number"
    )

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

    account_number = django_filters.CharFilter(
        field_name="cloud_account__user__account_number"
    )
    org_id = django_filters.CharFilter(field_name="cloud_account__user__org_id")
    username = django_filters.CharFilter(
        field_name="cloud_account__user__account_number"
    )

    class Meta:
        model = azure_models.AzureCloudAccount
        fields = {
            "subscription_id": ["exact"],
            "created_at": ["lt", "exact", "gt"],
            "updated_at": ["lt", "exact", "gt"],
        }
