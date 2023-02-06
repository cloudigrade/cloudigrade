"""Collection of tests for tasks.delete_from_sources_kafka_message."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api.clouds.aws import models as aws_models
from api.models import CloudAccount
from api.tasks import sources
from api.tests import helper as api_helper
from util.aws import sts
from util.tests import helper as util_helper

_faker = faker.Faker()


class DeleteFromSourcesKafkaMessageTest(TestCase):
    """Celery task 'delete_from_sources_kafka_message' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.application_id = _faker.pyint()
        self.application_authentication_id = _faker.pyint()
        self.authentication_id = _faker.pyint()
        self.source_id = _faker.pyint()

        self.account = api_helper.generate_cloud_account(
            platform_authentication_id=self.authentication_id,
            platform_application_id=self.application_id,
            platform_source_id=self.source_id,
        )
        self.user = self.account.user

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_from_sources_kafka_message_application_authentication_success(
        self, mock_notify_sources
    ):
        """Assert removing CloudAccount via ApplicationAuthentication.destroy."""
        self.assertEqual(CloudAccount.objects.count(), 1)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 1)

        account_number = str(self.user.account_number)
        org_id = None
        (
            message,
            headers,
        ) = util_helper.generate_applicationauthentication_create_message_value(
            account_number,
            platform_id=self.application_authentication_id,
            application_id=self.application_id,
            authentication_id=self.authentication_id,
        )

        expected_logger_infos = [
            "INFO:api.tasks.sources:delete_from_sources_kafka_message "
            f"for account_number {account_number}, "
            f"org_id {org_id}, "
            f"platform_id {self.application_authentication_id}",
            "INFO:api.tasks.sources:Deleting CloudAccounts using filter "
            f"(AND: ('platform_application_id', {self.application_id}), "
            f"('platform_authentication_id', {self.authentication_id}))",
        ]

        with patch.object(sts, "boto3") as mock_boto3, self.assertLogs(
            "api.tasks.sources", level="INFO"
        ) as logging_watcher:
            role = util_helper.generate_dummy_role()
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = role

            sources.delete_from_sources_kafka_message(message, headers)
            for index, expected_logger_info in enumerate(expected_logger_infos):
                self.assertEqual(expected_logger_info, logging_watcher.output[index])
        self.assertEqual(CloudAccount.objects.count(), 0)
        self.assertEqual(aws_models.AwsCloudAccount.objects.count(), 0)
        mock_notify_sources.delay.assert_called()

    def test_delete_from_sources_kafka_message_fail_missing_message_data(self):
        """Assert delete_from_sources_kafka_message fails from missing data."""
        self.assertEqual(CloudAccount.objects.count(), 1)

        message = {}
        headers = []
        sources.delete_from_sources_kafka_message(message, headers)

        # Delete should not have been called.
        self.assertEqual(CloudAccount.objects.count(), 1)

    def test_delete_from_sources_kafka_message_fail_wrong_account_number(self):
        """Assert delete fails from mismatched data."""
        self.assertEqual(CloudAccount.objects.count(), 1)
        account_number = _faker.user_name()
        application_id = _faker.pyint()
        authentication_id = _faker.pyint()
        application_authentication_id = _faker.pyint()
        (
            message,
            headers,
        ) = util_helper.generate_applicationauthentication_create_message_value(
            account_number,
            platform_id=application_authentication_id,
            application_id=application_id,
            authentication_id=authentication_id,
        )

        sources.delete_from_sources_kafka_message(message, headers)

        # Delete should not have been called.
        self.assertEqual(CloudAccount.objects.count(), 1)

    def test_delete_from_sources_kafka_message_fail_no_cloud_account(self):
        """Assert delete fails from nonexistent cloud account."""
        self.assertEqual(CloudAccount.objects.count(), 1)

        account_number = str(self.user.account_number)
        application_id = _faker.pyint()
        authentication_id = _faker.pyint()
        application_authentication_id = _faker.pyint()
        (
            message,
            headers,
        ) = util_helper.generate_applicationauthentication_create_message_value(
            account_number,
            platform_id=application_authentication_id,
            application_id=application_id,
            authentication_id=authentication_id,
        )

        sources.delete_from_sources_kafka_message(message, headers)

        # Delete should not have been called.
        self.assertEqual(CloudAccount.objects.count(), 1)
