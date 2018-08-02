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
                            AwsMachineImage,
                            InstanceEvent)
from account.serializers import (AwsAccountSerializer,
                                 aws)
from account.tests import helper as account_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class AwsAccountSerializerTest(TestCase):
    """AwsAccount serializer test case."""

    @patch('account.serializers.start_image_inspection')
    def test_create_succeeds_when_account_verified(self, mock_copy_snapshot):
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

        mock_ami = Mock()
        mock_ami.name = None
        mock_ami.tags = []

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'get_running_instances') as mock_get_run, \
                patch.object(aws, 'get_ami') as mock_get_ami:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role
            mock_verify.return_value = True, []
            mock_get_run.return_value = running_instances
            mock_get_ami.return_value = mock_ami
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
        self.assertIsInstance(mock_copy_snapshot.call_args[0][0], str)

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

    @patch('util.aws.ec2.check_image_state')
    @patch('account.tasks.aws')
    def test_ami_name_added(self, mock_aws, mock_check_image_state):
        """Test AMI name added to MachineImage."""
        mock_session = mock_aws.boto3.Session.return_value

        ami_id = util_helper.generate_dummy_image_id()
        ami_region = random.choice(util_helper.SOME_AWS_REGIONS)
        ami_name = _faker.bs()
        mock_ami = util_helper.generate_mock_image(ami_id)
        mock_ami.tags = []
        mock_ami.name = ami_name
        mock_resource = mock_session.resource.return_value
        mock_resource.Image.return_value = mock_ami

        test_user = util_helper.generate_test_user()
        test_account = AwsAccount.objects.create(
            user=test_user,
            aws_account_id=util_helper.generate_dummy_aws_account_id,
            account_arn=util_helper.generate_dummy_arn)
        test_image = AwsMachineImage.objects.create(
            account=test_account,
            ec2_ami_id=ami_id
        )

        serializer = AwsAccountSerializer()
        self.assertIsNone(test_image.name)

        serializer.add_ami_metadata(
            mock_session, ami_id, ami_region, test_image)
        self.assertEqual(test_image.name, ami_name)

    @patch('util.aws.ec2.check_image_state')
    @patch('account.tasks.aws')
    def test_openshift_tag_added(self, mock_aws, mock_check_image_state):
        """Test openshift tag added to MachineImage."""
        mock_session = mock_aws.boto3.Session.return_value

        ami_id = util_helper.generate_dummy_image_id()
        ami_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_ami = util_helper.generate_mock_image(ami_id)
        mock_ami.tags = [{'Key': 'cloudigrade-ocp-present',
                          'Value': 'cloudigrade-ocp-present'}]
        mock_ami.name = None
        mock_resource = mock_session.resource.return_value
        mock_resource.Image.return_value = mock_ami

        test_user = util_helper.generate_test_user()
        test_account = AwsAccount.objects.create(
            user=test_user,
            aws_account_id=util_helper.generate_dummy_aws_account_id,
            account_arn=util_helper.generate_dummy_arn)
        test_image = AwsMachineImage.objects.create(
            account=test_account,
            ec2_ami_id=ami_id
        )

        serializer = AwsAccountSerializer()
        self.assertFalse(test_image.openshift_detected)

        serializer.add_ami_metadata(
            mock_session, ami_id, ami_region, test_image)
        self.assertIsNone(test_image.name)
        self.assertTrue(test_image.openshift_detected)

    @patch('util.aws.ec2.check_image_state')
    @patch('account.tasks.aws')
    def test_openshift_tag_not_added(self, mock_aws, mock_check_image_state):
        """Test openshift tag not added to MachineImage."""
        mock_session = mock_aws.boto3.Session.return_value

        ami_id = util_helper.generate_dummy_image_id()
        ami_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_ami = util_helper.generate_mock_image(ami_id)
        mock_ami.tags = [{'Key': 'random',
                          'Value': 'random'}]
        mock_ami.name = None
        mock_resource = mock_session.resource.return_value
        mock_resource.Image.return_value = mock_ami

        test_user = util_helper.generate_test_user()
        test_account = AwsAccount.objects.create(
            user=test_user,
            aws_account_id=util_helper.generate_dummy_aws_account_id,
            account_arn=util_helper.generate_dummy_arn)
        test_image = AwsMachineImage.objects.create(
            account=test_account,
            ec2_ami_id=ami_id
        )

        serializer = AwsAccountSerializer()
        self.assertFalse(test_image.openshift_detected)

        serializer.add_ami_metadata(
            mock_session, ami_id, ami_region, test_image)
        self.assertIsNone(test_image.name)
        self.assertFalse(test_image.openshift_detected)

    @patch('util.aws.ec2.check_image_state')
    @patch('account.tasks.aws')
    def test_openshift_no_tags(self, mock_aws, mock_check_image_state):
        """Test case where AMI has no tags."""
        mock_session = mock_aws.boto3.Session.return_value

        ami_id = util_helper.generate_dummy_image_id()
        ami_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_ami = util_helper.generate_mock_image(ami_id)
        mock_ami.tags = None
        mock_ami.name = None
        mock_resource = mock_session.resource.return_value
        mock_resource.Image.return_value = mock_ami

        test_user = util_helper.generate_test_user()
        test_account = AwsAccount.objects.create(
            user=test_user,
            aws_account_id=util_helper.generate_dummy_aws_account_id,
            account_arn=util_helper.generate_dummy_arn)
        test_image = AwsMachineImage.objects.create(
            account=test_account,
            ec2_ami_id=ami_id
        )

        serializer = AwsAccountSerializer()
        self.assertFalse(test_image.openshift_detected)

        serializer.add_ami_metadata(
            mock_session, ami_id, ami_region, test_image)
        self.assertIsNone(test_image.name)
        self.assertFalse(test_image.openshift_detected)

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
            self.assertIn(aws_account_id,
                          raised_exception.detail['account_arn'][0])
