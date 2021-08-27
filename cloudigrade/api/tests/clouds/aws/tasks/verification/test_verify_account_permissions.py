"""Collection of tests for aws.tasks.cloudtrail.verify_account_permissions."""
from unittest.mock import patch

from django.test import TestCase

from api.clouds.aws import tasks
from util.tests import helper as util_helper


class VerifyAccountPermissionsTest(TestCase):
    """Task 'configure_customer_aws_and_create_cloud_account' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.arn = util_helper.generate_dummy_arn()

    @patch("api.clouds.aws.tasks.verification.AwsCloudAccount")
    def test_success(self, mock_aws_cloud_account_model):
        """Assert happy path when account is enabled."""
        mock_aws_cloud_account = mock_aws_cloud_account_model.objects.get.return_value
        mock_account = mock_aws_cloud_account.cloud_account.get.return_value
        mock_account.enable.return_value = True

        valid = tasks.verify_account_permissions(self.arn)

        self.assertTrue(valid)
        mock_account.enable.assert_called_once()

    def test_account_does_not_exist(self):
        """Assert proper exception handling when the account no longer exists."""
        with self.assertLogs("api.clouds.aws.tasks", level="INFO") as log_context:
            valid = tasks.verify_account_permissions(self.arn)
        self.assertFalse(valid)
        self.assertIn("cloud account object does not exist", log_context.output[0])
        self.assertIn(self.arn, log_context.output[0])
