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
