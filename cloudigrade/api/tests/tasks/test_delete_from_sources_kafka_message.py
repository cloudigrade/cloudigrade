"""Collection of tests for tasks.delete_from_sources_kafka_message."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api import tasks
from api.models import CloudAccount
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class DeleteFromSourcesKafkaMessageTest(TestCase):
    """Celery task 'delete_from_sources_kafka_message' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.account = api_helper.generate_aws_account()
        self.user = self.account.user

    @patch('api.models.CloudAccount.delete')
    def test_delete_from_sources_kafka_message_success(
            self, mock_clount_delete
    ):
        """Assert delete_from_sources_kafka_message happy path success."""
        account_number = str(self.user.username)
        username = self.account.content_object.aws_access_key_id
        authentication_id = _faker.pyint()
        message = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )

        tasks.delete_from_sources_kafka_message(message)
        mock_clount_delete.assert_called_once()

    @patch('api.models.CloudAccount.delete')
    def test_delete_from_sources_kafka_message_fail_missing_message_data(
        self, mock_clount_delete
    ):
        """Assert delete_from_sources_kafka_message fails from missing data."""
        message = {}
        tasks.delete_from_sources_kafka_message(message)

        # Delete should not have been called.
        mock_clount_delete.assert_not_called()

    @patch('api.models.CloudAccount.delete')
    def test_delete_from_sources_kafka_message_fail_wrong_account_number(
        self, mock_clount_delete
    ):
        """Assert delete fails from mismatched data."""
        account_number = _faker.user_name()
        username = self.account.content_object.aws_access_key_id
        authentication_id = _faker.pyint()
        message = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )

        tasks.delete_from_sources_kafka_message(message)

        # Delete should not have been called.
        mock_clount_delete.assert_not_called()

    @patch('api.models.CloudAccount.delete')
    def test_delete_from_sources_kafka_message_fail_no_clount(
        self, mock_clount_delete
    ):
        """Assert delete fails from nonexistent clount."""
        account_number = str(self.user.username)
        username = _faker.user_name()
        authentication_id = _faker.pyint()
        message = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )

        tasks.delete_from_sources_kafka_message(message)

        # Delete should not have been called.
        mock_clount_delete.assert_not_called()

    @patch('api.models.AwsCloudAccount.cloud_account')
    @patch('api.models.AwsCloudAccount.delete')
    def test_delete_from_sources_kafka_message_fail_no_clount_with_aws_clount(
        self, mock_aws_clount_delete, mock_aws_clount_clount
    ):
        """Assert delete fails for aws clount with no parent."""
        mock_aws_clount_clount.get.side_effect = CloudAccount.DoesNotExist()

        account_number = str(self.user.username)
        username = self.account.content_object.aws_access_key_id
        authentication_id = _faker.pyint()
        message = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )

        tasks.delete_from_sources_kafka_message(message)
        mock_aws_clount_delete.assert_called_once()
