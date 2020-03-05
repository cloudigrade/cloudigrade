"""Collection of tests for tasks.update_from_sources_kafka_message."""
from unittest.mock import patch

import faker
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

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

        self.clount = api_helper.generate_aws_account(
            arn=self.arn, authentication_id=self.authentication_id
        )
        self.account_number = str(_faker.pyint())
        self.user = User.objects.create(username=self.account_number)

    @patch("util.insights.get_sources_endpoint")
    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_success(
        self, mock_update_account, mock_get_auth, mock_get_endpoint
    ):
        """Assert update_from_source_kafka_message happy path success."""
        username = _faker.user_name()
        endpoint_id = _faker.pyint()
        source_id = _faker.pyint()

        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, username, self.authentication_id
        )
        mock_get_auth.return_value = {
            "password": self.arn,
            "username": username,
            "resource_type": "Endpoint",
            "resource_id": endpoint_id,
            "id": self.authentication_id,
            "authtype": settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE,
        }
        mock_get_endpoint.return_value = {"id": endpoint_id, "source_id": source_id}

        tasks.update_from_source_kafka_message(message, headers)

        mock_update_account.assert_called_with(
            self.clount,
            self.arn,
            self.account_number,
            self.authentication_id,
            endpoint_id,
            source_id,
        )

    @patch("util.insights.get_sources_endpoint")
    @patch("util.insights.get_sources_authentication")
    def test_update_from_sources_kafka_message_updates_arn(
        self, mock_get_auth, mock_get_endpoint
    ):
        """Assert update_from_source_kafka_message updates the arn on the clount."""
        username = _faker.user_name()
        endpoint_id = _faker.pyint()
        source_id = _faker.pyint()

        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, username, self.authentication_id
        )
        new_arn = util_helper.generate_dummy_arn(account_id=self.account_id)
        mock_get_auth.return_value = {
            "password": new_arn,
            "username": username,
            "resource_type": "Endpoint",
            "resource_id": endpoint_id,
            "id": self.authentication_id,
            "authtype": settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE,
        }
        mock_get_endpoint.return_value = {"id": endpoint_id, "source_id": source_id}

        tasks.update_from_source_kafka_message(message, headers)
        self.assertEqual(self.clount.content_object.account_arn, new_arn)

    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_fail_missing_message_data(
        self, mock_update_account
    ):
        """Assert update_from_source_kafka_message fails from missing data."""
        message = {}
        headers = []
        tasks.update_from_source_kafka_message(message, headers)

        mock_update_account.assert_not_called()

    @patch("util.insights.get_sources_endpoint")
    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.update_aws_cloud_account")
    def test_update_from_sources_kafka_message_fail_bad_authtype(
        self, mock_update_account, mock_get_auth, mock_get_endpoint
    ):
        """Assert update_from_source_kafka_message not called for invalid authtype."""
        username = _faker.user_name()
        endpoint_id = _faker.pyint()
        source_id = _faker.pyint()

        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, username, self.authentication_id
        )
        new_arn = util_helper.generate_dummy_arn(account_id=self.account_id)
        mock_get_auth.return_value = {
            "password": new_arn,
            "username": username,
            "resource_type": "Endpoint",
            "resource_id": endpoint_id,
            "id": self.authentication_id,
            "authtype": "INVALID",
        }
        mock_get_endpoint.return_value = {"id": endpoint_id, "source_id": source_id}

        tasks.update_from_source_kafka_message(message, headers)

        mock_update_account.assert_not_called()

    @patch("api.clouds.aws.tasks.configure_customer_aws_and_create_cloud_account")
    @patch("util.insights.get_sources_endpoint")
    @patch("util.insights.get_sources_authentication")
    def test_update_from_sources_kafka_message_new_aws_account_id(
        self, mock_get_auth, mock_get_endpoint, mock_create_clount
    ):
        """
        Assert the new cloud account created for new aws_account_id.

        A new CloudAccount will get created with the new arn. And the old
        CloudAccount will be removed.
        """
        username = _faker.user_name()
        endpoint_id = _faker.pyint()
        source_id = _faker.pyint()

        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, username, self.authentication_id
        )
        new_account_id = util_helper.generate_dummy_aws_account_id()
        new_arn = util_helper.generate_dummy_arn(account_id=new_account_id)

        mock_get_auth.return_value = {
            "password": new_arn,
            "username": username,
            "resource_type": "Endpoint",
            "resource_id": endpoint_id,
            "id": self.authentication_id,
            "authtype": settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE,
        }
        mock_get_endpoint.return_value = {"id": endpoint_id, "source_id": source_id}

        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "disable_cloudtrail"
        ):
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = util_helper.generate_dummy_role()
            tasks.update_from_source_kafka_message(message, headers)

        self.assertFalse(CloudAccount.objects.filter(id=self.clount.id).exists())

        mock_create_clount.delay.assert_called()

    @patch("api.tasks.update_aws_cloud_account")
    def test_update_non_cloudmeter_authid_does_nothing(self, mock_update_account):
        """Assert that nothing happens if update is called on an unknown authid."""
        username = _faker.user_name()
        new_authentication_id = _faker.pyint()

        message, headers = util_helper.generate_authentication_create_message_value(
            self.account_number, username, new_authentication_id
        )
        tasks.update_from_source_kafka_message(message, headers)
        mock_update_account.assert_not_called()
