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
        self.external_id = _faker.uuid4()

    def test_verify_permissions_success(self):
        """Test happy path for verify_permissions."""
        with patch.object(util.aws, "get_session"), patch.object(
            util.aws, "verify_account_access"
        ) as mock_aws_verify_account_access, patch(
            "api.tasks.sources.notify_application_availability_task"
        ) as mock_notify_sources:
            mock_aws_verify_account_access.return_value = True, []
            verified = util.verify_permissions(self.arn, None)

        self.assertTrue(verified)
        mock_notify_sources.delay.assert_not_called()

    def test_verify_permissions_fails_if_cloud_account_does_not_exist(self):
        """Test handling when the CloudAccount is missing."""
        arn = util_helper.generate_dummy_arn()
        external_id = _faker.uuid4()
        with patch(
            "api.tasks.sources.notify_application_availability_task"
        ) as mock_notify_sources:
            verified = util.verify_permissions(arn, external_id)

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
                verified = util.verify_permissions(self.arn, None)

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
            verified = util.verify_permissions(self.arn, None)

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
            verified = util.verify_permissions(self.arn, None)

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
            verified = util.verify_permissions(self.arn, None)

        self.assertFalse(verified)
        mock_notify_sources.delay.assert_called()
