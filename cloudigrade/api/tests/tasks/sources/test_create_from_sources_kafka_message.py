"""Collection of tests for tasks.create_from_sources_kafka_message."""
import uuid
from unittest.mock import patch

import faker
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from api.tasks import sources
from util.exceptions import SourcesAPINotOkStatus
from util.tests import helper as util_helper

_faker = faker.Faker()


class CreateFromSourcesKafkaMessageTest(TestCase):
    """Celery task 'create_from_sources_kafka_message' test cases."""

    def setUp(self):
        """Set up shared values for kafka creation tests."""
        self.account_number = str(_faker.pyint())
        self.org_id = str(_faker.pyint())
        self.username = _faker.user_name()
        self.authentication_id = _faker.pyint()
        self.application_id = _faker.pyint()
        self.source_id = _faker.pyint()
        self.cloudigrade_sources_app_id = _faker.pyint()
        (
            self.message,
            self.headers,
        ) = util_helper.generate_applicationauthentication_create_message_value(
            account_number=self.account_number,
            application_id=self.application_id,
            authentication_id=self.authentication_id,
        )

        self.arn = util_helper.generate_dummy_arn()
        self.subscription_id = uuid.uuid4()

        self.auth_return_value = {
            "username": self.arn,
            "resource_type": settings.SOURCES_RESOURCE_TYPE,
            "resource_id": self.application_id,
            "id": self.authentication_id,
            "authtype": settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE,
        }
        self.auth_azure_return_value = {
            "username": self.subscription_id,
            "resource_type": settings.SOURCES_RESOURCE_TYPE,
            "resource_id": self.application_id,
            "id": self.authentication_id,
            "authtype": settings.SOURCES_CLOUDMETER_LIGHTHOUSE_AUTHTYPE,
        }

    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_aws_success(
        self,
        mock_task,
        mock_get_app,
        mock_get_app_type_id,
        mock_get_auth,
    ):
        """Assert create_from_sources_kafka_message aws happy path success."""
        mock_get_app.return_value = {
            "application_type_id": self.cloudigrade_sources_app_id,
            "source_id": self.source_id,
        }
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id

        arn = util_helper.generate_dummy_arn()

        self.auth_return_value["username"] = arn
        mock_get_auth.return_value = self.auth_return_value
        sources.create_from_sources_kafka_message(self.message, self.headers)

        user = User.objects.get(username=self.account_number)
        mock_task.delay.assert_called_with(
            user.username,
            arn,
            self.authentication_id,
            self.application_id,
            self.source_id,
        )

    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.check_azure_subscription_and_create_cloud_account")
    def test_create_from_sources_kafka_message_azure_success(
        self,
        mock_task,
        mock_get_app,
        mock_get_app_type_id,
        mock_get_auth,
    ):
        """Assert create_from_sources_kafka_message azure happy path success."""
        mock_get_app.return_value = {
            "application_type_id": self.cloudigrade_sources_app_id,
            "source_id": self.source_id,
        }
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id

        mock_get_auth.return_value = self.auth_azure_return_value
        sources.create_from_sources_kafka_message(self.message, self.headers)

        user = User.objects.get(username=self.account_number)
        mock_task.delay.assert_called_with(
            user.username,
            self.subscription_id,
            self.authentication_id,
            self.application_id,
            self.source_id,
        )

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_aws_task_not_called_for_missing_application_id(
        self, mock_task, mock_get_application
    ):
        """Assert early exit if application_id not in message."""
        self.message["application_id"] = None
        sources.create_from_sources_kafka_message(self.message, self.headers)
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()
        mock_get_application.assert_not_called()

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_aws_task_not_called_for_missing_authentication_id(
        self, mock_task, mock_get_application
    ):
        """Assert early exit if authentication_id not in message."""
        self.message["authentication_id"] = None
        sources.create_from_sources_kafka_message(self.message, self.headers)
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()
        mock_get_application.assert_not_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_aws_task_not_called_for_unsupported_authtype(
        self,
        mock_task,
        mock_get_app,
        mock_get_app_type_id,
        mock_get_auth,
        mock_notify_sources,
    ):
        """Assert no account gets created for unsupported authtype."""
        mock_get_app.return_value = {
            "application_type_id": self.cloudigrade_sources_app_id
        }
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id
        self.auth_return_value["authtype"] = "INVALID"
        mock_get_auth.return_value = self.auth_return_value
        sources.create_from_sources_kafka_message(self.message, self.headers)
        mock_task.delay.assert_not_called()

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_fail_source_unexpected_response(
        self, mock_task, mock_get_app
    ):
        """
        Assert create_from_sources_kafka_message fails from not-200/404 source reply.

        This could happen if the sources API is misbehaving unexpectedly.
        """
        mock_get_app.side_effect = SourcesAPINotOkStatus

        with self.assertRaises(SourcesAPINotOkStatus):
            sources.create_from_sources_kafka_message(self.message, self.headers)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_returns_early_when_application_404(
        self, mock_task, mock_get_app
    ):
        """
        Assert create_from_sources_kafka_message returns if sources application 404s.

        This could happen if the application has been deleted from the
        sources API by the time this task runs.
        """
        mock_get_app.return_value = None

        sources.create_from_sources_kafka_message(self.message, self.headers)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_returns_early_when_authentication_404(
        self,
        mock_task,
        mock_get_app,
        mock_get_app_type_id,
        mock_get_auth,
        mock_notify_sources,
    ):
        """
        Assert create_from_sources_kafka_message returns if sources authentication 404s.

        This could happen if the authentication has been deleted from the
        sources API by the time this task runs.
        """
        mock_get_app.return_value = {
            "application_type_id": self.cloudigrade_sources_app_id
        }
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id
        mock_get_auth.return_value = None
        sources.create_from_sources_kafka_message(self.message, self.headers)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_create_returns_early_when_resource_type_invalid(
        self,
        mock_task,
        mock_get_app,
        mock_get_app_type_id,
        mock_get_auth,
        mock_notify_sources,
    ):
        """Assert task returns if resource_type is invalid."""
        mock_get_app.return_value = {
            "application_type_id": self.cloudigrade_sources_app_id
        }
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id

        self.auth_return_value["resource_type"] = "INVALID"
        mock_get_auth.return_value = self.auth_return_value

        sources.create_from_sources_kafka_message(self.message, self.headers)
        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_create_fails_if_no_password_or_username(
        self,
        mock_task,
        mock_get_app,
        mock_get_app_type_id,
        mock_get_auth,
        mock_notify_sources,
    ):
        """Assert create_from_sources_kafka_message fails if auth has no password."""
        mock_get_app.return_value = {
            "application_type_id": self.cloudigrade_sources_app_id
        }
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id

        self.auth_return_value.pop("username", None)
        self.auth_return_value.pop("password", None)
        mock_get_auth.return_value = self.auth_return_value
        sources.create_from_sources_kafka_message(self.message, self.headers)

        mock_task.delay.assert_not_called()

    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_early_exit_if_app_type_is_not_cloudigrade(
        self, mock_task, mock_get_app, mock_get_app_type_id, mock_get_auth
    ):
        """Assert create_from_sources_kafka_message happy path success."""
        mock_get_app.return_value = {"application_type_id": "INVALID"}
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id

        sources.create_from_sources_kafka_message(self.message, self.headers)
        mock_get_auth.assert_not_called()

        mock_task.delay.assert_not_called()

    @patch("util.redhatcloud.sources.get_authentication")
    @patch("util.redhatcloud.sources.get_cloudigrade_application_type_id")
    @patch("util.redhatcloud.sources.get_application")
    @patch("api.tasks.sources.configure_customer_aws_and_create_cloud_account")
    def test_create_uses_arn_from_password_if_no_username(
        self,
        mock_task,
        mock_get_app,
        mock_get_app_type_id,
        mock_get_auth,
    ):
        """Assert create_from_sources_kafka_message happy path success."""
        mock_get_app.return_value = {
            "application_type_id": self.cloudigrade_sources_app_id,
            "source_id": self.source_id,
        }
        mock_get_app_type_id.return_value = self.cloudigrade_sources_app_id

        arn = util_helper.generate_dummy_arn()
        self.auth_return_value.pop("username", None)
        self.auth_return_value["password"] = arn

        mock_get_auth.return_value = self.auth_return_value
        sources.create_from_sources_kafka_message(self.message, self.headers)

        user = User.objects.get(username=self.account_number)
        mock_task.delay.assert_called_with(
            user.username,
            arn,
            self.authentication_id,
            self.application_id,
            self.source_id,
        )
