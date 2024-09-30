"""DRF serializers for the cloudigrade public API."""

from django.utils.translation import gettext as _
from generic_relations.relations import GenericRelatedField
from rest_framework.exceptions import ValidationError
from rest_framework.fields import (
    CharField,
    ChoiceField,
    Field,
    IntegerField,
)
from rest_framework.serializers import ModelSerializer

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING, CLOUD_PROVIDERS
from api.clouds.aws.models import AwsCloudAccount
from api.clouds.aws.serializers import AwsCloudAccountSerializer
from api.clouds.aws.util import create_aws_cloud_account
from api.clouds.azure.models import AzureCloudAccount
from api.clouds.azure.serializers import AzureCloudAccountSerializer
from api.clouds.azure.util import create_azure_cloud_account
from api.models import (
    CloudAccount,
)
from util import aws
from util.exceptions import InvalidArn


class CloudAccountSerializer(ModelSerializer):
    """
    Serialize a customer CloudAccount for API v2.

    Todo:
        Further separate the AWS-specific functionality here to make cloud-specific
        features and properties more dynamic. Consider renaming "aws_account_id" and
        "account_arn" to more generic, cloud-agnostic names. For example, the
        InstanceSerializer uses "cloud_account_id".
    """

    account_id = IntegerField(source="id", read_only=True)
    account_arn = CharField(required=False)
    aws_account_id = CharField(required=False)
    external_id = CharField(required=False)

    subscription_id = CharField(required=False)

    cloud_type = ChoiceField(choices=CLOUD_PROVIDERS, required=True)
    content_object = GenericRelatedField(
        {
            AwsCloudAccount: AwsCloudAccountSerializer(),
            AzureCloudAccount: AzureCloudAccountSerializer(),
        },
        required=False,
    )

    # Foreign key non-string properties
    user_id = IntegerField(read_only=True)

    class Meta:
        model = CloudAccount
        fields = (
            "account_id",
            "created_at",
            "updated_at",
            "user_id",
            "content_object",
            "cloud_type",
            "account_arn",
            "aws_account_id",
            "subscription_id",
            "is_enabled",
            "platform_authentication_id",
            "platform_application_id",
            "platform_application_is_paused",
            "platform_source_id",
            "external_id",
        )
        read_only_fields = (
            "aws_account_id",
            "user_id",
            "content_object",
            "is_enabled",
        )
        create_only_fields = ("cloud_type", "subscription_id")

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

        if cloud_type == AWS_PROVIDER_STRING:
            account_arn = validated_data.get("account_arn")
            if account_arn is None:
                raise ValidationError(
                    {"account_arn": Field.default_error_messages["required"]},
                    "required",
                )
            return self.create_aws_cloud_account(validated_data)
        elif cloud_type == AZURE_PROVIDER_STRING:
            subscription_id = validated_data.get("subscription_id")
            errors = {}
            if subscription_id is None:
                errors["subscription_id"] = Field.default_error_messages["required"]
            if errors:
                raise ValidationError(
                    errors,
                    "required",
                )
            return self.create_azure_cloud_account(validated_data)

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

        Validate that we have the right access to the customer's AWS cloud account,
        set up Cloud Trail on their cloud account.

        """
        arn = validated_data["account_arn"]
        user = self.context["request"].user
        platform_authentication_id = validated_data.get("platform_authentication_id")
        platform_application_id = validated_data.get("platform_application_id")
        platform_source_id = validated_data.get("platform_source_id")
        external_id = validated_data.get("external_id")
        cloud_account = create_aws_cloud_account(
            user,
            arn,
            platform_authentication_id,
            platform_application_id,
            platform_source_id,
            external_id,
        )
        return cloud_account

    def create_azure_cloud_account(self, validated_data):
        """Create an Azure flavored CloudAccount."""
        user = self.context["request"].user
        subscription_id = validated_data["subscription_id"]

        platform_authentication_id = validated_data.get("platform_authentication_id")
        platform_application_id = validated_data.get("platform_application_id")
        platform_source_id = validated_data.get("platform_source_id")
        cloud_account = create_azure_cloud_account(
            user,
            subscription_id,
            platform_authentication_id,
            platform_application_id,
            platform_source_id,
        )
        return cloud_account
