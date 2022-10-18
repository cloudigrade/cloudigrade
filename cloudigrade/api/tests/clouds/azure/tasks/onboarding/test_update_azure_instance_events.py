"""Tests the azure.tasks.onboarding.update_azure_instance_events function."""
from unittest.mock import call, patch

import faker
from django.test import TestCase

from api import AZURE_PROVIDER_STRING
from api.clouds.azure.tasks.onboarding import (
    update_azure_instance_events,
    update_azure_instance_events_for_account,
)
from api.tests import helper as account_helper

_faker = faker.Faker()

log_prefix = "api.clouds.azure.tasks.onboarding"


class UpdateAzureInstanceEvents(TestCase):
    """Async function 'update_azure_instance_events' test cases."""

    def setUp(self):
        """Set up variables for the tests."""
        self.accounts = [
            account_helper.generate_cloud_account(
                cloud_type=AZURE_PROVIDER_STRING,
                azure_subscription_id=_faker.uuid4(),
                is_enabled=True,
            ),
            account_helper.generate_cloud_account(
                cloud_type=AZURE_PROVIDER_STRING,
                azure_subscription_id=_faker.uuid4(),
                is_enabled=False,
            ),
        ]

    @patch("api.clouds.azure.tasks.update_azure_instance_events_for_account.delay")
    def test_update_azure_instance_events(
        self,
        mock_update_azure_instance_events_for_account,
    ):
        """Test functionality of update azure instance events for all accounts."""
        update_azure_instance_events()

        expected_calls = [call(account.cloud_account_id) for account in self.accounts]
        mock_update_azure_instance_events_for_account.assert_has_calls(expected_calls)

    def test_update_azure_instance_events_for_account_dne(self):
        """Test that a log returns when the cloud account does not exist."""
        account_id = _faker.uuid4()

        with self.assertLogs(log_prefix, level="INFO") as logging_watcher:
            update_azure_instance_events_for_account(account_id)
            self.assertIn(
                f"Azure Cloud Account {account_id} not found; "
                "skipping instance events update",
                logging_watcher.output[0],
            )

    @patch("api.clouds.azure.tasks.onboarding.create_initial_azure_instance_events")
    @patch("api.clouds.azure.tasks.onboarding.get_vms_for_subscription")
    def test_update_azure_instance_events_for_account(
        self,
        mock_get_vms,
        mock_create_initial_azure_instance_events,
    ):
        """Test typical behavior for 'update_azure_instance_events_for_account'."""
        account = self.accounts[0]
        vms = account_helper.generate_azure_vm(account.cloud_account_id)
        mock_get_vms.return_value = vms

        update_azure_instance_events_for_account(account.cloud_account_id)
        mock_create_initial_azure_instance_events.assert_called_with(
            account.content_object, vms
        )
