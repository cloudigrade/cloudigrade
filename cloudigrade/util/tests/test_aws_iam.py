"""Collection of tests for ``util.aws.sts`` module."""
from unittest.mock import Mock, patch

from django.test import TestCase

from util.aws import AwsArn, iam
from util.tests import helper


class UtilAwsIamTest(TestCase):
    """AWS IAM utility functions test case."""

    @patch('util.aws.iam.get_session_account_id')
    @patch('util.aws.iam._get_primary_account_id')
    def test_get_standard_policy_name_and_arn(
        self, mock_get_primary_account_id, mock_get_session_account_id
    ):
        """Assert get_standard_policy_name_and_arn returns expected values."""
        system_account_id = helper.generate_dummy_aws_account_id()
        customer_account_id = helper.generate_dummy_aws_account_id()

        mock_get_primary_account_id.return_value = system_account_id
        mock_get_session_account_id.return_value = customer_account_id

        mock_session = Mock()
        policy_name, policy_arn = iam.get_standard_policy_name_and_arn(
            mock_session
        )
        mock_get_session_account_id.assert_called_with(mock_session)
        mock_get_primary_account_id.assert_called()

        arn = AwsArn(policy_arn)
        self.assertEqual(arn.account_id, customer_account_id)
        self.assertEqual(arn.service, 'iam')
        self.assertEqual(arn.resource_type, 'policy')
        self.assertIn(str(system_account_id), arn.resource)
