"""Collection of tests for custom DRF serializers in the account app."""
import random
from unittest.mock import MagicMock, Mock, patch

import faker
from botocore.exceptions import ClientError
from django.test import TestCase
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from account.models import (AwsAccount,
                            AwsInstance,
                            AwsMachineImage)
from account.serializers import (AwsAccountSerializer,
                                 AwsMachineImageSerializer,
                                 aws,)
from account.tests import helper as account_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class AwsAccountSerializerTest(TestCase):
    """AwsAccount serializer test case."""

    @patch('account.serializers.tasks')
    def test_create_succeeds_when_account_verified(self, mock_tasks):
        """
        Test saving and processing of a test ARN.

        This is a somewhat comprehensive test that includes finding two
        instances upon initial account discovery. Both instances should get a
        "power on" event. The images for these instances both have random names
        and are owned by other random account IDs. One image has OpenShift.
        """
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(aws_account_id)
        role = util_helper.generate_dummy_role()
        validated_data = {
            'account_arn': arn,
        }

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        mock_ami = Mock()
        mock_ami.name = None
        mock_ami.tags = []

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []

            serializer = AwsAccountSerializer(context=context)

            result = serializer.create(validated_data)
            self.assertIsInstance(result, AwsAccount)
            mock_tasks.initial_aws_describe_instances.delay.assert_called()

        # Verify that we created the account.
        account = AwsAccount.objects.get(aws_account_id=aws_account_id)
        self.assertEqual(str(aws_account_id), account.aws_account_id)
        self.assertEqual(arn, account.account_arn)

        # Verify that we created no instances yet.
        instances = AwsInstance.objects.filter(account=account).all()
        self.assertEqual(len(instances), 0)

        # Verify that we created no images yet.
        amis = AwsMachineImage.objects.all()
        self.assertEqual(len(amis), 0)

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
                patch.object(aws, 'get_running_instances') as mock_get_run:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_get_run.return_value = running_instances
            serializer = AwsAccountSerializer(context=context)

            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            raised_exception = cm.exception
            self.assertIn('account_arn', raised_exception.detail)
            self.assertIn(str(aws_account_id),
                          raised_exception.detail['account_arn'][0])


class AwsMachineImageSerializerTest(TestCase):
    """AwsMachineImage serializer test case."""

    def test_update_succeeds_when_rhel_challenged_is_unset(self):
        """If RHEL challenged is unset, test that the update succeeds."""
        mock_image = Mock()
        mock_image.rhel_challenged = True
        mock_image.openshift_challenged = True
        mock_image.save = Mock(return_value=None)
        validated_data = {
            'rhel_challenged': False
        }
        serializer = AwsMachineImageSerializer()
        serializer.update(mock_image, validated_data)
        self.assertFalse(mock_image.rhel_challenged)
        mock_image.save.assert_called()

    def test_update_succeeds_when_rhel_challenged_is_set(self):
        """If RHEL challenged is set, test that the update succeeds."""
        mock_image = Mock()
        mock_image.rhel_challenged = False
        mock_image.openshift_challenged = True
        mock_image.save = Mock(return_value=None)

        validated_data = {
            'rhel_challenged': True
        }
        serializer = AwsMachineImageSerializer()
        serializer.update(mock_image, validated_data)
        self.assertTrue(mock_image.rhel_challenged)

    def test_no_update_when_nothing_changes(self):
        """If RHEL challenged is set, test that the update succeeds."""
        mock_image = Mock()
        mock_image.rhel_challenged = False
        mock_image.openshift_challenged = False
        mock_image.save = Mock(return_value=None)

        validated_data = {}

        serializer = AwsMachineImageSerializer()
        serializer.update(mock_image, validated_data)

        self.assertFalse(mock_image.rhel_challenged)
        self.assertFalse(mock_image.openshift_challenged)
        mock_image.save.assert_not_called()
