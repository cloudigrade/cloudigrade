"""Collection of tests for api.cloud.azure.util.create_azure_cloud_account."""
from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from api.clouds.azure import util
from api.clouds.azure.models import AzureCloudAccount
from api.models import CloudAccount
from util.tests import helper as util_helper

_faker = faker.Faker()


class CreateAzureCloudAccountTest(TestCase):
    """Test cases for api.cloud.azure.util.create_azure_cloud_account."""

    def setUp(self):
        """Set up shared variables."""
        self.user = util_helper.generate_test_user()
        self.subscription_id = _faker.uuid4()
        self.auth_id = _faker.pyint()
        self.app_id = _faker.pyint()
        self.source_id = _faker.pyint()

    @patch.object(CloudAccount, "enable")
    def test_create_azure_clount_success(self, mock_enable):
        """Test create_azure_cloud_account success."""
        cloud_account = util.create_azure_cloud_account(
            self.user, self.subscription_id, self.auth_id, self.app_id, self.source_id
        )
        mock_enable.assert_called()
        self.assertEqual(cloud_account, CloudAccount.objects.get())
        azure_cloud_account = cloud_account.content_object
        self.assertEqual(azure_cloud_account, AzureCloudAccount.objects.get())

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch.object(CloudAccount, "enable")
    def test_create_azure_cloud_account_fails_duplicate_subscription_id(
        self, mock_enable, mock_notify_sources
    ):
        """Test create_azure_cloud_account when the subscription ID is already used."""
        util.create_azure_cloud_account(
            self.user, self.subscription_id, self.auth_id, self.app_id, self.source_id
        )
        mock_enable.assert_called()
        mock_notify_sources.delay.assert_not_called()

        mock_enable.reset_mock()
        mock_notify_sources.reset_mock()

        with self.assertRaises(ValidationError) as raise_context:
            util.create_azure_cloud_account(
                self.user,
                self.subscription_id,
                self.auth_id,
                self.app_id,
                self.source_id,
            )
        exception_detail = raise_context.exception.detail
        self.assertIn("subscription_id", exception_detail)
        self.assertIn(
            "Could not enable cloud metering.", exception_detail["subscription_id"]
        )
        self.assertIn("CG1005", exception_detail["subscription_id"])

        mock_enable.assert_not_called()
        mock_notify_sources.delay.assert_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch.object(CloudAccount, "enable")
    def test_create_azure_cloud_account_fails_subscription_id_is_not_uuid(
        self, mock_enable, mock_notify_sources
    ):
        """Test create_azure_cloud_account when the subscription ID is not a UUID."""
        subscription_id = _faker.slug()  # not a valid UUID!

        with self.assertRaises(ValidationError) as raise_context:
            util.create_azure_cloud_account(
                self.user,
                subscription_id,
                self.auth_id,
                self.app_id,
                self.source_id,
            )
        exception_detail = raise_context.exception.detail
        self.assertIn("subscription_id", exception_detail)
        self.assertIn(
            "Could not enable cloud metering.", exception_detail["subscription_id"]
        )
        self.assertIn("CG1006", exception_detail["subscription_id"])

        mock_enable.assert_not_called()
        mock_notify_sources.delay.assert_called_once()
        call_args = mock_notify_sources.delay.call_args
        self.assertEqual(call_args.kwargs["availability_status"], "unavailable")
        self.assertIn("CG1006", call_args.kwargs["availability_status_error"])
