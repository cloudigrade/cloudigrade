"""Collection of tests for the api.clouds.aws.util module."""
from unittest.mock import Mock, patch

import faker
from botocore.exceptions import ClientError
from django.test import TestCase

from api.clouds.aws import util
from api.tests import helper as api_helper
from util import aws
from util.tests import helper as util_helper

_faker = faker.Faker()


class CloudsAwsUtilCloudTrailTest(TestCase):
    """Test cases for CloudTrail related functions in api.clouds.aws.util."""

    def setUp(self):
        """Set up basic aws account."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.account = api_helper.generate_cloud_account_aws(
            aws_account_id=aws_account_id, arn=arn
        )

    def test_delete_cloudtrail_success(self):
        """Test delete_cloudtrail normal happy path."""
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "delete_cloudtrail"
        ) as mock_delete_cloudtrail:
            success = util.delete_cloudtrail(self.account.content_object)
            mock_delete_cloudtrail.assert_called()
        self.assertTrue(success)

    def test_delete_cloudtrail_not_found(self):
        """
        Test delete_cloudtrail handles when AWS raises an TrailNotFoundException error.

        This could happen if the trail has already been deleted. We treat this as a
        success since the same effective outcome is no trail for us.
        """
        client_error = ClientError(
            error_response={"Error": {"Code": "TrailNotFoundException"}},
            operation_name=Mock(),
        )
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "delete_cloudtrail"
        ) as mock_delete_cloudtrail:
            mock_delete_cloudtrail.side_effect = client_error
            success = util.delete_cloudtrail(self.account.content_object)
            mock_delete_cloudtrail.assert_called()
        self.assertTrue(success)

    def test_delete_cloudtrail_access_denied(self):
        """
        Test delete_cloudtrail handles when AWS raises an AccessDenied error.

        This could happen if the user has deleted the AWS account or role. We treat this
        as a non-blocking failure and simply log messages.
        """
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}},
            operation_name=Mock(),
        )
        expected_warnings = [
            "encountered AccessDenied and cannot delete cloudtrail",
            f"CloudAccount ID {self.account.id}",
        ]
        with self.assertLogs(
            "api.clouds.aws.util", level="WARNING"
        ) as logger, patch.object(util.aws, "get_session"), patch.object(
            util.aws, "delete_cloudtrail"
        ) as mock_delete_cloudtrail:
            mock_delete_cloudtrail.side_effect = client_error
            success = util.delete_cloudtrail(self.account.content_object)
            mock_delete_cloudtrail.assert_called()
            for expected_warning in expected_warnings:
                self.assertIn(expected_warning, logger.output[0])
        self.assertFalse(success)

    def test_delete_cloudtrail_unexpected_error_code(self):
        """
        Test delete_cloudtrail handles when AWS raises an unexpected error code.

        This could happen if AWS is misbehaving unexpectedly. We treat this as a
        non-blocking failure and simply log messages.
        """
        client_error = ClientError(
            error_response={"Error": {"Code": "Potatoes"}},
            operation_name=Mock(),
        )
        expected_errors = [
            "Unexpected error Potatoes occurred disabling CloudTrail",
            f"AwsCloudAccount ID {self.account.id}",
        ]
        with self.assertLogs(
            "api.clouds.aws.util", level="ERROR"
        ) as logger, patch.object(util.aws, "get_session"), patch.object(
            util.aws, "delete_cloudtrail"
        ) as mock_delete_cloudtrail:
            mock_delete_cloudtrail.side_effect = client_error
            success = util.delete_cloudtrail(self.account.content_object)
            mock_delete_cloudtrail.assert_called()
            self.assertIn("Traceback", logger.output[0])  # from logger.exception
            for expected_error in expected_errors:
                self.assertIn(expected_error, logger.output[1])  # from logger.error
        self.assertFalse(success)


class CloudsAwsUtilVerifyPermissionsTest(TestCase):
    """Test cases for api.clouds.aws.util.verify_permissions."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.account = api_helper.generate_cloud_account(
            aws_account_id=self.aws_account_id, user=self.user
        )
        self.arn = util_helper.generate_dummy_arn(account_id=self.aws_account_id)

    def test_verify_permissions_success(self):
        """Test happy path for verify_permissions."""
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "verify_account_access"
        ) as mock_aws_verify_account_access, patch(
            "api.tasks.sources.notify_application_availability_task"
        ) as mock_notify_sources:
            mock_aws_verify_account_access.return_value = True, []
            verified = util.verify_permissions(self.arn)

        self.assertTrue(verified)
        mock_notify_sources.delay.assert_not_called()

    def test_verify_permissions_fails_if_cloud_account_does_not_exist(self):
        """Test handling when the CloudAccount is missing."""
        arn = util_helper.generate_dummy_arn()
        with patch(
            "api.tasks.sources.notify_application_availability_task"
        ) as mock_notify_sources:
            verified = util.verify_permissions(arn)

        self.assertFalse(verified)
        # We do not notify sources because we do not have the CloudAccount which has
        # the application_id needed to notify sources!
        mock_notify_sources.delay.assert_not_called()

    def test_verify_permissions_fails_if_session_error_code_in_tuple(self):
        """Test handling error codes from AWS when trying to get a session."""
        for error_code in aws.COMMON_AWS_ACCESS_DENIED_ERROR_CODES:
            client_error = ClientError(
                error_response={"Error": {"Code": error_code}},
                operation_name=Mock(),
            )
            with patch.object(util.aws, "get_session") as mock_get_session, patch(
                "api.tasks.sources.notify_application_availability_task"
            ) as mock_notify_sources:
                mock_get_session.side_effect = client_error
                verified = util.verify_permissions(self.arn)

            self.assertFalse(verified)
            mock_notify_sources.delay.assert_called()

    def test_verify_permissions_fails_if_mystery_aws_error(self):
        """Test handling some other error from AWS when trying to get a session."""
        error_code = _faker.slug()
        client_error = ClientError(
            error_response={"Error": {"Code": error_code}},
            operation_name=Mock(),
        )
        with self.assertLogs(
            "api.clouds.aws.util", level="ERROR"
        ) as logger, patch.object(util.aws, "get_session") as mock_get_session, patch(
            "api.tasks.sources.notify_application_availability_task"
        ) as mock_notify_sources:
            mock_get_session.side_effect = client_error
            verified = util.verify_permissions(self.arn)

        self.assertFalse(verified)
        mock_notify_sources.delay.assert_called()

        expected_logger_error = (
            f"Unexpected AWS ClientError '{error_code}' in verify_permissions."
        )
        found_logger_output = [
            output for output in logger.output if expected_logger_error in output
        ]
        self.assertTrue(found_logger_output)

    def test_verify_permissions_fails_if_verify_account_access_fails(self):
        """Test handling when aws.verify_account_access does not succeed."""
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "verify_account_access"
        ) as mock_aws_verify_account_access, patch(
            "api.tasks.sources.notify_application_availability_task"
        ) as mock_notify_sources:
            mock_aws_verify_account_access.return_value = False, [_faker.slug()]
            verified = util.verify_permissions(self.arn)

        self.assertFalse(verified)
        mock_notify_sources.delay.assert_called()

    def test_verify_permissions_fails_if_mystery_exception(self):
        """Test handling a completely unexpected exception type."""
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "verify_account_access"
        ) as mock_verify_access, patch(
            "api.tasks.sources.notify_application_availability_task"
        ) as mock_notify_sources:
            mock_verify_access.side_effect = Exception
            verified = util.verify_permissions(self.arn)

        self.assertFalse(verified)
        mock_notify_sources.delay.assert_called()
