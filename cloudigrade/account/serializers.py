"""DRF API serializers for the account app."""
import logging

from botocore.exceptions import ClientError
from dateutil import tz
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.serializers import HyperlinkedModelSerializer, Serializer
from rest_polymorphic.serializers import PolymorphicSerializer

import account
from account import reports
from account.models import (AwsAccount,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage)
from account.tasks import copy_ami_snapshot
from account.util import (create_initial_aws_instance_events,
                          create_new_machine_images,
                          generate_aws_ami_messages)
from account.validators import validate_cloud_provider_account_id
from util import aws

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
        account = AwsAccount(
            account_arn=str(arn),
            aws_account_id=aws_account_id,
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
                                    _('Permission denied for ARN '
                                      '"{0}"').format(arn)
                                ]
                            }
                        )
                    raise
                new_amis = create_new_machine_images(account, instances_data)
                create_initial_aws_instance_events(account, instances_data)
            messages = generate_aws_ami_messages(instances_data, new_amis)
            for message in messages:
                image = AwsMachineImage.objects.get(
                    ec2_ami_id=message['image_id'])
                image.status = image.PREPARING
                image.save()
                copy_ami_snapshot.delay(
                    str(arn),
                    message['image_id'],
                    message['region']
                )
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
            'ec2_ami_id',
            'instance_type',
            'event_type',
            'occurred_at'
        )
        read_only_fields = (
            'instance',
            'id',
            'subnet',
            'ec2_ami_id',
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

    class Meta:
        model = AwsMachineImage
        fields = (
            'id',
            'created_at',
            'updated_at',
            'account',
            'is_encrypted',
            'ec2_ami_id',
            'status'
        )
        read_only_fields = (
            'id',
            'created_at',
            'updated_at',
            'account',
            'is_encrypted',
            'ec2_ami_id',
            'status'
        )
        extra_kwargs = {
            'url': {'view_name': 'image-detail', 'lookup_field': 'pk'},
        }


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


class ReportSerializer(Serializer):
    """Serialize a usage report for the API."""

    cloud_provider = serializers.ChoiceField(choices=account.CLOUD_PROVIDERS)
    cloud_account_id = serializers.CharField()

    start = serializers.DateTimeField(default_timezone=tz.tzutc())
    end = serializers.DateTimeField(default_timezone=tz.tzutc())

    class Meta:
        validators = [validate_cloud_provider_account_id]

    def generate(self):
        """Generate the usage report and return the results."""
        return reports.get_time_usage(**self.validated_data)
