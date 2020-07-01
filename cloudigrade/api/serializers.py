"""DRF API serializers for the account app v2."""
from datetime import timedelta

from django.utils.translation import gettext as _
from generic_relations.relations import GenericRelatedField
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import (
    CharField,
    ChoiceField,
    Field,
    IntegerField,
)
from rest_framework.serializers import ModelSerializer, Serializer

from api import CLOUD_PROVIDERS
from api.clouds.aws.models import AwsCloudAccount, AwsInstance, AwsMachineImage
from api.clouds.aws.serializers import (
    AwsCloudAccountSerializer,
    AwsInstanceSerializer,
    AwsMachineImageSerializer,
)
from api.clouds.aws.util import create_aws_cloud_account
from api.models import (
    CloudAccount,
    Instance,
    MachineImage,
)
from api.util import get_max_concurrent_usage
from util import aws
from util.exceptions import InvalidArn
from util.misc import get_today


class CloudAccountSerializer(ModelSerializer):
    """
    Serialize a customer CloudAccount for API v2.

    Todo:
        Further separate the AWS-specific functionality here to make cloud-specific
        features and properties more dynamic. Consider renaming "aws_account_id" and
        "account_arn" to more generic, cloud-agnostic names. For example, the
        InstanceSerializer uses "cloud_account_id".
    """

    account_arn = CharField(required=False)
    account_id = IntegerField(source="id", read_only=True)
    aws_account_id = CharField(required=False)

    cloud_type = ChoiceField(choices=CLOUD_PROVIDERS, required=True)
    content_object = GenericRelatedField(
        {AwsCloudAccount: AwsCloudAccountSerializer(),}, required=False
    )

    class Meta:
        model = CloudAccount
        fields = (
            "account_id",
            "created_at",
            "name",
            "updated_at",
            "user_id",
            "content_object",
            "cloud_type",
            "account_arn",
            "aws_account_id",
            "is_enabled",
            "platform_authentication_id",
            "platform_application_id",
            "platform_endpoint_id",
            "platform_source_id",
        )
        read_only_fields = (
            "aws_account_id",
            "user_id",
            "content_object",
            "is_enabled",
        )
        create_only_fields = ("cloud_type",)

    def validate_name(self, value):
        """Validate the input name is unique."""
        user = self.context["request"].user

        if CloudAccount.objects.filter(user=user, name=value).exists():
            raise ValidationError(
                _(
                    "Account with name '{0}' for account number '{1}' already exists"
                ).format(value, user.username)
            )

        return value

    def validate_account_arn(self, value):
        """Validate the input account_arn."""
        if (
            self.instance is not None
            and value != self.instance.content_object.account_arn
        ):
            raise ValidationError(_("You cannot update account_arn."))
        try:
            aws.AwsArn(value)
        except InvalidArn:
            raise ValidationError(_("Invalid ARN."))
        return value

    def create(self, validated_data):
        """
        Create a CloudAccount.

        Validates:
            - account_arn must not be None if cloud_type is aws
        """
        cloud_type = validated_data["cloud_type"]

        if cloud_type == "aws":
            account_arn = validated_data.get("account_arn")
            if account_arn is None:
                raise ValidationError(
                    {"account_arn": Field.default_error_messages["required"]},
                    "required",
                )
            return self.create_aws_cloud_account(validated_data)
        else:
            raise NotImplementedError

    def update(self, instance, validated_data):
        """Update the instance with the name from validated_data."""
        errors = {}

        for field in validated_data.copy():
            if field in self.Meta.create_only_fields:
                if getattr(instance, field) != validated_data.get(field):
                    errors[field] = [_("You cannot update field {}.").format(field)]
                else:
                    validated_data.pop(field, None)
        if errors:
            raise ValidationError(errors)
        return super().update(instance, validated_data)

    def get_user_id(self, account):
        """Get the user_id property for serialization."""
        return account.user_id

    def create_aws_cloud_account(self, validated_data):
        """
        Create an AWS flavored CloudAccount.

        Validate that we have the right access to the customer's AWS clount,
        set up Cloud Trail on their clount.

        """
        arn = validated_data["account_arn"]
        user = self.context["request"].user
        name = validated_data.get("name")
        platform_authentication_id = validated_data.get("platform_authentication_id")
        platform_application_id = validated_data.get("platform_application_id")
        platform_endpoint_id = validated_data.get("platform_endpoint_id")
        platform_source_id = validated_data.get("platform_source_id")
        cloud_account = create_aws_cloud_account(
            user,
            arn,
            name,
            platform_authentication_id,
            platform_application_id,
            platform_endpoint_id,
            platform_source_id,
        )
        return cloud_account


class MachineImageSerializer(ModelSerializer):
    """Serialize a customer AwsMachineImage for API v2."""

    cloud_type = ChoiceField(choices=["aws"], required=False)
    content_object = GenericRelatedField(
        {AwsMachineImage: AwsMachineImageSerializer(),}, required=False
    )

    image_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = MachineImage
        fields = (
            "architecture",
            "created_at",
            "image_id",
            "inspection_json",
            "is_encrypted",
            "name",
            "openshift",
            "openshift_detected",
            "rhel",
            "rhel_detected",
            "rhel_detected_by_tag",
            "rhel_enabled_repos_found",
            "rhel_product_certs_found",
            "rhel_release_files_found",
            "rhel_signed_packages_found",
            "rhel_version",
            "status",
            "syspurpose",
            "updated_at",
            "cloud_type",
            "content_object",
        )
        read_only_fields = (
            "architecture",
            "created_at",
            "id",
            "inspection_json",
            "is_encrypted",
            "name",
            "openshift",
            "openshift_detected",
            "rhel",
            "rhel_detected",
            "rhel_detected_by_tag",
            "rhel_enabled_repos_found",
            "rhel_product_certs_found",
            "rhel_release_files_found",
            "rhel_signed_packages_found",
            "rhel_version",
            "status",
            "syspurpose",
            "updated_at",
            "cloud_type",
        )


class InstanceSerializer(ModelSerializer):
    """Serialize a customer AwsInstance for API v2."""

    cloud_type = ChoiceField(choices=["aws"], required=False)
    content_object = GenericRelatedField(
        {AwsInstance: AwsInstanceSerializer(),}, required=False
    )
    instance_id = IntegerField(source="id", read_only=True)

    class Meta:
        model = Instance
        fields = (
            "cloud_account_id",
            "created_at",
            "instance_id",
            "machine_image_id",
            "updated_at",
            "cloud_type",
            "content_object",
        )
        read_only_fields = (
            "cloud_account_id",
            "created_at",
            "id",
            "machine_image_id",
            "updated_at",
        )

    def create(self, validated_data):
        """Create a Instance."""
        raise NotImplementedError

    def update(self, instance, validated_data):
        """Update a Instance."""
        raise NotImplementedError


class DailyConcurrentUsageDummyQueryset(object):
    """Dummy queryset for getting days with their max concurrent usage."""

    def __init__(
        self, start_date=None, end_date=None, user_id=None,
    ):
        """Initialize parameters."""
        self.start_date = start_date
        self.end_date = end_date
        self.user_id = user_id
        self._days = None

    @property
    def days(self):
        """Get all days."""
        if self._days is None:
            tomorrow = get_today() + timedelta(days=1)
            days = []
            current = self.start_date
            delta_day = timedelta(days=1)
            end_date = min(self.end_date, tomorrow)
            while current < end_date:
                days.append(current)
                current += delta_day
            self._days = days
        return self._days

    def count(self):
        """Count the available days."""
        return len(self.days)

    def __getitem__(self, index):
        """Get a specific day."""
        days = self.days[index]
        results = []
        for date in days:
            result = get_max_concurrent_usage(date, self.user_id)
            results.append(result)

        return results


class DailyConcurrentUsageSerializer(Serializer):
    """Serialize a report of daily RHEL concurrency over time for the API."""

    date = serializers.DateField(required=True)
    maximum_counts = serializers.SerializerMethodField()

    def get_maximum_counts(self, obj):
        """Massage the results dict a bit."""
        response = []
        if obj.get("maximum_counts", None):
            for key, value in obj["maximum_counts"].items():
                response.append(
                    {
                        "arch": key.arch,
                        "role": key.role,
                        "sla": key.sla,
                        "instances_count": value["max_count"],
                    }
                )
        return response
