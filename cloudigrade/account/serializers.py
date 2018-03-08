"""DRF API serializers for the account app."""
import logging

from dateutil import tz
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers

from account import reports
from account.models import Account
from account.util import create_initial_instance_events
from util import aws

logger = logging.getLogger(__name__)


class AccountSerializer(serializers.HyperlinkedModelSerializer):
    """Serialize a customer Account for the API."""

    class Meta:
        model = Account
        fields = ('id', 'url', 'account_id', 'account_arn')
        read_only_fields = ('account_id', )

    def create(self, validated_data):
        """Create an Account."""
        arn = validated_data['account_arn']
        account_id = aws.extract_account_id_from_arn(arn)
        account = Account(
            account_arn=arn,
            account_id=account_id
        )
        session = aws.get_session(arn)
        if aws.verify_account_access(session):
            instances_data = aws.get_running_instances(session)
            with transaction.atomic():
                account.save()
                create_initial_instance_events(account, instances_data)
        else:
            raise serializers.ValidationError(
                _('Account verification failed. ARN Info Not Stored')
            )
        return account


class ReportSerializer(serializers.Serializer):
    """Serialize a usage report for the API."""

    account_id = serializers.DecimalField(max_digits=12, decimal_places=0)
    start = serializers.DateTimeField(default_timezone=tz.tzutc())
    end = serializers.DateTimeField(default_timezone=tz.tzutc())

    def create(self):
        """Create the usage report and return the results."""
        validated_data = self.validated_data
        account_id = validated_data['account_id']
        start = validated_data['start']
        end = validated_data['end']

        results = reports.get_hourly_usage(
            start=start,
            end=end,
            account_id=account_id
        )
        return results
