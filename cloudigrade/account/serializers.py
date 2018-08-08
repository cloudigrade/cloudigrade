"""DRF API serializers for the account app."""
import logging

from botocore.exceptions import ClientError
from dateutil import tz
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.serializers import (HyperlinkedModelSerializer,
                                        Serializer)
from rest_polymorphic.serializers import PolymorphicSerializer

from account import reports
from account.models import (AwsAccount,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage)
from account.util import (create_initial_aws_instance_events,
                          create_new_machine_images,
                          generate_aws_ami_messages,
                          start_image_inspection)
from account.validators import in_the_past
from util import aws
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

        account = AwsAccount.objects.filter(
            aws_account_id=aws_account_id
        ).first()
        if account is not None:
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
            instances_data = aws.get_running_instances(session)
            with transaction.atomic():
                account.save()
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
                new_amis = create_new_machine_images(account, instances_data)
                create_initial_aws_instance_events(account, instances_data)
            messages = generate_aws_ami_messages(instances_data, new_amis)
            for message in messages:
                image = start_image_inspection(
                    str(arn), message['image_id'], message['region'])
                self.add_ami_metadata(session,
                                      message['image_id'],
                                      message['region'],
                                      image)
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
        return account

    def update(self, instance, validated_data):
        """Update the instance with the name from validated_data."""
        instance.name = validated_data.get('name', instance.name)
        instance.save()
        return instance

    def add_ami_metadata(self, session, ami_id, ami_region, image):
        """
        Update our MachineImage with various AWS AMI metadata.

        This includes:
        - Set openshift detected bool if the AWS AMI is tagged for it.
        - Set name string if the AWS AMI has a name set.

        Args:
            session (boto3.session.Session): Session using customer
                ARN.
            ami_id (str): AWS AMI id.
            ami_region (str): AMS AMI region.
            image (MachineImage): MachineImage instance to be tagged.

        Returns:
            None

        """
        ec2_image = aws.get_ami(session, ami_id, ami_region)
        dirty = False

        if ec2_image.name:
            image.name = ec2_image.name
            dirty = True

        if ec2_image.tags is not None:
            has_openshift = 'cloudigrade-ocp-present' in [
                tags['Key'] for tags in ec2_image.tags]
            if has_openshift:
                image.openshift_detected = True
                dirty = True

        if dirty:
            image.save()

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
            'instance',
            'id',
            'subnet',
            'machineimage',
            'instance_type',
            'event_type',
            'occurred_at'
        )
        read_only_fields = (
            'instance',
            'id',
            'subnet',
            'machineimage',
            'instance_type',
            'event_type',
            'occurred_at'
        )
        extra_kwargs = {
            'url': {'view_name': 'event-detail', 'lookup_field': 'pk'},
        }


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
            'id',
            'created_at',
            'updated_at',
            'account',
            'is_encrypted',
            'ec2_ami_id',
            'status',
            'rhel',
            'rhel_detected',
            'rhel_challenged',
            'openshift',
            'openshift_detected',
            'openshift_challenged',
        )
        read_only_fields = (
            'id',
            'created_at',
            'updated_at',
            'account',
            'is_encrypted',
            'ec2_ami_id',
            'status',
            'rhel',
            'rhel_detected',
            'openshift',
            'openshift_detected',
        )
        extra_kwargs = {
            'url': {'view_name': 'image-detail', 'lookup_field': 'pk'},
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

        if (rhel_challenged or openshift_challenged) is not None:
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
            'id',
            'created_at',
            'updated_at',
            'url',
            'ec2_instance_id',
            'region'
        )
        read_only_fields = (
            'account',
            'id',
            'created_at',
            'updated_at',
            'url',
            'ec2_instance_id',
            'region'
        )
        extra_kwargs = {
            'url': {'view_name': 'instance-detail', 'lookup_field': 'pk'},
        }


class InstancePolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all instance types."""

    model_serializer_mapping = {
        AwsInstance: AwsInstanceSerializer,
    }


class CloudAccountOverviewSerializer(Serializer):
    """Serialize the cloud accounts overviews for the API."""

    user_id = serializers.IntegerField(required=False)
    start = serializers.DateTimeField(default_timezone=tz.tzutc())
    end = serializers.DateTimeField(default_timezone=tz.tzutc(),
                                    validators=[in_the_past])
    name_pattern = serializers.CharField(required=False)
    account_id = serializers.IntegerField(required=False)

    def generate(self):
        """Generate the cloud accounts overviews and return the results."""
        start = self.validated_data['start']
        end = self.validated_data['end']
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
    end = serializers.DateTimeField(default_timezone=tz.tzutc(),
                                    validators=[in_the_past])
    name_pattern = serializers.CharField(required=False)
    account_id = serializers.IntegerField(required=False)

    def generate(self):
        """Generate the usage report and return the results."""
        start = self.validated_data['start']
        end = self.validated_data['end']
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
    end = serializers.DateTimeField(default_timezone=tz.tzutc(),
                                    validators=[in_the_past])
    account_id = serializers.IntegerField(required=True)

    def generate(self):
        """Generate the usage report and return the results."""
        start = self.validated_data['start']
        end = self.validated_data['end']

        user = self.context['request'].user
        user_id = user.id
        account_id = self.validated_data.get('account_id', None)

        if user.is_superuser:
            user_id = self.validated_data.get('user_id', user.id)

        return reports.get_images_overviews(user_id, start, end, account_id)


class UserSerializer(Serializer):
    """Serialize a user."""

    id = serializers.CharField(read_only=True)
    username = serializers.CharField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
