"""Collection of tests for custom DRF serializers in the account app."""
import uuid
from unittest.mock import patch

from django.test import TestCase
from django.utils.translation import gettext as _
from rest_framework import serializers

from account.models import Account, Instance, InstanceEvent
from account.serializers import AccountSerializer, ReportSerializer, reports, \
    aws
from util.tests import helper


class AccountSerializerTest(TestCase):
    """Account serializer test case."""

    def test_create_succeeds_when_account_verified(self):
        """Test saving and processing of a test ARN."""
        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(mock_account_id)
        mock_role = helper.generate_dummy_role()
        mock_region = f'region-{uuid.uuid4()}'
        mock_instances = {mock_region: [
            helper.generate_dummy_describe_instance(
                state=aws.InstanceState.running
            ),
            helper.generate_dummy_describe_instance(
                state=aws.InstanceState.stopping
            )
        ]}
        mock_validated_data = {
            'account_arn': mock_arn,
        }

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws, 'boto3') as mock_boto3, \
                patch.object(aws, 'get_running_instances') as mock_get_running:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role
            mock_verify.return_value = True
            mock_get_running.return_value = mock_instances
            serializer = AccountSerializer()

            result = serializer.create(mock_validated_data)
            self.assertIsInstance(result, Account)

        account = Account.objects.get(account_id=mock_account_id)
        self.assertEqual(mock_account_id, account.account_id)
        self.assertEqual(mock_arn, account.account_arn)

        instances = Instance.objects.filter(account=account).all()
        self.assertEqual(len(mock_instances[mock_region]), len(instances))
        for region, mock_instances_list in mock_instances.items():
            for mock_instance in mock_instances_list:
                instance_id = mock_instance['InstanceId']
                instance = Instance.objects.get(ec2_instance_id=instance_id)
                self.assertIsInstance(instance, Instance)
                self.assertEqual(region, instance.region)
                event = InstanceEvent.objects.get(instance=instance)
                self.assertIsInstance(event, InstanceEvent)
                self.assertEqual(InstanceEvent.TYPE.power_on, event.event_type)

    def test_create_fails_when_account_not_verified(self):
        """Test that an account is not saved if verification fails."""
        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(mock_account_id)
        mock_role = helper.generate_dummy_role()
        mock_validated_data = {
            'account_arn': mock_arn,
        }

        expected_detail = _('Account verification failed. ARN Info Not Stored')

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role
            mock_verify.return_value = False
            serializer = AccountSerializer()

            with self.assertRaises(serializers.ValidationError) as cm:
                serializer.create(mock_validated_data)

            the_exception = cm.exception
            self.assertEqual(the_exception.detail, [expected_detail])


class ReportSerializerTest(TestCase):
    """Report serializer test case."""

    def test_report_with_timezones_specified(self):
        """Test that start/end dates with timezones shift correctly to UTC."""
        account_id = helper.generate_dummy_aws_account_id()
        start_no_tz = '2018-01-01T00:00:00-05'
        end_no_tz = '2018-02-01T00:00:00+04'
        mock_request_data = {
            'account_id': account_id,
            'start': start_no_tz,
            'end': end_no_tz,
        }
        expected_start = helper.utc_dt(2018, 1, 1, 5, 0)
        expected_end = helper.utc_dt(2018, 1, 31, 20, 0)

        with patch.object(reports, 'get_hourly_usage') as mock_get_hourly:
            serializer = ReportSerializer(data=mock_request_data)
            serializer.is_valid(raise_exception=True)
            results = serializer.create()
            mock_get_hourly.assert_called_with(
                account_id=account_id,
                start=expected_start,
                end=expected_end
            )
            self.assertEqual(results, mock_get_hourly.return_value)

    def test_report_without_timezones_specified(self):
        """Test that UTC is used if timezones are missing from start/end."""
        account_id = helper.generate_dummy_aws_account_id()
        start_no_tz = '2018-01-01T00:00:00'
        end_no_tz = '2018-02-01T00:00:00'
        mock_request_data = {
            'account_id': account_id,
            'start': start_no_tz,
            'end': end_no_tz,
        }
        expected_start = helper.utc_dt(2018, 1, 1, 0, 0)
        expected_end = helper.utc_dt(2018, 2, 1, 0, 0)

        with patch.object(reports, 'get_hourly_usage') as mock_get_hourly:
            serializer = ReportSerializer(data=mock_request_data)
            serializer.is_valid(raise_exception=True)
            results = serializer.create()
            mock_get_hourly.assert_called_with(
                account_id=account_id,
                start=expected_start,
                end=expected_end
            )
            self.assertEqual(results, mock_get_hourly.return_value)
