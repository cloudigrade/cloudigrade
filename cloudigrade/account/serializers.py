"""DRF API serializers for the account app."""
import logging

from botocore.exceptions import ClientError
from dateutil import tz
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.serializers import (HyperlinkedModelSerializer,
                                        Serializer)
from rest_polymorphic.serializers import PolymorphicSerializer

from account import reports, tasks
from account.models import (AwsAccount,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage)
from util import aws, misc
from util.exceptions import InvalidArn

logger = logging.getLogger(__name__)


class AwsAccountSerializer(HyperlinkedModelSerializer):
    """Serialize a customer AwsAccount for the API."""

    class Meta:
        model = AwsAccount
        fields = (
            'account_arn',
            'aws_account_id',
            'created_at',
            'id',
            'name',
            'updated_at',
            'url',
            'user_id',
        )
        read_only_fields = (
            'aws_account_id',
            'user_id',
        )
        extra_kwargs = {
            'url': {'view_name': 'account-detail', 'lookup_field': 'pk'},
        }

    def validate(self, data):
        """Validate that clount name is unique per user."""
        user = self.context['request'].user
        name = data.get('name')

        try:
            AwsAccount.objects.get(user=user, name=name)
        except AwsAccount.DoesNotExist:
            return data

        raise serializers.ValidationError(_(
            "Account with name '{0}' for user '{1}' already exists").format(
            name, user))

    def validate_account_arn(self, value):
        """Validate the input account_arn."""
        if self.instance is not None and value != self.instance.account_arn:
            raise serializers.ValidationError(
                _('You cannot change this field.')
            )
        try:
            aws.AwsArn(value)
        except InvalidArn:
            raise serializers.ValidationError(
                _('Invalid ARN.')
            )
        return value

    def create(self, validated_data):
        """Create an AwsAccount."""
        arn = aws.AwsArn(validated_data['account_arn'])
        aws_account_id = arn.account_id

        account_exists = AwsAccount.objects.filter(
            aws_account_id=aws_account_id
        ).exists()
        if account_exists:
            raise serializers.ValidationError(
                detail={
                    'account_arn': [
                        _('An ARN already exists for account "{0}"').format(
                            aws_account_id
                        )
                    ]
                }
            )

        user = self.context['request'].user
        name = validated_data.get('name')
        account = AwsAccount(
            account_arn=str(arn),
            aws_account_id=aws_account_id,
            name=name,
            user=user,
        )
        try:
            session = aws.get_session(str(arn))
        except ClientError as error:
            if error.response.get('Error', {}).get('Code') == 'AccessDenied':
                raise serializers.ValidationError(
                    detail={
                        'account_arn': [
                            _('Permission denied for ARN "{0}"').format(arn)
                        ]
                    }
                )
            raise
        account_verified, failed_actions = aws.verify_account_access(session)
        if account_verified:
            try:
                aws.configure_cloudtrail(session, aws_account_id)
            except ClientError as error:
                if error.response.get('Error', {}).get('Code') == \
                        'AccessDeniedException':
                    raise serializers.ValidationError(
                        detail={
                            'account_arn': [
                                _('Access denied to create CloudTrail for '
                                  'ARN "{0}"').format(arn)
                            ]
                        }
                    )
                raise
        else:
            failure_details = [_('Account verification failed.')]
            failure_details += [
                _('Access denied for policy action "{0}".').format(action)
                for action in failed_actions
            ]
            raise serializers.ValidationError(
                detail={
                    'account_arn': failure_details
                }
            )
        account.save()
        tasks.initial_aws_describe_instances.delay(account.id)
        return account

    def update(self, instance, validated_data):
        """Update the instance with the name from validated_data."""
        instance.name = validated_data.get('name', instance.name)
        instance.save()
        return instance

    def get_user_id(self, account):
        """Get the user_id property for serialization."""
        return account.user_id


class AccountPolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all account types."""

    model_serializer_mapping = {
        AwsAccount: AwsAccountSerializer,
    }


class AwsInstanceEventSerializer(HyperlinkedModelSerializer):
    """Serialize a customer AwsInstanceEvent for the API."""

    class Meta:
        model = AwsInstanceEvent
        fields = (
            'event_type',
            'id',
            'instance',
            'instance_id',
            'instance_type',
            'machineimage',
            'machineimage_id',
            'occurred_at',
            'subnet',
            'url',
        )
        read_only_fields = (
            'event_type',
            'id',
            'instance',
            'instance_id',
            'instance_type',
            'machineimage',
            'machineimage_id',
            'occurred_at',
            'subnet',
            'url',
        )
        extra_kwargs = {
            'url': {'view_name': 'instanceevent-detail', 'lookup_field': 'pk'},
        }

    def get_instance_id(self, event):
        """Get the instance_id property for serialization."""
        return event.instance_id

    def get_machineimage_id(self, event):
        """Get the machineimage_id property for serialization."""
        return event.machineimage_id


class InstanceEventPolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all instance event types."""

    model_serializer_mapping = {
        AwsInstanceEvent: AwsInstanceEventSerializer,
    }


class AwsMachineImageSerializer(HyperlinkedModelSerializer):
    """Serialize a customer AwsMachineImage for the API."""

    rhel_challenged = serializers.BooleanField(required=False)
    openshift_challenged = serializers.BooleanField(required=False)

    class Meta:
        model = AwsMachineImage
        fields = (
            'created_at',
            'ec2_ami_id',
            'id',
            'inspection_json',
            'is_cloud_access',
            'is_encrypted',
            'is_marketplace',
            'name',
            'openshift',
            'openshift_challenged',
            'openshift_detected',
            'owner_aws_account_id',
            'platform',
            'region',
            'rhel',
            'rhel_challenged',
            'rhel_detected',
            'rhel_enabled_repos_found',
            'rhel_product_certs_found',
            'rhel_release_files_found',
            'rhel_signed_packages_found',
            'status',
            'updated_at',
            'url',
        )
        read_only_fields = (
            'created_at',
            'ec2_ami_id',
            'id',
            'inspection_json',
            'is_cloud_access',
            'is_encrypted',
            'is_marketplace',
            'name',
            'openshift',
            'openshift_detected',
            'owner_aws_account_id',
            'platform',
            'region',
            'rhel',
            'rhel_detected',
            'rhel_enabled_repos_found',
            'rhel_product_certs_found',
            'rhel_release_files_found',
            'rhel_signed_packages_found',
            'status',
            'updated_at',
            'url',
        )
        extra_kwargs = {
            'url': {'view_name': 'machineimage-detail', 'lookup_field': 'pk'},
        }

    def update(self, image, validated_data):
        """
        Update the AwsMachineImage challenge properties.

        Args:
            image (AwsMachineImage: Image to be updated.
            validated_data (dict): Dictionary of properties to be updated.

        Returns (AwsMachineImage): Updated object.

        """
        rhel_challenged = validated_data.get('rhel_challenged', None)
        openshift_challenged = validated_data.get('openshift_challenged', None)

        if rhel_challenged is not None:
            image.rhel_challenged = rhel_challenged

        if openshift_challenged is not None:
            image.openshift_challenged = openshift_challenged

        if rhel_challenged is not None or openshift_challenged is not None:
            image.save()

        return image


class MachineImagePolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all image types."""

    model_serializer_mapping = {
        AwsMachineImage: AwsMachineImageSerializer,
    }


class AwsInstanceSerializer(HyperlinkedModelSerializer):
    """Serialize a customer AwsInstance for the API."""

    class Meta:
        model = AwsInstance
        fields = (
            'account',
            'account_id',
            'created_at',
            'ec2_instance_id',
            'id',
            'machineimage',
            'machineimage_id',
            'region',
            'updated_at',
            'url',
        )
        read_only_fields = (
            'account',
            'account_id',
            'created_at',
            'ec2_instance_id',
            'id',
            'machineimage',
            'machineimage_id',
            'region',
            'updated_at',
            'url',
        )
        extra_kwargs = {
            'url': {'view_name': 'instance-detail', 'lookup_field': 'pk'},
        }

    def get_account_id(self, instance):
        """Get the account_id property for serialization."""
        return instance.account_id


class InstancePolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all instance types."""

    model_serializer_mapping = {
        AwsInstance: AwsInstanceSerializer,
    }


class CloudAccountOverviewSerializer(Serializer):
    """Serialize the cloud accounts overviews for the API."""

    user_id = serializers.IntegerField(required=False)
    start = serializers.DateTimeField(default_timezone=tz.tzutc())
    end = serializers.DateTimeField(default_timezone=tz.tzutc())
    name_pattern = serializers.CharField(required=False)
    account_id = serializers.IntegerField(required=False)

    def validate(self, data):
        """Validate that the end date is after the start date."""
        if data['start'] > data['end']:
            raise serializers.ValidationError(
                'End date must be after start date.'
            )
        return data

    def generate(self):
        """Generate the cloud accounts overviews and return the results."""
        start = misc.truncate_date(self.validated_data['start'])
        end = misc.truncate_date(self.validated_data['end'])
        name_pattern = self.validated_data.get('name_pattern', None)

        user = self.context['request'].user
        user_id = user.id
        account_id = self.validated_data.get('account_id', None)

        if user.is_superuser:
            user_id = self.validated_data.get('user_id', user.id)

        return reports.get_account_overviews(user_id, start, end,
                                             name_pattern, account_id)


class DailyInstanceActivitySerializer(Serializer):
    """Serialize a report of daily instance activity over time for the API."""

    user_id = serializers.IntegerField(required=False)
    start = serializers.DateTimeField(default_timezone=tz.tzutc())
    end = serializers.DateTimeField(default_timezone=tz.tzutc())
    name_pattern = serializers.CharField(required=False)
    account_id = serializers.IntegerField(required=False)

    def validate(self, data):
        """Validate that the end date is after the start date."""
        if data['start'] > data['end']:
            raise serializers.ValidationError(
                'End date must be after start date.'
            )
        return data

    def generate(self):
        """Generate the usage report and return the results."""
        start = misc.truncate_date(self.validated_data['start'])
        end = misc.truncate_date(self.validated_data['end'])
        name_pattern = self.validated_data.get('name_pattern', None)

        user = self.context['request'].user
        user_id = user.id
        account_id = self.validated_data.get('account_id', None)

        if user.is_superuser:
            user_id = self.validated_data.get('user_id', user.id)

        return reports.get_daily_usage(user_id, start, end,
                                       name_pattern, account_id)


class CloudAccountImagesSerializer(Serializer):
    """Serialize the cloud machine images with usage over time for the API."""

    user_id = serializers.IntegerField(required=False)
    start = serializers.DateTimeField(default_timezone=tz.tzutc())
    end = serializers.DateTimeField(default_timezone=tz.tzutc())
    account_id = serializers.IntegerField(required=True)

    def validate(self, data):
        """Validate that the end date is after the start date."""
        if data['start'] > data['end']:
            raise serializers.ValidationError(
                'End date must be after start date.'
            )
        return data

    def generate(self):
        """Generate the usage report and return the results."""
        start = misc.truncate_date(self.validated_data['start'])
        end = misc.truncate_date(self.validated_data['end'])

        user = self.context['request'].user
        user_id = user.id
        account_id = self.validated_data.get('account_id', None)

        if user.is_superuser:
            user_id = self.validated_data.get('user_id', user.id)

        return reports.get_images_overviews(user_id, start, end, account_id)


class UserSerializer(Serializer):
    """Serialize a user."""

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    accounts = serializers.IntegerField(read_only=True)
    challenged_images = serializers.IntegerField(read_only=True)
