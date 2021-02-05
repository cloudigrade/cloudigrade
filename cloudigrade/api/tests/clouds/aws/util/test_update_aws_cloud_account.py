"""Collection of tests for api.cloud.aws.util.update_aws_cloud_account."""
from unittest.mock import patch

import faker
from django.contrib.auth.models import User
from django.test import TestCase

from api.clouds.aws import util
from api.models import CloudAccount
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class UpdateAWSClountTest(TestCase):
    """Test cases for api.cloud.aws.util.update_aws_cloud_account."""

    def setUp(self):
        """Set up shared variables."""
        self.account_number = _faker.random_int(min=100000, max=999999)
        self.user = util_helper.generate_test_user(account_number=self.account_number)
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.arn = util_helper.generate_dummy_arn(account_id=self.aws_account_id)
        self.auth_id = _faker.pyint()
        self.app_id = _faker.pyint()
        self.source_id = _faker.pyint()

        self.clount = api_helper.generate_cloud_account(
            arn=self.arn,
            aws_account_id=self.aws_account_id,
            user=self.user,
            name=self.account_number,
            platform_authentication_id=self.auth_id,
            platform_application_id=self.app_id,
            platform_source_id=self.source_id,
        )

    @patch("api.error_codes.notify_sources_application_availability")
    def test_update_aws_clount_notifies_sources_invalid_arn(self, mock_notify_sources):
        """Test update_aws_cloud_account notifies sources if ARN is invalid."""
        util.update_aws_cloud_account(
            self.clount, "INVALID", self.account_number, self.auth_id, self.source_id
        )
        mock_notify_sources.assert_called()

    @patch("api.clouds.aws.tasks.configure_customer_aws_and_create_cloud_account")
    @patch("api.error_codes.notify_sources_application_availability")
    @patch.object(CloudAccount, "disable")
    @patch.object(CloudAccount, "enable")
    def test_update_aws_clount_different_aws_id_recreates_user(
        self,
        mock_enable,
        mock_disable,
        mock_notify_sources,
        mock_configure_and_create_clount,
    ):
        """Test update_aws_cloud_account creates a new user."""
        aws_account_id2 = util_helper.generate_dummy_aws_account_id()
        arn2 = util_helper.generate_dummy_arn(account_id=aws_account_id2)
        util.update_aws_cloud_account(
            self.clount, arn2, self.account_number, self.auth_id, self.source_id
        )
        self.assertEqual(1, User.objects.all().count())

        new_user = User.objects.get(username=self.account_number)
        self.assertNotEqual(self.user.id, new_user.id)
