"""Collection of tests for custom Django model logic."""
import uuid
from unittest.mock import patch

from django.test import TransactionTestCase

from api import AZURE_PROVIDER_STRING
from api.clouds.azure import models as azure_models
from api.tests import helper
from api.tests.clouds.aws.test_models import ModelStrTestMixin
from util.tests import helper as util_helper


class AzureCloudAccountModelTest(TransactionTestCase, ModelStrTestMixin):
    """AzureCloudAccount Model Test Cases."""

    def setUp(self):
        """Set up basic azure account."""
        self.created_at = util_helper.utc_dt(2019, 1, 1, 0, 0, 0)
        self.subscription_id = uuid.uuid4()
        self.account = helper.generate_cloud_account(
            cloud_type=AZURE_PROVIDER_STRING,
            azure_subscription_id=self.subscription_id,
            created_at=self.created_at,
        )

    def test_cloud_account_str(self):
        """Test that the CloudAccount str (and repr) is valid."""
        excluded_field_names = {"content_type", "object_id"}
        self.assertTypicalStrOutput(self.account, excluded_field_names)

    def test_azure_cloud_account_str(self):
        """Test that the AzureCloudAccount str (and repr) is valid."""
        self.assertTypicalStrOutput(self.account.content_object)

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_enable_succeeds(self, mock_notify_sources):
        """
        Test that enabling an account does all the relevant verification and setup.

        Enabling a CloudAccount having an AzureCloudAccount should:

        - check that we can access the given azure subscription_id
        """
        # Normally you shouldn't directly manipulate the is_enabled value,
        # but here we need to force it down to check that it gets set back.
        self.account.is_enabled = False
        self.account.save()
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)

        enable_date = util_helper.utc_dt(2019, 1, 4, 0, 0, 0)
        with patch(
            "api.clouds.azure.models.get_cloudigrade_available_subscriptions"
        ) as mock_get_subs, util_helper.clouditardis(enable_date):
            mock_get_subs.return_value = [self.subscription_id]
            self.account.enable()

        self.account.refresh_from_db()
        self.assertTrue(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, enable_date)

    def test_enable_failure(self):
        """Test that enabling an account rolls back if cloud-specific step fails."""
        # Normally you shouldn't directly manipulate the is_enabled value,
        # but here we need to force it down to check that it gets set back.
        self.account.is_enabled = False
        self.account.save()
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)

        with patch(
            "api.clouds.azure.models.get_cloudigrade_available_subscriptions"
        ) as mock_get_subs, self.assertLogs("api.models", level="INFO") as cm:
            mock_get_subs.return_value = []
            success = self.account.enable(disable_upon_failure=False)
            self.assertFalse(success)

        self.assertIn(
            "subscription not present in list of available subscriptions",
            cm.records[1].getMessage(),
        )

        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_succeeds(self, mock_notify_sources):
        """Test that an account is deleted if there are no errors."""
        self.account.delete()
        self.assertEqual(0, azure_models.AzureCloudAccount.objects.count())
