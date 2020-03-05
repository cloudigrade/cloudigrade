"""Collection of tests for tasks.create_from_sources_kafka_message."""
from unittest.mock import patch

import faker
from django.contrib.auth.models import User
from django.test import TestCase

from api import tasks
from util.exceptions import SourcesAPINotOkStatus
from util.tests import helper as util_helper

_faker = faker.Faker()


class CreateFromSourcesKafkaMessageTest(TestCase):
    """Celery task 'create_from_sources_kafka_message' test cases."""

    @patch("util.insights.get_sources_endpoint")
    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_success(
        self, mock_task, mock_get_auth, mock_get_endpoint
    ):
        """Assert create_from_sources_kafka_message happy path success."""
        account_number = str(_faker.pyint())
        username = _faker.user_name()
        authentication_id = _faker.pyint()
        endpoint_id = _faker.pyint()
        source_id = _faker.pyint()

        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )
        password = util_helper.generate_dummy_arn()
        mock_get_auth.return_value = {
            "password": password,
            "username": username,
            "resource_type": "Endpoint",
            "resource_id": endpoint_id,
            "id": authentication_id,
        }
        mock_get_endpoint.return_value = {"id": endpoint_id, "source_id": source_id}

        tasks.create_from_sources_kafka_message(message, headers)

        user = User.objects.get(username=account_number)
        mock_task.delay.assert_called_with(
            user.id, password, authentication_id, endpoint_id, source_id
        )

    @patch("util.insights.get_sources_endpoint")
    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_gets_username_from_authentication(
        self, mock_task, mock_get_auth, mock_get_endpoint
    ):
        """Assert create_from_sources_kafka_message gets username from auth."""
        account_number = str(_faker.pyint())
        username = _faker.user_name()
        authentication_id = _faker.pyint()
        endpoint_id = _faker.pyint()
        source_id = _faker.pyint()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, None, authentication_id
        )
        password = util_helper.generate_dummy_arn()
        mock_get_auth.return_value = {
            "password": password,
            "username": username,
            "resource_type": "Endpoint",
            "resource_id": endpoint_id,
            "id": authentication_id,
        }
        mock_get_endpoint.return_value = {"id": endpoint_id, "source_id": source_id}
        tasks.create_from_sources_kafka_message(message, headers)

        user = User.objects.get(username=account_number)
        mock_task.delay.assert_called_with(
            user.id, password, authentication_id, endpoint_id, source_id
        )

    @patch("util.insights.get_sources_endpoint")
    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_aws_task_not_called_for_unsupported_authtype(
        self, mock_task, mock_get_auth, mock_get_endpoint
    ):
        """Assert no account gets created for unsupported authtype."""
        account_number = str(_faker.pyint())
        authentication_id = _faker.pyint()
        message, headers = util_helper.generate_authentication_create_message_value(
            account_number, None, authentication_id, authentication_type="INVALID"
        )
        tasks.create_from_sources_kafka_message(message, headers)
        mock_task.delay.assert_not_called()

    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_fail_missing_message_data(
        self, mock_task
    ):
        """Assert create_from_sources_kafka_message fails from missing data."""
        message = {}
        headers = []
        tasks.create_from_sources_kafka_message(message, headers)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_fail_source_unexpected_response(
        self, mock_task, mock_get_auth
    ):
        """
        Assert create_from_sources_kafka_message fails from not-200/404 source reply.

        This could happen if the sources API is misbehaving unexpectedly.
        """
        message, headers = util_helper.generate_authentication_create_message_value()
        mock_get_auth.side_effect = SourcesAPINotOkStatus

        with self.assertRaises(SourcesAPINotOkStatus):
            tasks.create_from_sources_kafka_message(message, headers)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_returns_early_when_authentication_404(
        self, mock_task, mock_get_auth
    ):
        """
        Assert create_from_sources_kafka_message returns if sources authentication 404s.

        This could happen if the authentication has been deleted from the
        sources API by the time this task runs.
        """
        message, headers = util_helper.generate_authentication_create_message_value()
        mock_get_auth.return_value = None

        tasks.create_from_sources_kafka_message(message, headers)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("util.insights.get_sources_authentication")
    @patch("util.insights.get_sources_endpoint")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_returns_early_when_endpoint_404(
        self, mock_task, mock_get_endpoint, mock_get_auth
    ):
        """
        Assert create_from_sources_kafka_message returns if sources endpoint 404s.

        This could happen if the endpoint has been deleted from the
        sources API by the time this task runs.
        """
        message, headers = util_helper.generate_authentication_create_message_value()
        mock_get_auth.return_value = {"resource_id": _faker.pyint()}
        mock_get_endpoint.return_value = None

        tasks.create_from_sources_kafka_message(message, headers)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()
