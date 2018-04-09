"""Collection of tests for custom DRF serializers in the account app."""
import random
from unittest.mock import patch

from django.test import TestCase
from django.utils.translation import gettext as _
from rest_framework import serializers

import account.serializers as account_serializers
from account import AWS_PROVIDER_STRING, reports
from account.models import (AwsAccount, AwsInstance, AwsMachineImage,
                            InstanceEvent)
from account.serializers import AwsAccountSerializer, ReportSerializer, aws
from util.tests import helper as util_helper


class AwsAccountSerializerTest(TestCase):
    """AwsAccount serializer test case."""

    def test_create_succeeds_when_account_verified(self):
        """Test saving and processing of a test ARN."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        running_instances = {
            region: [
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.running
                ),
                util_helper.generate_dummy_describe_instance(
                    state=aws.InstanceState.stopping
                )
            ]
        }

        validated_data = {
            'account_arn': arn,
        }

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws, 'boto3') as mock_boto3, \
                patch.object(aws, 'get_running_instances') as mock_get_run, \
                patch.object(account_serializers,
                             'copy_ami_snapshot') as mock_copy_snapshot:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True
            mock_get_run.return_value = running_instances
            mock_copy_snapshot.return_value = None
            serializer = AwsAccountSerializer()

            result = serializer.create(validated_data)
            self.assertIsInstance(result, AwsAccount)

        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        self.assertEqual(aws_account_id, account.aws_account_id)
        self.assertEqual(arn, account.account_arn)

        instances = AwsInstance.objects.filter(account=account).all()
        self.assertEqual(len(running_instances[region]), len(instances))
        for region, mock_instances_list in running_instances.items():
            for mock_instance in mock_instances_list:
                instance_id = mock_instance['InstanceId']
                instance = AwsInstance.objects.get(ec2_instance_id=instance_id)
                self.assertIsInstance(instance, AwsInstance)
                self.assertEqual(region, instance.region)
                event = InstanceEvent.objects.get(instance=instance)
                self.assertIsInstance(event, InstanceEvent)
                self.assertEqual(InstanceEvent.TYPE.power_on, event.event_type)

        amis = AwsMachineImage.objects.filter(account=account).all()
        self.assertEqual(len(running_instances[region]), len(amis))

    def test_create_fails_when_account_not_verified(self):
        """Test that an account is not saved if verification fails."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()
        validated_data = {
            'account_arn': arn,
        }

        expected_detail = _(
            'AwsAccount verification failed. ARN Info Not Stored'
        )

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = False
            serializer = AwsAccountSerializer()

            with self.assertRaises(serializers.ValidationError) as cm:
                serializer.create(validated_data)

            the_exception = cm.exception
            self.assertEqual(the_exception.detail, [expected_detail])


class ReportSerializerTest(TestCase):
    """Report serializer test case."""

    def test_report_with_timezones_specified(self):
        """Test that start/end dates with timezones shift correctly to UTC."""
        cloud_provider = AWS_PROVIDER_STRING
        cloud_account_id = util_helper.generate_dummy_aws_account_id()
        start_no_tz = '2018-01-01T00:00:00-05'
        end_no_tz = '2018-02-01T00:00:00+04'
        request_data = {
            'cloud_provider': cloud_provider,
            'cloud_account_id': str(cloud_account_id),
            'start': start_no_tz,
            'end': end_no_tz,
        }
        expected_start = util_helper.utc_dt(2018, 1, 1, 5, 0)
        expected_end = util_helper.utc_dt(2018, 1, 31, 20, 0)

        with patch.object(reports, 'get_time_usage') as mock_get_hourly:
            serializer = ReportSerializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            results = serializer.generate()
            mock_get_hourly.assert_called_with(
                cloud_provider=cloud_provider,
                cloud_account_id=cloud_account_id,
                start=expected_start,
                end=expected_end
            )
            self.assertEqual(results, mock_get_hourly.return_value)

    def test_report_without_timezones_specified(self):
        """Test that UTC is used if timezones are missing from start/end."""
        cloud_provider = AWS_PROVIDER_STRING
        cloud_account_id = util_helper.generate_dummy_aws_account_id()
        start_no_tz = '2018-01-01T00:00:00'
        end_no_tz = '2018-02-01T00:00:00'
        mock_request_data = {
            'cloud_provider': cloud_provider,
            'cloud_account_id': str(cloud_account_id),
            'start': start_no_tz,
            'end': end_no_tz,
        }
        expected_start = util_helper.utc_dt(2018, 1, 1, 0, 0)
        expected_end = util_helper.utc_dt(2018, 2, 1, 0, 0)

        with patch.object(reports, 'get_time_usage') as mock_get_hourly:
            serializer = ReportSerializer(data=mock_request_data)
            serializer.is_valid(raise_exception=True)
            results = serializer.generate()
            mock_get_hourly.assert_called_with(
                cloud_provider=cloud_provider,
                cloud_account_id=cloud_account_id,
                start=expected_start,
                end=expected_end
            )
            self.assertEqual(results, mock_get_hourly.return_value)
