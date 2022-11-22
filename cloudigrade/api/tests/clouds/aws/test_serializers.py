"""Collection of tests for custom DRF serializers in the account app."""
from unittest.mock import Mock, patch

import faker
from botocore.exceptions import ClientError
from django.test import TransactionTestCase
from rest_framework.serializers import ValidationError

from api.clouds.aws.models import AwsCloudAccount, AwsMachineImage
from api.models import CloudAccount, Instance
from api.serializers import CloudAccountSerializer, aws
from util.tests import helper as util_helper

_faker = faker.Faker()


class AwsAccountSerializerTest(TransactionTestCase):
    """AwsAccount serializer test case."""

    def setUp(self):
        """Set up shared test data."""
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.arn = util_helper.generate_dummy_arn(self.aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.validated_data = util_helper.generate_dummy_aws_cloud_account_post_data()
        self.validated_data.update({"account_arn": self.arn})

    def test_serialization_fails_when_all_empty_fields(self):
        """Test that an account is not saved if all fields are empty."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {"request": mock_request}

        validated_data = {}

        with patch.object(aws, "verify_account_access") as mock_verify, patch.object(
            aws.sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(context=context, data=validated_data)
            serializer.is_valid()
            self.assertEquals(
                "This field is required.",
                str(serializer.errors["cloud_type"][0]),
            )

    def test_serialization_fails_on_only_empty_cloud_type(self):
        """Test that an account is not saved if only cloud_type is empty."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {"request": mock_request}

        validated_data = {"account_arn": self.arn}

        with patch.object(aws, "verify_account_access") as mock_verify, patch.object(
            aws.sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(context=context, data=validated_data)
            serializer.is_valid()
            self.assertEquals(
                "This field is required.",
                str(serializer.errors["cloud_type"][0]),
            )

    def test_serialization_fails_on_only_empty_account_arn(self):
        """Test that an AWS account is not saved if account_arn is empty."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {"request": mock_request}

        validated_data = {"cloud_type": "aws"}

        with patch.object(aws, "verify_account_access") as mock_verify, patch.object(
            aws.sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(context=context, data=validated_data)
            serializer.is_valid()
            with self.assertRaises(ValidationError) as cm:
                serializer.create(validated_data)
            self.assertEquals(
                "This field is required.",
                str(cm.exception.detail["account_arn"]),
            )

    def test_serialization_fails_on_unsupported_cloud_type(self):
        """Test that account is not saved with unsupported cloud_type."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {"request": mock_request}

        bad_type = _faker.name()
        validated_data = {"cloud_type": bad_type}

        with patch.object(aws, "verify_account_access") as mock_verify, patch.object(
            aws.sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = True, []

            serializer = CloudAccountSerializer(context=context, data=validated_data)
            serializer.is_valid()
            self.assertEquals(
                f'"{bad_type}" is not a valid choice.',
                str(serializer.errors["cloud_type"][0]),
            )

    @patch.object(CloudAccount, "enable")
    def test_create_succeeds_when_account_verified(self, mock_enable):
        """Test saving of a test ARN."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {"request": mock_request}

        serializer = CloudAccountSerializer(context=context)

        result = serializer.create(self.validated_data)
        self.assertIsInstance(result, CloudAccount)
        mock_enable.assert_called()

        # Verify that we created the account.
        account = AwsCloudAccount.objects.get(aws_account_id=self.aws_account_id)
        self.assertEqual(self.aws_account_id, account.aws_account_id)
        self.assertEqual(self.arn, account.account_arn)

        # Verify that we created no instances yet.
        instances = Instance.objects.filter(
            cloud_account=account.cloud_account.get()
        ).all()
        self.assertEqual(len(instances), 0)

        # Verify that we created no images yet.
        amis = AwsMachineImage.objects.all()
        self.assertEqual(len(amis), 0)

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_create_fails_access_denied(self, mock_notify_sources):
        """Test that an exception is raised if access is denied to the arn."""
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}},
            operation_name=Mock(),
        )

        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {"request": mock_request}
        serializer = CloudAccountSerializer(context=context)

        with patch.object(aws, "verify_account_access") as mock_verify, patch.object(
            aws.sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.side_effect = client_error
            mock_verify.return_value = True, []

            expected_error = "Could not enable"
            with self.assertLogs("api.models", level="INFO") as cm, self.assertRaises(
                ValidationError
            ):
                serializer.create(self.validated_data)
            log_record = cm.records[1]
            self.assertIn(expected_error, log_record.msg.detail["account_arn"])

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_create_fails_when_aws_verify_fails(self, mock_notify_sources):
        """Test that an exception is raised if verify_account_access fails."""
        mock_request = Mock()
        mock_request.user = util_helper.generate_test_user()
        context = {"request": mock_request}
        serializer = CloudAccountSerializer(context=context)

        with patch.object(aws, "verify_account_access") as mock_verify, patch.object(
            aws.sts, "boto3"
        ) as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            mock_verify.return_value = False, []

            expected_error = "Could not enable"
            with self.assertLogs("api.models", level="INFO") as cm, self.assertRaises(
                ValidationError
            ):
                serializer.create(self.validated_data)
            log_record = cm.records[1]
            self.assertIn(expected_error, log_record.msg.detail["account_arn"])
