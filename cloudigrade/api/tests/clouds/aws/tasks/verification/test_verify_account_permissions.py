"""Collection of tests for aws.tasks.cloudtrail.verify_account_permissions."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.clouds.aws import tasks
from util.tests import helper as util_helper


class VerifyAccountPermissionsTest(TestCase):
    """Task 'configure_customer_aws_and_create_cloud_account' test cases."""

    @patch("api.clouds.aws.tasks.verification.verify_permissions")
    def test_success(self, mock_verify_permissions):
        """Account permissions are verified successfully."""
        arn = util_helper.generate_dummy_arn

        valid = tasks.verify_account_permissions(arn)

        mock_verify_permissions.assert_called()
        self.assertTrue(valid)

    @patch("api.clouds.aws.tasks.verification.AwsCloudAccount")
    @patch("api.clouds.aws.tasks.verification.verify_permissions")
    def test_failure(self, mock_verify_permissions, mock_aws_cloud_account):
        """Account permission verification fails."""
        arn = util_helper.generate_dummy_arn
        mock_verify_permissions.side_effect = ValidationError()

        with self.assertLogs("api.clouds.aws.tasks", level="INFO") as cm:
            valid = tasks.verify_account_permissions(arn)

            mock_verify_permissions.assert_called()
            self.assertFalse(valid)
            self.assertIn(
                "failed validation. Disabling the cloud account.", cm.output[0]
            )
            aws_clount = mock_aws_cloud_account.objects.get
            aws_clount.assert_called_once()
            clount = aws_clount.return_value.cloud_account.get.return_value
            clount.disable.assert_called_once()
