"""Collection of tests for tasks.delete_from_sources_kafka_message."""
from unittest.mock import patch

import faker
from django.conf import settings
from django.test import TestCase

from api import tasks
from api.clouds.aws import models as aws_models
from api.models import CloudAccount
from api.tests import helper as api_helper
from util.aws import sts
from util.tests import helper as util_helper

_faker = faker.Faker()


class DeleteFromSourcesKafkaMessageTest(TestCase):
    """Celery task 'delete_from_sources_kafka_message' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.authentication_id = _faker.pyint()
        self.application_id = _faker.pyint()
        self.endpoint_id = _faker.pyint()
        self.source_id = _faker.pyint()

        self.account = api_helper.generate_aws_account(
            platform_authentication_id=self.authentication_id,
            platform_application_id=self.application_id,
            platform_endpoint_id=self.endpoint_id,
            platform_source_id=self.source_id,
        )
        self.user = self.account.user

    @patch("api.models.notify_sources_application_availability")
    def test_delete_from_sources_kafka_message_success(self, mock_notify_sources):
        """Assert delete_from_sources_kafka_message happy path success."""
        account_number = str(self.user.username)
        username = _faker.user_name()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username, platform_id=self.authentication_id
        )
        self.assertGreaterEqual(CloudAccount.objects.count(), 0)
        self.assertGreaterEqual(aws_models.AwsCloudAccount.objects.count(), 0)

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_disable_cloudtrail"
        ):
            role = util_helper.generate_dummy_role()
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role

            tasks.delete_from_sources_kafka_message(
                message, headers, settings.AUTHENTICATION_DESTROY_EVENT
            )
        self.assertEqual(CloudAccount.objects.count(), 0)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 0)
        mock_notify_sources.assert_called()

    @patch("api.models.CloudAccount.delete")
    def test_delete_from_sources_kafka_message_fail_missing_message_data(
        self, mock_clount_delete
    ):
        """Assert delete_from_sources_kafka_message fails from missing data."""
        message = {}
        headers = []
        tasks.delete_from_sources_kafka_message(
            message, headers, settings.AUTHENTICATION_DESTROY_EVENT
        )

        # Delete should not have been called.
        mock_clount_delete.assert_not_called()

    @patch("api.models.CloudAccount.delete")
    def test_delete_from_sources_kafka_message_fail_wrong_account_number(
        self, mock_clount_delete
    ):
        """Assert delete fails from mismatched data."""
        account_number = _faker.user_name()
        username = _faker.user_name()
        authentication_id = _faker.pyint()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )

        tasks.delete_from_sources_kafka_message(
            message, headers, settings.AUTHENTICATION_DESTROY_EVENT
        )

        # Delete should not have been called.
        mock_clount_delete.assert_not_called()

    @patch("api.models.CloudAccount.delete")
    def test_delete_from_sources_kafka_message_fail_no_clount(self, mock_clount_delete):
        """Assert delete fails from nonexistent clount."""
        account_number = str(self.user.username)
        username = _faker.user_name()
        authentication_id = _faker.pyint()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )

        tasks.delete_from_sources_kafka_message(
            message, headers, settings.AUTHENTICATION_DESTROY_EVENT
        )

        # Delete should not have been called.
        mock_clount_delete.assert_not_called()

    @patch("api.models.notify_sources_application_availability")
    def test_delete_endpoint_from_sources_kafka_message_success(
        self, mock_notify_sources
    ):
        """Assert delete_from_sources_kafka_message with endpoint delete success."""
        account_number = str(self.user.username)
        username = _faker.user_name()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username, platform_id=self.endpoint_id
        )
        self.assertGreaterEqual(CloudAccount.objects.count(), 0)
        self.assertGreaterEqual(aws_models.AwsCloudAccount.objects.count(), 0)

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_disable_cloudtrail"
        ):
            role = util_helper.generate_dummy_role()
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role

            tasks.delete_from_sources_kafka_message(
                message, headers, settings.ENDPOINT_DESTROY_EVENT
            )
        self.assertEqual(CloudAccount.objects.count(), 0)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 0)

    @patch("api.models.notify_sources_application_availability")
    def test_delete_source_from_sources_kafka_message_success(
        self, mock_notify_sources
    ):
        """Assert delete_from_sources_kafka_message with source delete success."""
        account_number = str(self.user.username)
        username = _faker.user_name()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username, platform_id=self.source_id
        )
        self.assertGreaterEqual(CloudAccount.objects.count(), 0)
        self.assertGreaterEqual(aws_models.AwsCloudAccount.objects.count(), 0)

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_disable_cloudtrail"
        ):
            role = util_helper.generate_dummy_role()
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role

            tasks.delete_from_sources_kafka_message(
                message, headers, settings.SOURCE_DESTROY_EVENT
            )
        self.assertEqual(CloudAccount.objects.count(), 0)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 0)

    def test_delete_fails_unsupported_event_type(self):
        """Assert delete_from_sources_kafka_message fails for bad event type."""
        account_number = str(self.user.username)
        username = _faker.user_name()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username
        )
        self.assertGreaterEqual(CloudAccount.objects.count(), 0)
        self.assertGreaterEqual(aws_models.AwsCloudAccount.objects.count(), 0)

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_disable_cloudtrail"
        ):
            role = util_helper.generate_dummy_role()
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role

            tasks.delete_from_sources_kafka_message(message, headers, "BAD EVENT")
        self.assertEqual(CloudAccount.objects.count(), 1)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 1)

    @patch("api.models.notify_sources_application_availability")
    def test_delete_application_from_sources_kafka_message_success(
        self, mock_notify_sources
    ):
        """Assert application delete remove clount."""
        account_number = str(self.user.username)
        username = _faker.user_name()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username, platform_id=self.application_id
        )
        self.assertGreaterEqual(CloudAccount.objects.count(), 0)
        self.assertGreaterEqual(aws_models.AwsCloudAccount.objects.count(), 0)

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_disable_cloudtrail"
        ):
            role = util_helper.generate_dummy_role()
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role

            tasks.delete_from_sources_kafka_message(
                message, headers, settings.APPLICATION_DESTROY_EVENT
            )
        self.assertEqual(CloudAccount.objects.count(), 0)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 0)

    @patch("api.models.notify_sources_application_availability")
    def test_delete_application_authentication_from_sources_kafka_message_success(
        self, mock_notify_sources
    ):
        """Assert application_authentication delete remove clount."""
        account_number = str(self.user.username)
        (
            message,
            headers,
        ) = util_helper.generate_applicationauthentication_create_message_value(
            account_number,
            application_id=self.application_id,
            authentication_id=self.authentication_id,
        )
        self.assertGreaterEqual(CloudAccount.objects.count(), 0)
        self.assertGreaterEqual(aws_models.AwsCloudAccount.objects.count(), 0)

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_disable_cloudtrail"
        ):
            role = util_helper.generate_dummy_role()
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role

            tasks.delete_from_sources_kafka_message(
                message, headers, settings.APPLICATION_AUTHENTICATION_DESTROY_EVENT
            )
        self.assertEqual(CloudAccount.objects.count(), 0)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 0)
        mock_notify_sources.assert_called()
