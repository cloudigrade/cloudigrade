"""Collection of tests for custom DRF serializers in the account app."""
from unittest.mock import Mock, patch

import faker
from botocore.exceptions import ClientError
from django.test import TestCase, TransactionTestCase
from rest_framework.serializers import ValidationError

from api.models import (AwsCloudAccount,
                        AwsMachineImage, CloudAccount, Instance)
from api.serializers import (CloudAccountSerializer,
                             MachineImageSerializer, aws)
from api.tests import helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class AwsAccountSerializerTest(TransactionTestCase):
    """AwsAccount serializer test case."""

    def setUp(self):
        """Set up shared test data."""
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.arn = util_helper.generate_dummy_arn(self.aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.validated_data = {
            'account_arn': self.arn,
            'name': 'account_name',
            'cloud_type': 'aws',
        }

    def test_serialization_fails_when_all_empty_fields(self):
        """Test that an account is not saved if all fields are empty."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        validated_data = {}

        with patch.object(
            aws, 'verify_account_access'
        ) as mock_verify, patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(
                context=context, data=validated_data
            )
            serializer.is_valid()
            self.assertEquals(
                'This field is required.',
                str(serializer.errors['cloud_type'][0]),
            )
            self.assertEquals(
                'This field is required.', str(serializer.errors['name'][0])
            )

    def test_serialization_fails_on_only_empty_name(self):
        """Test that an account is not saved if only name is empty."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        validated_data = {'account_arn': self.arn, 'cloud_type': 'aws'}

        with patch.object(
            aws, 'verify_account_access'
        ) as mock_verify, patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(
                context=context, data=validated_data
            )
            serializer.is_valid()
            self.assertEquals(
                'This field is required.', str(serializer.errors['name'][0])
            )

    def test_serialization_fails_on_only_empty_cloud_type(self):
        """Test that an account is not saved if only cloud_type is empty."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        validated_data = {'account_arn': self.arn, 'name': _faker.name()}

        with patch.object(
            aws, 'verify_account_access'
        ) as mock_verify, patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(
                context=context, data=validated_data
            )
            serializer.is_valid()
            self.assertEquals(
                'This field is required.',
                str(serializer.errors['cloud_type'][0]),
            )

    def test_serialization_fails_on_only_empty_account_arn(self):
        """Test that an AWS account is not saved if account_arn is empty."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        validated_data = {'cloud_type': 'aws', 'name': _faker.name()}

        with patch.object(
            aws, 'verify_account_access'
        ) as mock_verify, patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(
                context=context, data=validated_data
            )
            serializer.is_valid()
            self.assertEquals(
                'This field is required.',
                str(serializer.errors['account_arn'][0]),
            )

    def test_serialization_fails_on_unsupported_cloud_type(self):
        """Test that account is not saved with unsupported cloud_type."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        bad_type = _faker.name()
        validated_data = {'cloud_type': bad_type, 'name': _faker.name()}

        with patch.object(
            aws, 'verify_account_access'
        ) as mock_verify, patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(
                context=context, data=validated_data
            )
            serializer.is_valid()
            self.assertEquals(
                f'"{bad_type}" is not a valid choice.',
                str(serializer.errors['cloud_type'][0]),
            )

    @patch('api.serializers.tasks')
    def test_create_succeeds_when_account_verified(self, mock_tasks):
        """Test saving of a test ARN."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}

        serializer = CloudAccountSerializer(context=context)

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            result = serializer.create(self.validated_data)
            self.assertIsInstance(result, CloudAccount)
            mock_tasks.initial_aws_describe_instances.delay.assert_called()

        # Verify that we created the account.
        account = AwsCloudAccount.objects.get(
            aws_account_id=self.aws_account_id)
        self.assertEqual(self.aws_account_id, account.aws_account_id)
        self.assertEqual(self.arn, account.account_arn)

        # Verify that we created no instances yet.
        instances = Instance.objects.filter(
            cloud_account=account.cloud_account.get()).all()
        self.assertEqual(len(instances), 0)

        # Verify that we created no images yet.
        amis = AwsMachineImage.objects.all()
        self.assertEqual(len(amis), 0)

    def test_create_fails_duplicate_arn(self):
        """Test that an exception is raised if arn already exists."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}
        serializer = CloudAccountSerializer(context=context)

        helper.generate_aws_account(
            aws_account_id=self.aws_account_id,
            arn=self.arn,
            name='account_name'
        )

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            with self.assertRaises(ValidationError) as cm:
                serializer.create(self.validated_data)
                expected_error = {
                    'account_arn': [
                        'An ARN already exists for account "{0}"'.format(
                            self.aws_account_id)
                    ]
                }
                self.assertEquals(expected_error, cm.exception)

    def test_create_fails_access_denied(self):
        """Test that an exception is raised if access is denied to the arn."""
        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDenied'}},
            operation_name=Mock(),
        )

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}
        serializer = CloudAccountSerializer(context=context)

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.side_effect = client_error
            mock_verify.return_value = True, []

            with self.assertRaises(ValidationError) as cm:
                serializer.create(self.validated_data)
                expected_error = {
                    'account_arn': [
                        'Permission denied for ARN "{0}"'.format(
                            self.arn)
                    ]
                }
                self.assertEquals(expected_error, cm.exception)

    def test_create_fails_when_aws_verify_fails(self):
        """Test that an exception is raised if verify_account_access fails."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}
        serializer = CloudAccountSerializer(context=context)

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = False, []

            with self.assertRaises(ValidationError) as cm:
                serializer.create(self.validated_data)
                expected_error = {
                    'account_arn': [
                        'Account verification failed.'
                    ]
                }
                self.assertEquals(expected_error, cm.exception)

    def test_create_fails_cloudtrail_configuration_error(self):
        """Test that an exception occurs if cloudtrail configuration fails."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {'request': mock_request}
        serializer = CloudAccountSerializer(context=context)

        client_error = ClientError(
            error_response={'Error': {'Code': 'AccessDeniedException'}},
            operation_name=Mock(),
        )

        with patch.object(aws, 'verify_account_access') as mock_verify, \
                patch.object(aws.sts, 'boto3') as mock_boto3, \
                patch.object(aws, 'configure_cloudtrail') as mock_cloudtrail:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []
            mock_cloudtrail.side_effect = client_error

            with self.assertRaises(ValidationError) as cm:
                serializer.create(self.validated_data)
                expected_error = {
                    'account_arn': [
                        'Access denied to create CloudTrail for '
                        'ARN "{0}"'.format(self.arn)
                    ]
                }
                self.assertEquals(expected_error, cm.exception)


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
        serializer = MachineImageSerializer()
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
        serializer = MachineImageSerializer()
        serializer.update(mock_image, validated_data)
        self.assertTrue(mock_image.rhel_challenged)

    def test_no_update_when_nothing_changes(self):
        """If RHEL challenged is set, test that the update succeeds."""
        mock_image = Mock()
        mock_image.rhel_challenged = False
        mock_image.openshift_challenged = False
        mock_image.save = Mock(return_value=None)

        validated_data = {}

        serializer = MachineImageSerializer()
        serializer.update(mock_image, validated_data)

        self.assertFalse(mock_image.rhel_challenged)
        self.assertFalse(mock_image.openshift_challenged)
        mock_image.save.assert_not_called()
