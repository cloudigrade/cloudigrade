"""DRF API serializers for the account app."""
import logging

from dateutil import tz
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.reverse import reverse

import account
from account import reports
from account.models import Account, AwsAccount
from account.util import create_initial_aws_instance_events
from account.validators import validate_cloud_provider_account_id
from util import aws

logger = logging.getLogger(__name__)


class AccountSerializer(serializers.HyperlinkedModelSerializer):
    """
    Serialize a customer Account for the API.

    The serialized response includes a special "detail" field that links
    to the cloud provider specific account.
    """

    class Meta:
        model = Account
        fields = (
            'created_at',
            'detail',
            'id',
            'updated_at',
            'url',
        )

    detail = serializers.SerializerMethodField()

    def get_detail(self, obj):
        """Link to child account model for more detail."""
        request = self.context.get('request', None)
        if hasattr(obj, 'awsaccount'):
            return reverse(
                'awsaccount-detail', args=[obj.awsaccount.id], request=request
            )
        return None


class AwsAccountSerializer(serializers.HyperlinkedModelSerializer):
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

    def create(self, validated_data):
        """Create an AwsAccount."""
        arn = validated_data['account_arn']
        aws_account_id = aws.extract_account_id_from_arn(arn)
        account = AwsAccount(account_arn=arn, aws_account_id=aws_account_id)
        session = aws.get_session(arn)
        if aws.verify_account_access(session):
            instances_data = aws.get_running_instances(session)
            with transaction.atomic():
                account.save()
                create_initial_aws_instance_events(account, instances_data)
        else:
            raise serializers.ValidationError(
                _('AwsAccount verification failed. ARN Info Not Stored')
            )
        return account


class ReportSerializer(serializers.Serializer):
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
