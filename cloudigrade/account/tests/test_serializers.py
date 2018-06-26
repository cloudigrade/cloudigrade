"""Collection of tests for custom DRF serializers in the account app."""
import random
from unittest.mock import MagicMock, Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

import account.serializers as account_serializers
from account import AWS_PROVIDER_STRING, reports
from account.models import (AwsAccount, AwsInstance, AwsMachineImage,
                            InstanceEvent)
from account.serializers import AwsAccountSerializer, ReportSerializer, aws
from account.tests import helper as account_helper
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

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'get_running_instances') as mock_get_run, \
                patch.object(account_serializers,
                             'copy_ami_snapshot') as mock_copy_snapshot:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_get_run.return_value = running_instances
            mock_copy_snapshot.return_value = None
            serializer = AwsAccountSerializer(context=context)

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

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        failed_actions = ['foo', 'bar']

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = False, failed_actions
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(serializers.ValidationError) as cm:
                serializer.create(validated_data)

            exception = cm.exception
            self.assertIn('account_arn', exception.detail)
            for index in range(len(failed_actions)):
                self.assertIn(failed_actions[index],
                              exception.detail['account_arn'][index + 1])

    def test_create_fails_when_arn_access_denied(self):
        """Test that an account is not saved if ARN access is denied."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        validated_data = {
            'account_arn': arn,
        }

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDenied'}},
            operation_name=Mock(),
        )

        with patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.side_effect = client_error
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertIn('account_arn', raised_exception.detail)
            self.assertIn(arn, raised_exception.detail['account_arn'][0])

    def test_create_fails_when_cloudtrail_fails(self):
        """Test that an account is not saved if cloudtrails errors."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()

        validated_data = {
            'account_arn': arn,
        }

        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDeniedException'}},
            operation_name=Mock(),
        )

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'configure_cloudtrail') as mock_cloudtrail:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_cloudtrail.side_effect = client_error
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertIn('account_arn', raised_exception.detail)
            self.assertIn(arn, raised_exception.detail['account_arn'][0])

    def test_create_fails_when_assume_role_fails_unexpectedly(self):
        """Test that account is not saved if assume_role fails unexpectedly."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        validated_data = {
            'account_arn': arn,
        }

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        client_error = ClientError(
            error_response=MagicMock(),
            operation_name=Mock(),
        )

        with patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.side_effect = client_error
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ClientError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertEqual(raised_exception, client_error)

    def test_create_fails_when_another_arn_has_same_aws_account_id(self):
        """Test that an account is not saved if ARN reuses an AWS account."""
        user = util_helper.generate_test_user()
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

        # Create one with the same AWS account ID but a different ARN.
        account_helper.generate_aws_account(
            aws_account_id=aws_account_id,
            user=user,
        )

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'get_running_instances') as mock_get_run, \
                patch.object(account_serializers,
                             'copy_ami_snapshot') as mock_copy_snapshot:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_get_run.return_value = running_instances
            mock_copy_snapshot.return_value = None
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertIn('account_arn', raised_exception.detail)
            self.assertIn(aws_account_id,
                          raised_exception.detail['account_arn'][0])


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
