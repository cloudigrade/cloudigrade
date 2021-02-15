"""Collection of tests for api.cloud.aws.util.create_aws_cloud_account."""
from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.clouds.aws import util
from api.models import CloudAccount
from util.tests import helper as util_helper

_faker = faker.Faker()


class CreateAWSClountTest(TestCase):
    """Test cases for api.cloud.aws.util.create_aws_cloud_account."""

    def setUp(self):
        """Set up shared variables."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.arn = util_helper.generate_dummy_arn(account_id=self.aws_account_id)
        self.name = _faker.word()
        self.auth_id = _faker.pyint()
        self.app_id = _faker.pyint()
        self.source_id = _faker.pyint()

    @patch.object(CloudAccount, "enable")
    def test_create_aws_clount_success(self, mock_enable):
        """Test create_aws_cloud_account success."""
        util.create_aws_cloud_account(
            self.user, self.arn, self.name, self.auth_id, self.app_id, self.source_id
        )

        mock_enable.assert_called()

    @patch("api.error_codes.sources.notify_application_availability")
    @patch.object(CloudAccount, "enable")
    def test_create_aws_clount_fails_same_aws_account_different_arn(
        self, mock_enable, mock_notify_sources
    ):
        """
        Test create_aws_cloud_account fails with same ARN and different AWS Account.

        If we ever change cloudigrade to support multiple ARNs in the same AWS Account,
        this test and its underlying logic must be rewritten.
        """
        util.create_aws_cloud_account(
            self.user, self.arn, self.name, self.auth_id, self.app_id, self.source_id
        )

        other_name = self.name = _faker.word()
        other_arn = util_helper.generate_dummy_arn(
            account_id=self.aws_account_id, resource=_faker.word()
        )
        self.assertNotEqual(self.arn, other_arn)

        with self.assertRaises(ValidationError) as raise_context:
            util.create_aws_cloud_account(
                self.user,
                other_arn,
                other_name,
                self.auth_id,
                self.app_id,
                self.source_id,
            )
        exception_detail = raise_context.exception.detail
        self.assertIn("account_arn", exception_detail)
        self.assertIn(
            "Could not set up cloud metering.", exception_detail["account_arn"]
        )
        self.assertIn("CG1002", exception_detail["account_arn"])

    @patch("api.error_codes.sources.notify_application_availability")
    @patch.object(CloudAccount, "enable")
    def test_create_aws_clount_fails_with_same_arn_different_user(
        self, mock_enable, mock_notify_sources
    ):
        """Test create_aws_cloud_account fails with same ARN and a different user."""
        util.create_aws_cloud_account(
            self.user, self.arn, self.name, self.auth_id, self.app_id, self.source_id
        )

        other_user = util_helper.generate_test_user()
        other_name = self.name = _faker.word()

        with self.assertRaises(ValidationError) as raise_context:
            util.create_aws_cloud_account(
                other_user,
                self.arn,
                other_name,
                self.auth_id,
                self.app_id,
                self.source_id,
            )
        exception_detail = raise_context.exception.detail
        self.assertIn("account_arn", exception_detail)
        self.assertIn(
            "Could not set up cloud metering.", exception_detail["account_arn"]
        )
        self.assertNotIn("CG1002", exception_detail["account_arn"])

    @patch("api.error_codes.sources.notify_application_availability")
    @patch.object(CloudAccount, "enable")
    def test_create_aws_clount_fails_with_same_user_same_name(
        self, mock_enable, mock_notify_sources
    ):
        """Test create_aws_cloud_account fails with same name different platform IDs."""
        # The first call just creates the existing objects.
        util.create_aws_cloud_account(
            self.user, self.arn, self.name, self.auth_id, self.app_id, self.source_id
        )

        other_arn = util_helper.generate_dummy_arn()
        other_auth_id = _faker.pyint()
        other_app_id = _faker.pyint()
        other_source_id = _faker.pyint()

        with self.assertRaises(ValidationError) as raise_context:
            util.create_aws_cloud_account(
                self.user,
                other_arn,
                self.name,
                other_auth_id,
                other_app_id,
                other_source_id,
            )
        exception_detail = raise_context.exception.detail
        self.assertIn("name", exception_detail)
        self.assertIn("Could not set up cloud metering.", exception_detail["name"])
        self.assertIn("CG1003", exception_detail["name"])

    @patch("api.error_codes.sources.notify_application_availability")
    @patch.object(CloudAccount, "enable")
    def test_create_aws_clount_fails_with_same_arn_same_user(
        self, mock_enable, mock_notify_sources
    ):
        """Test create_aws_cloud_account failure message for same user."""
        util.create_aws_cloud_account(
            self.user, self.arn, self.name, self.auth_id, self.app_id, self.source_id
        )

        other_name = self.name = _faker.word()
        with self.assertRaises(ValidationError) as raise_context:
            util.create_aws_cloud_account(
                self.user,
                self.arn,
                other_name,
                self.auth_id,
                self.app_id,
                self.source_id,
            )
        exception_detail = raise_context.exception.detail
        self.assertIn("account_arn", exception_detail)
        self.assertIn(
            "Could not set up cloud metering.", exception_detail["account_arn"]
        )
        self.assertIn("CG1001", exception_detail["account_arn"])

    @patch("api.error_codes.sources.notify_application_availability")
    @patch.object(CloudAccount, "enable")
    def test_create_aws_clount_fails_with_different_user_same_account_id(
        self, mock_enable, mock_notify_sources
    ):
        """Test create_aws_cloud_account failure message for different user."""
        # The first call just creates the existing objects.
        util.create_aws_cloud_account(
            self.user, self.arn, self.name, self.auth_id, self.app_id, self.source_id
        )

        other_arn = util_helper.generate_dummy_arn(
            account_id=self.aws_account_id, resource=_faker.word()
        )
        other_auth_id = _faker.pyint()
        other_app_id = _faker.pyint()
        other_source_id = _faker.pyint()
        other_user = util_helper.generate_test_user()

        with self.assertRaises(ValidationError) as raise_context:
            util.create_aws_cloud_account(
                other_user,
                other_arn,
                self.name,
                other_auth_id,
                other_app_id,
                other_source_id,
            )
        exception_detail = raise_context.exception.detail
        self.assertIn(
            "Could not set up cloud metering.", exception_detail["account_arn"]
        )
        self.assertNotIn("CG1002", exception_detail["account_arn"])
