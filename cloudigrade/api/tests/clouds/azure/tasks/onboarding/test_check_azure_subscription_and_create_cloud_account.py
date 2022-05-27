"""Collection of tests for check_azure_subscription_and_create_cloud_account."""
import uuid
from unittest.mock import patch

import faker
from django.contrib.auth.models import User
from django.test import TestCase

from api.clouds.azure import tasks
from api.models import CloudAccount

_faker = faker.Faker()


class CheckAzureSubscriptionAndCreateCloudAccountTest(TestCase):
    """Task 'check_azure_subscription_and_create_cloud_account' test cases."""

    @patch("api.clouds.azure.tasks.onboarding.create_azure_cloud_account")
    def test_success(self, mock_create):
        """Assert the task happy path upon normal operation."""
        # User that would ultimately own the created objects.
        user = User.objects.create()

        # Dummy values for the various interactions.
        subscription_id = str(uuid.uuid4())
        auth_id = _faker.pyint()
        application_id = _faker.pyint()
        source_id = _faker.pyint()

        tasks.check_azure_subscription_and_create_cloud_account(
            user.username,
            user.last_name,
            subscription_id,
            auth_id,
            application_id,
            source_id,
        )

        mock_create.assert_called_with(
            user,
            subscription_id,
            auth_id,
            application_id,
            source_id,
        )

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.azure.tasks.onboarding.create_azure_cloud_account")
    def test_fails_if_user_not_found(self, mock_create, mock_notify_sources):
        """Assert the task returns early if user is not found."""
        username = -1  # This user should never exist.
        org_id = None

        subscription_id = str(uuid.uuid4())
        auth_id = _faker.pyint()
        application_id = _faker.pyint()
        source_id = _faker.pyint()

        tasks.check_azure_subscription_and_create_cloud_account(
            username,
            org_id,
            subscription_id,
            auth_id,
            application_id,
            source_id,
        )

        mock_create.assert_not_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.azure.models.get_cloudigrade_available_subscriptions")
    def test_account_not_created_if_enable_fails(
        self, mock_get_subs, mock_notify_sources
    ):
        """Assert the account is not created if enable fails."""
        user = User.objects.create()

        subscription_id = str(uuid.uuid4())
        auth_id = _faker.pyint()
        application_id = _faker.pyint()
        source_id = _faker.pyint()

        mock_get_subs.return_value = []

        tasks.check_azure_subscription_and_create_cloud_account(
            user.username,
            user.last_name,
            subscription_id,
            auth_id,
            application_id,
            source_id,
        )

        self.assertFalse(CloudAccount.objects.filter(user=user).exists())
