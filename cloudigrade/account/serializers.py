"""DRF API serializers for the account app."""
import logging

from dateutil import tz
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.serializers import HyperlinkedModelSerializer, Serializer
from rest_polymorphic.serializers import PolymorphicSerializer

import account
from account import reports
from account.models import AwsAccount
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
        )
        read_only_fields = ('aws_account_id',)
        extra_kwargs = {
            'url': {'view_name': 'account-detail', 'lookup_field': 'pk'},
        }

    def create(self, validated_data):
        """Create an AwsAccount."""
        arn = aws.AwsArn(validated_data['account_arn'])
        aws_account_id = arn.account_id
        user = self.context['request'].user
        account = AwsAccount(
            account_arn=str(arn),
            aws_account_id=aws_account_id,
            user=user,
        )
        session = aws.get_session(str(arn))
        if aws.verify_account_access(session):
            instances_data = aws.get_running_instances(session)
            with transaction.atomic():
                account.save()
                new_amis = create_new_machine_images(account, instances_data)
                create_initial_aws_instance_events(account, instances_data)
            messages = generate_aws_ami_messages(instances_data, new_amis)
            for message in messages:
                copy_ami_snapshot.delay(
                    str(arn),
                    message['image_id'],
                    message['region']
                )
        else:
            raise serializers.ValidationError(
                _('AwsAccount verification failed. ARN Info Not Stored')
            )
        return account


class AccountPolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all account types."""

    model_serializer_mapping = {
        AwsAccount: AwsAccountSerializer,
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
