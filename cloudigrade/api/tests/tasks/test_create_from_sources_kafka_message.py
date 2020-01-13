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

    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_success(self, mock_task, mock_get_auth):
        """Assert create_from_sources_kafka_message happy path success."""
        account_number = str(_faker.pyint())
        username = _faker.user_name()
        authentication_id = _faker.pyint()
        message = util_helper.generate_authentication_create_message_value(
            account_number, username, authentication_id
        )
        password = _faker.password()
        mock_get_auth.return_value = {"password": password}

        tasks.create_from_sources_kafka_message(message)

        user = User.objects.get(username=account_number)
        mock_task.delay.assert_called_with(user.id, username, password)

    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_fail_missing_message_data(
        self, mock_task
    ):
        """Assert create_from_sources_kafka_message fails from missing data."""
        message = {}
        tasks.create_from_sources_kafka_message(message)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()

    @patch("util.insights.get_sources_authentication")
    @patch("api.tasks.configure_customer_aws_and_create_cloud_account")
    def test_create_from_sources_kafka_message_fail_source_404(
        self, mock_task, mock_get_auth
    ):
        """
        Assert create_from_sources_kafka_message fails from 404 source reply.

        This could happen if the authentication has been deleted from the
        sources API by the time this task runs.
        """
        message = util_helper.generate_authentication_create_message_value()
        mock_get_auth.side_effect = SourcesAPINotOkStatus

        with self.assertRaises(SourcesAPINotOkStatus):
            tasks.create_from_sources_kafka_message(message)

        # User should not have been created.
        self.assertEqual(User.objects.all().count(), 0)
        mock_task.delay.assert_not_called()
