"""DRF API serializers for the account app v2."""
from datetime import datetime, timedelta

from botocore.exceptions import ClientError
from django.db.transaction import on_commit
from django.utils.translation import gettext as _
from generic_relations.relations import GenericRelatedField
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import (BooleanField, CharField,
                                   ChoiceField, Field, IntegerField)
from rest_framework.serializers import ModelSerializer, Serializer

from api import CLOUD_PROVIDERS, tasks
from api.models import (AwsCloudAccount, AwsInstance,
                        AwsMachineImage, CloudAccount, Instance,
                        MachineImage)
from api.util import max_concurrent_usage
from util import aws
from util.exceptions import InvalidArn


class AwsCloudAccountSerializer(ModelSerializer):
    """Serialize a customer AWS CloudAccount for API v2."""

    aws_cloud_account_id = IntegerField(source='id', read_only=True)

    class Meta:
        model = AwsCloudAccount
        fields = (
            'account_arn',
            'aws_account_id',
            'aws_cloud_account_id',
            'created_at',
            'updated_at',
        )


class CloudAccountSerializer(ModelSerializer):
    """Serialize a customer CloudAccount for API v2."""

    account_arn = CharField(required=False)
    account_id = IntegerField(source='id', read_only=True)
    aws_account_id = CharField(required=False)

    cloud_type = ChoiceField(
        choices=CLOUD_PROVIDERS,
        required=True
    )
    content_object = GenericRelatedField({
        AwsCloudAccount: AwsCloudAccountSerializer(),
    }, required=False)

    class Meta:
        model = CloudAccount
        fields = (
            'account_id',
            'created_at',
            'name',
            'updated_at',
            'user_id',
            'content_object',
            'cloud_type',
            'account_arn',
            'aws_account_id',
        )
        read_only_fields = (
            'aws_account_id',
            'user_id',
            'content_object',
        )
        create_only_fields = ('cloud_type', )

    def validate(self, data):
        """
        Validate conditions across multiple fields.

        - name must be unique per user
        """
        user = self.context['request'].user
        name = data.get('name')

        try:
            CloudAccount.objects.get(user=user, name=name)
        except CloudAccount.DoesNotExist:
            return data

        raise ValidationError(_(
            "Account with name '{0}' for account "
            "number '{1}' already exists").format(name, user.username))

    def validate_account_arn(self, value):
        """Validate the input account_arn."""
        if self.instance is not None and value != \
                self.instance.content_object.account_arn:
            raise ValidationError(
                _('You cannot update account_arn.')
            )
        try:
            aws.AwsArn(value)
        except InvalidArn:
            raise ValidationError(
                _('Invalid ARN.')
            )
        return value

    def create(self, validated_data):
        """
        Create a CloudAccount.

        Validates:
            - account_arn must not be None if cloud_type is aws
        """
        cloud_type = validated_data['cloud_type']

        if cloud_type == 'aws':
            account_arn = validated_data.get('account_arn')
            if account_arn is None:
                raise ValidationError(
                    {'account_arn': Field.default_error_messages['required']},
                    'required',
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
                    errors[field] = [
                        _('You cannot update field {}.').format(field)
                    ]
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
        arn = aws.AwsArn(validated_data['account_arn'])
        aws_account_id = arn.account_id

        account_exists = AwsCloudAccount.objects.filter(
            aws_account_id=aws_account_id
        ).exists()
        if account_exists:
            raise ValidationError(
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
        aws_cloud_account = AwsCloudAccount(
            account_arn=str(arn),
            aws_account_id=aws_account_id,
        )

        try:
            session = aws.get_session(str(arn))
        except ClientError as error:
            if error.response.get('Error', {}).get('Code') == 'AccessDenied':
                raise ValidationError(
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
                    raise ValidationError(
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
            raise ValidationError(
                detail={
                    'account_arn': failure_details
                }
            )
        aws_cloud_account.save()
        cloud_account = CloudAccount(
            name=name,
            user=user,
            content_object=aws_cloud_account
        )
        cloud_account.save()
        on_commit(lambda:
                  tasks.initial_aws_describe_instances.delay(
                      aws_cloud_account.id)
                  )
        return cloud_account


class AwsMachineImageSerializer(ModelSerializer):
    """Serialize a customer AwsMachineImage for API v2."""

    aws_image_id = IntegerField(source='id', read_only=True)

    class Meta:
        model = AwsMachineImage
        fields = (
            'aws_image_id',
            'created_at',
            'ec2_ami_id',
            'id',
            'owner_aws_account_id',
            'platform',
            'region',
            'updated_at',
            'is_cloud_access',
            'is_marketplace',
        )
        read_only_fields = (
            'created_at',
            'ec2_ami_id',
            'id',
            'owner_aws_account_id',
            'platform',
            'region',
            'updated_at',
            'is_cloud_access',
            'is_marketplace',
        )

    def create(self, validated_data):
        """Create an AwsMachineImage."""
        raise NotImplementedError

    def update(self, instance, validated_data):
        """Update an AwsMachineImage."""
        raise NotImplementedError


class MachineImageSerializer(ModelSerializer):
    """Serialize a customer AwsMachineImage for API v2."""

    cloud_type = ChoiceField(
        choices=['aws'],
        required=False
    )
    content_object = GenericRelatedField({
        AwsMachineImage: AwsMachineImageSerializer(),
    }, required=False)

    image_id = IntegerField(source='id', read_only=True)

    rhel_challenged = BooleanField(required=False)
    openshift_challenged = BooleanField(required=False)

    class Meta:
        model = MachineImage
        fields = (
            'created_at',
            'image_id',
            'inspection_json',
            'is_encrypted',
            'name',
            'openshift',
            'openshift_challenged',
            'openshift_detected',
            'rhel',
            'rhel_challenged',
            'rhel_detected',
            'rhel_enabled_repos_found',
            'rhel_product_certs_found',
            'rhel_release_files_found',
            'rhel_signed_packages_found',
            'status',
            'updated_at',
            'cloud_type',
            'content_object',
        )
        read_only_fields = (
            'created_at',
            'id',
            'inspection_json',
            'is_encrypted',
            'name',
            'openshift',
            'openshift_detected',
            'rhel',
            'rhel_detected',
            'rhel_enabled_repos_found',
            'rhel_product_certs_found',
            'rhel_release_files_found',
            'rhel_signed_packages_found',
            'status',
            'updated_at',
            'cloud_type',
        )

    def update(self, image, validated_data):
        """
        Update the AwsMachineImage challenge properties.

        Args:
            image (MachineImage): Image to be updated.
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


class AwsInstanceSerializer(ModelSerializer):
    """Serialize a customer AwsInstance for API v2."""

    aws_instance_id = IntegerField(source='id', read_only=True)

    class Meta:
        model = AwsInstance
        fields = (
            'aws_instance_id',
            'created_at',
            'ec2_instance_id',
            'region',
            'updated_at',
        )
        read_only_fields = (
            'account',
            'created_at',
            'ec2_instance_id',
            'id',
            'region',
            'updated_at',
        )

    def create(self, validated_data):
        """Create a AwsInstance."""
        raise NotImplementedError

    def update(self, instance, validated_data):
        """Update a AwsInstance."""
        raise NotImplementedError


class InstanceSerializer(ModelSerializer):
    """Serialize a customer AwsInstance for API v2."""

    cloud_type = ChoiceField(
        choices=['aws'],
        required=False
    )
    content_object = GenericRelatedField({
        AwsInstance: AwsInstanceSerializer(),
    }, required=False)
    instance_id = IntegerField(source='id', read_only=True)

    class Meta:
        model = Instance
        fields = (
            'cloud_account_id',
            'created_at',
            'instance_id',
            'machine_image_id',
            'updated_at',
            'cloud_type',
            'content_object',
        )
        read_only_fields = (
            'cloud_account_id',
            'created_at',
            'id',
            'machine_image_id',
            'updated_at',
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
        self,
        start_date=None,
        end_date=None,
        user_id=None,
        cloud_account_id=None,
    ):
        """Initialize parameters."""
        self.start_date = start_date
        self.end_date = end_date
        self.user_id = user_id
        self.cloud_account_id = cloud_account_id
        self._days = None

    @property
    def days(self):
        """Get all days."""
        if self._days is None:
            tomorrow = datetime.utcnow().date() + timedelta(days=1)
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
        for day in days:
            result = max_concurrent_usage(
                day, self.user_id, self.cloud_account_id
            )
            results.append(result)

        return results


class DailyConcurrentUsageSerializer(Serializer):
    """Serialize a report of daily RHEL concurrency over time for the API."""

    date = serializers.DateField(required=True)
    instances = serializers.IntegerField(required=True)
    vcpu = serializers.FloatField(required=True)
    memory = serializers.FloatField(required=True)
