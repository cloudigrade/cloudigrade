"""Collection of tests for the 'delete_accounts' management command."""
from unittest.mock import patch

import requests
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings

from api import models
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class DeleteAccountsTest(TransactionTestCase):
    """Management command 'delete_accounts' test case."""

    def setUp(self):
        """Set up test data."""
        self.user = util_helper.generate_test_user()
        self.account = api_helper.generate_cloud_account(user=self.user)
        self.account_2 = api_helper.generate_cloud_account(user=self.user)

    def assertPresent(self):
        """Assert that all expected objects are present."""
        self.assertEqual(models.CloudAccount.objects.filter(is_enabled=True).count(), 2)

    def assertDisabled(self):
        """Assert that all accounts are disabled."""
        self.assertEqual(models.CloudAccount.objects.filter(is_enabled=True).count(), 0)

    @patch("api.clouds.aws.util.delete_cloudtrail")
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_handle(self, mock_delete_cloudtrail):
        """Test calling disable_accounts with confirm arg."""
        self.assertPresent()
        call_command("disable_accounts", "--confirm")
        mock_delete_cloudtrail.assert_called()
        self.assertDisabled()

    @patch("api.models.notify_sources_application_availability")
    @patch("api.clouds.aws.util.delete_cloudtrail")
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True)
    def test_handle_when_kafka_errors(self, mock_delete_cloudtrail, mock_notify):
        """Test disable_accounts works despite sources-api errors."""
        self.assertPresent()
        mock_notify.side_effect = requests.exceptions.ConnectionError("test error")
        call_command("disable_accounts", "--confirm")
        mock_notify.assert_called()
        mock_delete_cloudtrail.assert_called()
        self.assertDisabled()

    @patch("builtins.input", return_value="N")
    def test_handle_no(self, mock_input):
        """Test calling disable_accounts with 'N' (no) input."""
        self.assertPresent()
        call_command("disable_accounts")
        self.assertPresent()

    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    @patch("api.clouds.aws.util.delete_cloudtrail")
    @patch("builtins.input", return_value="Y")
    def test_handle_yes(self, mock_input, mock_delete_cloudtrail):
        """Test calling disable_accounts with 'Y' (yes) input."""
        self.assertPresent()
        call_command("disable_accounts")
        self.assertDisabled()
        mock_delete_cloudtrail.assert_called()

    @override_settings(IS_PRODUCTION=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True)
    @patch("api.models.notify_sources_application_availability")
    @patch("api.clouds.aws.util.delete_cloudtrail")
    @patch("builtins.input", return_value="Y")
    def test_handle_in_production_aborts(
        self, mock_input, mock_delete_cloudtrail, mock_notify
    ):
        """Test calling disable_accounts in production does nothing."""
        self.assertPresent()
        call_command("disable_accounts")
        self.assertPresent()
        mock_delete_cloudtrail.assert_not_called()
        mock_notify.assert_not_called()
