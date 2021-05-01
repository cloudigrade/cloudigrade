"""Collection of tests for api.cloud.aws.util.update_aws_cloud_account."""
from unittest.mock import patch

import faker
from django.test import TestCase


from api.clouds.aws import util
from api.clouds.aws.models import AwsCloudAccount
from api.models import CloudAccount, Instance
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

    @patch("cloudigrade.api.tasks.notify_application_availability_task")
    def test_update_aws_clount_notifies_sources_invalid_arn(self, mock_notify_sources):
        """Test update_aws_cloud_account notifies sources if ARN is invalid."""
        util.update_aws_cloud_account(
            self.clount, "INVALID", self.account_number, self.auth_id, self.source_id
        )
        mock_notify_sources.delay.assert_called()

    @patch("cloudigrade.api.tasks.notify_application_availability_task")
    @patch.object(CloudAccount, "disable")
    @patch.object(CloudAccount, "enable")
    def test_update_aws_clount_different_aws_account_id_success(
        self,
        mock_enable,
        mock_disable,
        mock_notify_sources,
    ):
        """Test update_aws_cloud_account works."""
        aws_account_id2 = util_helper.generate_dummy_aws_account_id()
        arn2 = util_helper.generate_dummy_arn(account_id=aws_account_id2)

        api_helper.generate_instance(self.clount)

        util.update_aws_cloud_account(
            self.clount, arn2, self.account_number, self.auth_id, self.source_id
        )
        self.assertTrue(AwsCloudAccount.objects.filter(account_arn=arn2).exists())
        self.assertEqual(0, Instance.objects.all().count())

    @patch("api.clouds.aws.util._notify_error_with_generic_message_for_different_user")
    @patch("cloudigrade.api.tasks.notify_application_availability_task")
    @patch.object(CloudAccount, "disable")
    @patch.object(CloudAccount, "enable")
    def test_update_aws_clount_different_aws_account_id_fails_arn_already_exists(
        self,
        mock_enable,
        mock_disable,
        mock_notify_sources,
        mock_notify_error,
    ):
        """Test update_aws_cloud_account fails for duplicate arn."""
        aws_account_id2 = util_helper.generate_dummy_aws_account_id()
        arn2 = util_helper.generate_dummy_arn(account_id=aws_account_id2)

        api_helper.generate_cloud_account(
            arn=arn2,
            aws_account_id=aws_account_id2,
        )

        util.update_aws_cloud_account(
            self.clount, arn2, self.account_number, self.auth_id, self.source_id
        )

        mock_notify_error.assert_called()

    @patch("api.clouds.aws.util._notify_error_with_generic_message_for_different_user")
    @patch("cloudigrade.api.tasks.notify_application_availability_task")
    @patch.object(CloudAccount, "disable")
    @patch.object(CloudAccount, "enable")
    def test_update_aws_clount_different_aws_account_id_fails_account_id_already_exists(
        self,
        mock_enable,
        mock_disable,
        mock_notify_sources,
        mock_notify_error,
    ):
        """Test update_aws_cloud_account fails for duplicate aws_account_id."""
        aws_account_id2 = util_helper.generate_dummy_aws_account_id()
        arn2 = util_helper.generate_dummy_arn(account_id=aws_account_id2)
        arn3 = util_helper.generate_dummy_arn(account_id=aws_account_id2)

        api_helper.generate_cloud_account(
            arn=arn2,
            aws_account_id=aws_account_id2,
        )

        util.update_aws_cloud_account(
            self.clount, arn3, self.account_number, self.auth_id, self.source_id
        )

        mock_notify_error.assert_called()
