"""Collection of tests for tasks.update_from_sources_kafka_message."""
from unittest.mock import patch

import faker
from django.conf import settings
from django.test import TestCase
from rest_framework.serializers import ValidationError

from api import tasks
from api.clouds.aws import models as aws_models
from api.models import CloudAccount
from api.tests import helper as api_helper
from util.aws import sts
from util.tests import helper as util_helper

_faker = faker.Faker()


class UpdateFromSourcesKafkaMessageTest(TestCase):
    """Celery task 'update_from_source_kafka_message' test cases."""

    def setUp(self):
        """Set up shared variables."""
        self.authentication_id = _faker.pyint()
        self.account_id = util_helper.generate_dummy_aws_account_id()
        self.arn = util_helper.generate_dummy_arn(account_id=self.account_id)

        self.clount = api_helper.generate_cloud_account(
            arn=self.arn, platform_authentication_id=self.authentication_id
        )

        self.username = _faker.user_name()
        self.application_id = _faker.pyint()
        self.source_id = _faker.pyint()

        self.account_number = str(_faker.pyint())

        self.auth_return_value = {
            "username": self.arn,
            "resource_type": settings.SOURCES_RESOURCE_TYPE,
            "resource_id": self.application_id,
            "id": self.authentication_id,
            "authtype": settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE,
        }
        self.app_return_value = {
            "source_id": self.source_id,
            "id": self.application_id,
        }

    @patch("util.redhatcloud.sources.get_application")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_success(
        self, mock_update_account, mock_get_auth, mock_get_app
    ):
        """Assert update_from_source_kafka_message happy path success."""
        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, self.authentication_id
        )
        mock_get_auth.return_value = self.auth_return_value
        mock_get_app.return_value = self.app_return_value

        tasks.update_from_source_kafka_message(message, headers)

        mock_update_account.assert_called_with(
            self.clount,
            self.arn,
            self.account_number,
            self.authentication_id,
            self.source_id,
        )

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    def test_update_from_sources_kafka_message_updates_arn(
        self, mock_get_auth, mock_notify_sources, mock_get_app
    ):
        """Assert update_from_source_kafka_message updates the arn on the clount."""
        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, self.authentication_id
        )
        new_arn = util_helper.generate_dummy_arn(account_id=self.account_id)
        self.auth_return_value["username"] = new_arn
        mock_get_auth.return_value = self.auth_return_value
        mock_get_app.return_value = self.app_return_value

        with patch("api.clouds.aws.util.verify_permissions") as mock_verify_permissions:
            mock_verify_permissions.return_value = True
            tasks.update_from_source_kafka_message(message, headers)
            mock_verify_permissions.assert_called()

        self.clount.refresh_from_db()
        self.assertEqual(self.clount.content_object.account_arn, new_arn)
        self.assertTrue(self.clount.is_enabled)
        mock_notify_sources.delay.assert_called()

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    def test_update_from_sources_kafka_message_updates_arn_but_disables_cloud_account(
        self, mock_get_auth, mock_notify_sources, mock_get_app
    ):
        """
        Assert update_from_source_kafka_message updates the arn and disables clount.

        This can happen if we get a well-formed ARN, but the AWS-side verification fails
        due to something like badly configured IAM Role or Policy. In this case, we do
        want to save the updated ARN, but we need to disable the Cloud Account until it
        can verify its permissions (at a later date).
        """
        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, self.authentication_id
        )
        new_arn = util_helper.generate_dummy_arn(account_id=self.account_id)
        self.auth_return_value["username"] = new_arn

        mock_get_auth.return_value = self.auth_return_value
        mock_get_app.return_value = self.app_return_value

        validation_error = ValidationError(detail={_faker.slug(): _faker.slug()})
        with patch("api.clouds.aws.util.verify_permissions") as mock_verify_permissions:
            mock_verify_permissions.side_effect = validation_error
            tasks.update_from_source_kafka_message(message, headers)
            mock_verify_permissions.assert_called()

        self.clount.refresh_from_db()
        self.assertEqual(self.clount.content_object.account_arn, new_arn)
        self.assertFalse(self.clount.is_enabled)

    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_fail_missing_message_data(
        self, mock_update_account
    ):
        """Assert update_from_source_kafka_message fails from missing data."""
        message = {}
        headers = []
        tasks.update_from_source_kafka_message(message, headers)

        mock_update_account.assert_not_called()

    @patch("util.redhatcloud.sources.get_application")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_fail_bad_authtype(
        self, mock_update_account, mock_get_auth, mock_get_app
    ):
        """Assert update_from_source_kafka_message not called for invalid authtype."""
        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, self.authentication_id
        )
        new_arn = util_helper.generate_dummy_arn(account_id=self.account_id)

        self.auth_return_value["username"] = new_arn
        self.auth_return_value["authtype"] = "INVALID"
        mock_get_auth.return_value = self.auth_return_value
        mock_get_app.return_value = self.app_return_value

        tasks.update_from_source_kafka_message(message, headers)
        mock_update_account.assert_not_called()

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch.object(CloudAccount, "enable")
    def test_update_from_sources_kafka_message_new_aws_account_id(
        self, mock_enable, mock_get_auth, mock_notify_sources, mock_get_app
    ):
        """
        Assert the new cloud account created for new aws_account_id.

        A new CloudAccount will get created with the new arn. And the old
        CloudAccount will be removed.
        """
        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, self.authentication_id
        )
        new_account_id = util_helper.generate_dummy_aws_account_id()
        new_arn = util_helper.generate_dummy_arn(account_id=new_account_id)

        self.auth_return_value["username"] = new_arn
        mock_get_auth.return_value = self.auth_return_value
        mock_get_app.return_value = self.app_return_value

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_delete_cloudtrail"
        ), patch("api.clouds.aws.util.verify_permissions"):
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = util_helper.generate_dummy_role()
            tasks.update_from_source_kafka_message(message, headers)

        mock_enable.assert_called()

    @patch("api.tasks.sources.list_application_authentications")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_non_cloudmeter_authid_does_nothing(
        self, mock_update_account, mock_list_sources_app_auths
    ):
        """Assert that nothing happens if update is called on an unknown authid."""
        new_authentication_id = _faker.pyint()
        mock_list_sources_app_auths.return_value = {
            "data": [],
            "meta": {
                "count": 0,
            },
        }

        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, new_authentication_id
        )
        tasks.update_from_source_kafka_message(message, headers)
        mock_update_account.assert_not_called()

    @patch("api.tasks.sources.list_application_authentications")
    @patch("api.tasks.create_from_sources_kafka_message")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_fixed_cloudmeter_authid_succeeds(
        self, mock_update_account, mock_create_account, mock_list_sources_app_auths
    ):
        """Assert that updating an unknown Auth obj meant for us creates account."""
        new_authentication_id = _faker.pyint()
        app_auth_data = {
            "application_id": "1001",
            "authentication_id": "2001",
            "created_at": "2020-05-10T17:06:10Z",
            "id": "100",
            "tenant": "100001",
            "updated_at": "2020-05-10T17:06:10Z",
        }
        mock_list_sources_app_auths.return_value = {
            "data": [
                app_auth_data,
            ],
            "meta": {
                "count": 1,
            },
        }

        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, new_authentication_id
        )
        tasks.update_from_source_kafka_message(message, headers)
        mock_create_account.delay.assert_called_once_with(app_auth_data, headers)
        mock_update_account.assert_not_called()

    @patch("util.redhatcloud.sources.get_authentication")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_returns_early_when_authentication_404(
        self, mock_update_account, mock_get_auth
    ):
        """
        Assert update_from_sources_kafka_message returns if sources authentication 404s.

        This could happen if the authentication has been deleted from the
        sources API by the time this task runs.
        """
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number=self.account_number, platform_id=self.authentication_id
        )
        mock_get_auth.return_value = None

        tasks.update_from_source_kafka_message(message, headers)
        mock_get_auth.assert_called()
        mock_update_account.delay.assert_not_called()

    @patch("util.redhatcloud.sources.get_authentication")
    @patch("api.tasks.update_aws_cloud_account")
    def test_create_returns_early_when_resource_type_invalid(
        self, mock_update_account, mock_get_auth
    ):
        """Assert task returns if resource_type is invalid."""
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number=self.account_number, platform_id=self.authentication_id
        )
        mock_get_auth.return_value = {
            "resource_id": _faker.pyint(),
            "resource_type": "INVALID",
        }

        tasks.update_from_source_kafka_message(message, headers)

        mock_update_account.delay.assert_not_called()

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    def test_arn_from_password_if_no_username(
        self, mock_get_auth, mock_notify_sources, mock_get_app
    ):
        """Assert update gets the arn from the password field if username DNE."""
        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, self.authentication_id
        )
        new_arn = util_helper.generate_dummy_arn(account_id=self.account_id)

        self.auth_return_value.pop("username", None)
        self.auth_return_value["password"] = new_arn

        mock_get_auth.return_value = self.auth_return_value
        mock_get_app.return_value = self.app_return_value

        with patch("api.clouds.aws.util.verify_permissions") as mock_verify_permissions:
            mock_verify_permissions.return_value = True
            tasks.update_from_source_kafka_message(message, headers)
            mock_verify_permissions.assert_called()

        self.clount.refresh_from_db()
        self.assertEqual(self.clount.content_object.account_arn, new_arn)
        self.assertTrue(self.clount.is_enabled)
        mock_notify_sources.delay.assert_called()

    @patch("api.tasks.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_application")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_blank_arn_notifies_sources(
        self, mock_update_account, mock_get_auth, mock_get_app, mock_notify_sources
    ):
        """Assert that sources is notified if ARN is blank."""
        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, self.username, self.authentication_id
        )
        self.auth_return_value["username"] = ""
        mock_get_auth.return_value = self.auth_return_value
        mock_get_app.return_value = self.app_return_value

        tasks.update_from_source_kafka_message(message, headers)

        mock_update_account.assert_not_called()
        mock_notify_sources.delay.assert_called()
