"""Collection of tests for azure.tasks.onboarding.initial_azure_vm_discovery."""
import faker
from django.test import TestCase

from api import AZURE_PROVIDER_STRING
from api.clouds.azure.tasks.onboarding import initial_azure_vm_discovery
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
