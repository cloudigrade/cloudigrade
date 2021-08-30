"""Collection of tests for the 'delete_accounts' management command."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TransactionTestCase, override_settings

from api import models
from api.tests import helper as api_helper
from util.exceptions import KafkaProducerException
from util.tests import helper as util_helper


class DeleteAccountsTest(TransactionTestCase):
    """Management command 'delete_accounts' test case."""

    def setUp(self):
        """Set up test data."""
        self.stdout = StringIO()
        self.stderr = StringIO()
        self.user = util_helper.generate_test_user()
        self.account = api_helper.generate_cloud_account(user=self.user)
        self.account_2 = api_helper.generate_cloud_account(user=self.user)

    def assertPresent(self):
        """Assert that all expected objects are present."""
        self.assertEqual(models.CloudAccount.objects.filter(is_enabled=True).count(), 2)

    def assertDisabled(self):
        """Assert that all accounts are disabled."""
        self.assertEqual(models.CloudAccount.objects.filter(is_enabled=True).count(), 0)

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.aws.util.delete_cloudtrail")
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    def test_handle(self, mock_delete_cloudtrail, mock_notify_sources):
        """Test calling disable_accounts with confirm arg."""
        self.assertPresent()
        call_command(
            "disable_accounts", "--confirm", stdout=self.stdout, stderr=self.stderr
        )
        mock_notify_sources.delay.assert_called()
        mock_delete_cloudtrail.assert_called()
        self.assertDisabled()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.aws.util.delete_cloudtrail")
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True)
    def test_handle_when_kafka_errors(
        self, mock_delete_cloudtrail, mock_notify_sources
    ):
        """Test disable_accounts works despite sources-api errors."""
        self.assertPresent()
        mock_notify_sources.delay.side_effect = KafkaProducerException("bad error")
        call_command(
            "disable_accounts", "--confirm", stdout=self.stdout, stderr=self.stderr
        )
        mock_notify_sources.delay.assert_called()
        mock_delete_cloudtrail.assert_called()
        self.assertDisabled()

    @patch("builtins.input", return_value="N")
    def test_handle_no(self, mock_input):
        """Test calling disable_accounts with 'N' (no) input."""
        self.assertPresent()
        call_command("disable_accounts", stdout=self.stdout, stderr=self.stderr)
        self.assertPresent()

    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False)
    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.aws.util.delete_cloudtrail")
    @patch("builtins.input", return_value="Y")
    def test_handle_yes(self, mock_input, mock_delete_cloudtrail, mock_notify_sources):
        """Test calling disable_accounts with 'Y' (yes) input."""
        self.assertPresent()
        call_command("disable_accounts", stdout=self.stdout, stderr=self.stderr)
        self.assertDisabled()
        mock_delete_cloudtrail.assert_called()
        mock_notify_sources.delay.assert_called()

    @override_settings(IS_PRODUCTION=True)
    @override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True)
    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.aws.util.delete_cloudtrail")
    @patch("builtins.input", return_value="Y")
    def test_handle_in_production_aborts(
        self, mock_input, mock_delete_cloudtrail, mock_notify_sources
    ):
        """Test calling disable_accounts in production does nothing."""
        self.assertPresent()
        call_command("disable_accounts", stdout=self.stdout, stderr=self.stderr)
        self.assertPresent()
        mock_delete_cloudtrail.assert_not_called()
        mock_notify_sources.delay.assert_not_called()
