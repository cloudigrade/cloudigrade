"""Collection of tests for azure.tasks.onboarding.initial_azure_vm_discovery."""
from unittest.mock import MagicMock, patch

import faker
from django.test import TestCase

from api import AZURE_PROVIDER_STRING
from api.clouds.azure.tasks.onboarding import (
    AzureCloudAccount,
    initial_azure_vm_discovery,
)
from api.tests import helper as account_helper

_faker = faker.Faker()

log_prefix = "api.clouds.azure.tasks.onboarding"


class InitialAzureVmDiscovery(TestCase):
    """Celery task 'initial_azure_vm_discovery' test cases."""

    def test_initial_azure_vm_discovery(self):
        """Test happy path of initial_azure_vm_discovery."""
        subscription_id = _faker.uuid4()
        account = account_helper.generate_cloud_account(
            cloud_type=AZURE_PROVIDER_STRING,
            azure_subscription_id=subscription_id,
            is_enabled=True,
        )

        with self.assertLogs(log_prefix, level="INFO") as logging_watcher:
            initial_azure_vm_discovery(account.id)
            self.assertIn(
                "Initiating an Initial VM Discovery for the"
                f" Azure cloud account id {account.id} with the"
                f" Azure subscription id {subscription_id}",
                logging_watcher.output[0],
            )

    def test_initial_azure_vm_discovery_account_does_not_exist(self):
        """Test behavior of initial_azure_vm_discovery with non-existent account."""
        account_id = _faker.pyint()

        with self.assertLogs(log_prefix, level="WARNING") as logging_watcher:
            initial_azure_vm_discovery(account_id)
            self.assertIn(
                f"AzureCloudAccount id {account_id}"
                " could not be found for initial vm discovery",
                logging_watcher.output[0],
            )

    def test_initial_azure_vm_discovery_account_disabled(self):
        """Test behavior of initial_azure_vm_discovery with disabled account."""
        account = account_helper.generate_cloud_account(
            cloud_type=AZURE_PROVIDER_STRING, is_enabled=False
        )

        with self.assertLogs(log_prefix, level="WARNING") as logging_watcher:
            initial_azure_vm_discovery(account.id)
            self.assertIn(
                f"AzureCloudAccount id {account.id} is not enabled;"
                " skipping initial vm discovery",
                logging_watcher.output[0],
            )

    def test_initial_azure_vm_discovery_account_paused(self):
        """Test behavior of initial_azure_vm_discovery with paused account."""
        account = account_helper.generate_cloud_account(
            cloud_type=AZURE_PROVIDER_STRING, platform_application_is_paused=True
        )

        with self.assertLogs(log_prefix, level="WARNING") as logging_watcher:
            initial_azure_vm_discovery(account.id)
            self.assertIn(
                f"AzureCloudAccount id {account.id} is paused;"
                " skipping initial vm discovery",
                logging_watcher.output[0],
            )

    @patch("api.clouds.azure.tasks.onboarding.lock_task_for_user_ids")
    @patch("api.clouds.azure.tasks.onboarding.AzureCloudAccount.objects.get")
    def test_initial_azure_vm_discovery_account_deleted(
        self, mock_azure_cloud_account_get, mock_lock_task
    ):
        """Test behavior of initial_azure_vm_discovery when account is deleted."""
        subscription_id = _faker.uuid4()
        cloud_account_id = _faker.pyint()
        azure_cloud_account_id = _faker.pyint()
        user_id = _faker.pyint()

        cloud_account = MagicMock()
        cloud_account.id = cloud_account_id
        cloud_account.is_enabled = True
        cloud_account.platform_application_is_paused = False
        cloud_account.user.id = user_id

        azure_cloud_account = MagicMock()
        azure_cloud_account.id = azure_cloud_account_id
        azure_cloud_account.cloud_account.get.return_value = cloud_account
        azure_cloud_account.subscription_id = subscription_id

        mock_azure_cloud_account_get.side_effect = [
            azure_cloud_account,
            AzureCloudAccount.DoesNotExist(),
        ]
        with self.assertLogs(log_prefix, level="WARNING") as logging_watcher:
            initial_azure_vm_discovery(azure_cloud_account.id)

        self.assertIn(
            f"AzureCloudAccount id {azure_cloud_account.id} no longer exists; "
            "skipping initial vm discovery.",
            logging_watcher.output[0],
        )
