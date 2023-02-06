"""Collection of tests for ``util.aws.helper`` module."""
import uuid
from unittest.mock import Mock, call, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from util.aws import helper
from util.exceptions import AwsThrottlingException
from util.tests import helper as util_helper


class UtilAwsHelperTest(TestCase):
    """AWS helper utility functions test case."""

    def test_rewrap_aws_errors_returns_inner_return(self):
        """Assert rewrap_aws_errors returns inner function's result if no exception."""

        @helper.rewrap_aws_errors
        def dummy_adder(a, b):
            return a + b

        expected_result = 3
        actual_result = dummy_adder(1, 2)
        self.assertEqual(actual_result, expected_result)

    def test_rewrap_aws_errors_raises_not_aws_clienterror(self):
        """Assert rewrap_aws_errors allows non-ClientError exceptions to raise."""

        class DummyException(Exception):
            pass

        @helper.rewrap_aws_errors
        def dummy_adder(a, b):
            raise DummyException

        with self.assertRaises(DummyException):
            dummy_adder(1, 2)

    def test_rewrap_aws_errors_quietly_logs_aws_unauthorizedoperation(self):
        """
        Assert rewrap_aws_errors quietly logs UnauthorizedOperation exceptions.

        When we encounter UnauthorizedOperation, that means we did not have permission
        to perform the operation on behalf of the customer. This should only happen if
        the customer's AWS IAM configuration has broken. When this happens, we want to
        processing to stop gracefully (such as the async tasks) and to allow the
        periodic task responsible for checking permissions to disable the account if
        necessary.
        """
        mock_error = {
            "Error": {
                "Code": "UnauthorizedOperation",
                "Message": "Something bad happened.",
            }
        }

        @helper.rewrap_aws_errors
        def dummy_adder(a, b):
            raise ClientError(mock_error, "SomeRandomAction")

        with self.assertLogs("util.aws.helper", level="WARNING") as logging_watcher:
            actual_result = dummy_adder(1, 2)
            self.assertIn("Something bad happened.", logging_watcher.output[0])

        self.assertIsNone(actual_result)

    def test_rewrap_aws_throttling(self):
        """Assert rewrap_aws_errors raises AwsThrottlingException."""
        mock_error = {
            "Error": {
                "Code": "ThrottlingException",
                "Message": "AWS is throttling your request.",
            }
        }

        @helper.rewrap_aws_errors
        def dummy_adder():
            raise ClientError(mock_error, "SomeRandomAction")

        with self.assertRaises(AwsThrottlingException):
            dummy_adder()

    @patch("util.aws.helper._verify_policy_action")
    def test_verify_account_access_success(self, mock_verify_policy_action):
        """Assert that account access is verified when all actions are OK."""
        mock_session = Mock()
        expected_calls = [call(mock_session, "sts:GetCallerIdentity")]
        mock_verify_policy_action.side_effect = [True]
        verified, failed_actions = helper.verify_account_access(mock_session)
        self.assertTrue(verified)
        self.assertEqual(len(failed_actions), 0)
        mock_verify_policy_action.assert_has_calls(expected_calls)

    @patch("util.aws.helper._verify_policy_action")
    def test_verify_account_access_failure(self, mock_verify_policy_action):
        """Assert that account access fails when some actions are not OK."""
        mock_session = Mock()
        expected_calls = [call(mock_session, "sts:GetCallerIdentity")]
        mock_verify_policy_action.side_effect = [False]
        verified, failed_actions = helper.verify_account_access(mock_session)
        self.assertFalse(verified)
        self.assertEqual(failed_actions, ["sts:GetCallerIdentity"])
        mock_verify_policy_action.assert_has_calls(expected_calls)

    @patch("util.aws.helper._get_primary_account_id")
    def test_verify_policy_success(self, mock_get_primary_account_id):
        """Assert successful sts:GetCallerIdentity verification returns True."""
        server_aws_account_id = util_helper.generate_dummy_aws_account_id()
        mock_get_primary_account_id.return_value = server_aws_account_id
        customer_aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.assertNotEqual(customer_aws_account_id, server_aws_account_id)

        mock_session = Mock()
        mock_client = mock_session.client.return_value
        dummy_arn = util_helper.generate_dummy_arn(
            account_id=customer_aws_account_id,
            service="sts",
            resource_type="assumed-role",
            resource=f"customer-arn-name/cloudigrade-{customer_aws_account_id}",
        )
        mock_client.get_caller_identity.return_value = {
            "UserId": str(uuid.uuid4()),
            "Account": customer_aws_account_id,
            "Arn": dummy_arn,
        }
        result = helper._verify_policy_action(mock_session, "sts:GetCallerIdentity")
        self.assertTrue(result)

    @patch("util.aws.helper._get_primary_account_id")
    def test_verify_policy_invalid_arn_fails(self, mock_get_primary_account_id):
        """Assert verifying sts:GetCallerIdentity with an invalid ARN returns False."""
        server_aws_account_id = util_helper.generate_dummy_aws_account_id()
        mock_get_primary_account_id.return_value = server_aws_account_id

        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_client.get_caller_identity.return_value = {"Arn": str(uuid.uuid4())}
        result = helper._verify_policy_action(mock_session, "sts:GetCallerIdentity")
        self.assertFalse(result)

    def test_verify_policy_action_unknown(self):
        """Assert trying to verify an unknown action returns False."""
        mock_session = Mock()
        bogus_action = str(uuid.uuid4())
        result = helper._verify_policy_action(mock_session, bogus_action)
        self.assertFalse(result)

    def test_verify_account_access_failure_unauthorized(self):
        """Assert that account access fails for an unauthorized operation."""
        action = "sts:GetCallerIdentity"
        function_name = "get_caller_identity"

        mock_function = Mock()
        mock_function.side_effect = ClientError(
            error_response={"Error": {"Code": "UnauthorizedOperation"}},
            operation_name=action,
        )
        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_client.attach_mock(mock_function, function_name)

        result = helper._verify_policy_action(mock_session, action)
        self.assertFalse(result)
