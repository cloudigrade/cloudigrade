"""Collection of tests for check_azure_subscription_and_create_cloud_account."""
import uuid
from unittest.mock import patch

import faker
from django.test import TestCase

from api.clouds.azure import tasks
from api.models import CloudAccount
from api.models import User

_faker = faker.Faker()


class CheckAzureSubscriptionAndCreateCloudAccountTest(TestCase):
    """Task 'check_azure_subscription_and_create_cloud_account' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        # User that would ultimately own the created objects.
        self.user = User.objects.create(
            account_number=_faker.random_int(min=100000, max=999999)
        )

        # Fake inputs that would come from sources-api.
        self.subscription_id = str(uuid.uuid4())
        self.auth_id = _faker.pyint()
        self.application_id = _faker.pyint()
        self.source_id = _faker.pyint()

    @patch("api.clouds.azure.tasks.onboarding.create_azure_cloud_account")
    def test_success(self, mock_create):
        """Assert the task happy path upon normal operation."""
        tasks.check_azure_subscription_and_create_cloud_account(
            self.user.account_number,
            self.user.org_id,
            self.subscription_id,
            self.auth_id,
            self.application_id,
            self.source_id,
        )

        mock_create.assert_called_with(
            self.user,
            self.subscription_id,
            self.auth_id,
            self.application_id,
            self.source_id,
        )

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.azure.tasks.onboarding.create_azure_cloud_account")
    def test_fails_if_user_not_found(self, mock_create, mock_notify_sources):
        """Assert the task returns early if user is not found."""
        account_number = -1  # This user should never exist.
        org_id = None

        tasks.check_azure_subscription_and_create_cloud_account(
            account_number,
            org_id,
            self.subscription_id,
            self.auth_id,
            self.application_id,
            self.source_id,
        )

        mock_create.assert_not_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.azure.models.get_cloudigrade_available_subscriptions")
    def test_account_not_created_if_enable_fails(
        self, mock_get_subs, mock_notify_sources
    ):
        """Assert the account is not created if enable fails."""
        mock_get_subs.return_value = []

        tasks.check_azure_subscription_and_create_cloud_account(
            self.user.account_number,
            self.user.org_id,
            self.subscription_id,
            self.auth_id,
            self.application_id,
            self.source_id,
        )

        self.assertFalse(CloudAccount.objects.filter(user=self.user).exists())
