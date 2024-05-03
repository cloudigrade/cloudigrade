"""Collection of tests for internal viewsets."""

import decimal

from django.test import TestCase

from api import models
from api.clouds.aws import models as aws_models
from api.models import User
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class InternalViewSetTest(TestCase):
    """Test internal viewsets."""

    def setUp(self):
        """
        Set up a bunch of test data.

        This gets very noisy very quickly because we need users who have
        accounts that have instances that have events that used various image
        types.
        """
        # Users
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.user3 = util_helper.generate_test_user()

        # Accounts for the users
        self.account_u1_1 = api_helper.generate_cloud_account(user=self.user1)
        self.account_u1_2 = api_helper.generate_cloud_account(user=self.user1)
        self.account_u2_1 = api_helper.generate_cloud_account(user=self.user2)
        self.account_u2_2 = api_helper.generate_cloud_account(user=self.user2)

        self.client = api_helper.SandboxedRestClient(
            api_root="/internal/api/cloudigrade/v1"
        )
        self.client._force_authenticate(self.user3)

    def test_list_users(self):
        """Assert that a user sees all User objects."""
        users = list(User.objects.all())
        expected_account_numbers = set(user.account_number for user in users)

        response = self.client.get_users()
        count = response.data["meta"]["count"]
        actual_account_numbers = set(
            item["account_number"] for item in response.data["data"]
        )

        self.assertGreater(count, 0)
        self.assertEqual(count, len(users))
        self.assertEqual(expected_account_numbers, actual_account_numbers)

    def test_list_cloudaccounts(self):
        """Assert that a user sees all CloudAccount objects."""
        cloudaccounts = list(models.CloudAccount.objects.all())
        expected_ids = set(account.id for account in cloudaccounts)

        response = self.client.get_cloudaccounts()
        actual_ids = set(item["id"] for item in response.data["data"])
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(cloudaccounts))
        self.assertEqual(expected_ids, actual_ids)

    def test_list_awscloudaccounts(self):
        """Assert that a user sees all AwsCloudAccount objects."""
        accounts = list(aws_models.AwsCloudAccount.objects.all())
        expected_ids = set(account.aws_account_id for account in accounts)

        response = self.client.get_awscloudaccounts()
        actual_ids = set(
            decimal.Decimal(item["aws_account_id"]) for item in response.data["data"]
        )
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(accounts))
        self.assertEqual(expected_ids, actual_ids)
