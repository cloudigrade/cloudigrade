"""Collection of tests for custom Django model logic."""

import uuid
from unittest.mock import Mock, patch

from azure.core.exceptions import ClientAuthenticationError
from django.db.models.signals import post_delete
from django.test import TestCase, TransactionTestCase

from api import AZURE_PROVIDER_STRING
from api.clouds.azure import models as azure_models
from api.tests import helper
from util.tests import helper as util_helper

log_prefix = "api.clouds.azure.models"


class AzureCloudAccountModelTest(TransactionTestCase, helper.ModelStrTestMixin):
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

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_triggers_lighthouse_unregistration(self, mock_notify_sources):
        """Tests that deleting an account triggers a lighthouse unregistration."""
        with util_helper.mock_signal_handler(
            post_delete,
            azure_models.delete_lighthouse_registration,
            azure_models.AzureCloudAccount,
        ) as mock_del_registration:
            self.account.delete()
            self.assertEqual(0, azure_models.AzureCloudAccount.objects.count())
            mock_del_registration.assert_called()


class AzureDeleteLighthouseRegistrationTest(TestCase):
    """Azure Delete Lighthouse Registration test cases."""

    def setUp(self):
        """Set up an azure cloud account."""
        self.created_at = util_helper.utc_dt(2019, 1, 1, 0, 0, 0)
        self.subscription_id = uuid.uuid4()
        self.account = helper.generate_cloud_account(
            cloud_type=AZURE_PROVIDER_STRING,
            azure_subscription_id=self.subscription_id,
            created_at=self.created_at,
        )
        self.tenant_scope = f"subscriptions/{self.subscription_id}"
        self.reg_name = uuid.uuid4()

    def ra_id(self, subscription=None, name=None):
        """Generate a registration assignment id."""
        return (
            f"/subscriptions/{subscription or self.subscription_id}/"
            "providers/Microsoft.ManagedServices/"
            f"registrationAssignments/{name or self.reg_name}"
        )

    def reg_assignment(self, subscription=None, name=None):
        """Generate a registration assignment."""
        ra = Mock()
        ra.subscription = subscription or uuid.uuid4()
        ra.name = name or uuid.uuid4()
        ra.id = self.ra_id(ra.subscription, ra.name)
        ra.properties.provisioning_state = "Succeeded"
        return ra

    @patch("api.clouds.azure.models.ManagedServicesClient")
    def test_lighthouse_registration_delete(self, mock_msc):
        """Test happy path deleting the lighthouse registration assignment."""
        mock_msclient = Mock()
        mock_msc.return_value = mock_msclient
        reg_assignment = self.reg_assignment(
            subscription=self.subscription_id, name=self.reg_name
        )
        mock_msclient.registration_assignments.list.return_value = [reg_assignment]

        with self.assertLogs(log_prefix, level="INFO") as logging_watcher:
            azure_models.delete_lighthouse_registration(
                instance=self.account.content_object
            )
            self.assertIn(
                "Attempting to delete the Azure lighthouse registration"
                f" for tenant subscription {self.subscription_id}",
                logging_watcher.output[0],
            )
            self.assertIn(
                "Found a lighthouse registration assignment"
                f" for tenant subscription {self.subscription_id},"
                f" name {self.reg_name}, id {reg_assignment.id}",
                logging_watcher.output[1],
            )
            mock_msclient.registration_assignments.begin_delete.assert_called()

    @patch("api.clouds.azure.models.ManagedServicesClient")
    def test_lighthouse_registration_not_found(self, mock_msc):
        """Test skipping deletion if lighthouse registration assignment is not found."""
        mock_msclient = Mock()
        mock_msc.return_value = mock_msclient
        reg_assignment = self.reg_assignment()
        mock_msclient.registration_assignments.list.return_value = [reg_assignment]

        with self.assertLogs(log_prefix, level="INFO") as logging_watcher:
            azure_models.delete_lighthouse_registration(
                instance=self.account.content_object
            )
            self.assertIn(
                "Attempting to delete the Azure lighthouse registration"
                f" for tenant subscription {self.subscription_id}",
                logging_watcher.output[0],
            )
            self.assertIn(
                "Could not find a matching lighthouse registration"
                f" for tenant subscription {self.subscription_id}",
                logging_watcher.output[1],
            )

    @patch("api.clouds.azure.models.ManagedServicesClient")
    def test_lighthouse_registration_delete_skip_multiple(self, mock_msc):
        """Test that we skip deletion if multiple registrations are found.."""
        mock_msclient = Mock()
        mock_msc.return_value = mock_msclient
        reg_assignment1 = self.reg_assignment(subscription=self.subscription_id)
        reg_assignment2 = self.reg_assignment(subscription=self.subscription_id)
        mock_msclient.registration_assignments.list.return_value = [
            reg_assignment1,
            reg_assignment2,
        ]

        with self.assertLogs(log_prefix, level="INFO") as logging_watcher:
            azure_models.delete_lighthouse_registration(
                instance=self.account.content_object
            )
            self.assertIn(
                "Attempting to delete the Azure lighthouse registration"
                f" for tenant subscription {self.subscription_id}",
                logging_watcher.output[0],
            )
            self.assertIn(
                "Found a lighthouse registration assignment"
                f" for tenant subscription {self.subscription_id},"
                f" name {reg_assignment1.name}, id {reg_assignment1.id}",
                logging_watcher.output[1],
            )
            self.assertIn(
                "Found multiple lighthouse registrations"
                f" for tenant subscription {self.subscription_id},"
                f" skipping deleting the lighthouse registration.",
                logging_watcher.output[2],
            )

    @patch("api.clouds.azure.models.ManagedServicesClient")
    def test_lighthouse_registration_delete_auth_error(self, mock_msc):
        """Test ClientAuthenticationError while deleting the lighthouse registration."""
        mock_msclient = Mock()
        mock_msc.return_value = mock_msclient
        mock_msclient.registration_assignments.list.side_effect = (
            ClientAuthenticationError("simulated auth error")
        )

        with self.assertLogs(log_prefix, level="WARN") as logging_watcher:
            azure_models.delete_lighthouse_registration(
                instance=self.account.content_object
            )
            self.assertIn(
                "ClientAuthenticationError while trying to find"
                " the lighthouse registration assignment for"
                f" tenant subscription {self.subscription_id}"
                " - simulated auth error",
                logging_watcher.output[0],
            )

    @patch("api.clouds.azure.models.ManagedServicesClient")
    def test_lighthouse_registration_delete_exception(self, mock_msc):
        """Test Exception while deleting the lighthouse registration."""
        mock_msclient = Mock()
        mock_msc.return_value = mock_msclient
        mock_msclient.side_effect = Exception

        with self.assertLogs(log_prefix, level="ERROR") as logging_watcher:
            azure_models.delete_lighthouse_registration(
                instance=self.account.content_object
            )
            self.assertIn(
                "Unexpected error while trying to find"
                " the lighthouse registration assignment"
                f" for tenant subscription {self.subscription_id}",
                logging_watcher.output[0],
            )
