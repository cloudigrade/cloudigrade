"""Collection of tests for AccountViewSet."""

import faker
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import CloudAccount
from api.tests import helper as api_helper
from api.viewsets import AccountViewSet
from util.tests import helper as util_helper


class AccountViewSetTest(TransactionTestCase):
    """AccountViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        # First user and its accounts
        self.user1 = util_helper.generate_test_user()
        self.account_user1_aws1 = api_helper.generate_cloud_account_aws(user=self.user1)
        self.account_user1_aws2 = api_helper.generate_cloud_account_aws(user=self.user1)
        self.account_user1_aws3 = api_helper.generate_cloud_account_aws(
            user=self.user1, missing_content_object=True
        )
        self.account_user1_azure1 = api_helper.generate_cloud_account_azure(
            user=self.user1
        )
        # Second user and its accounts
        self.user2 = util_helper.generate_test_user()
        self.account_user2_aws1 = api_helper.generate_cloud_account_aws(user=self.user2)
        self.account_user2_aws2 = api_helper.generate_cloud_account_aws(user=self.user2)
        self.account_user2_aws3 = api_helper.generate_cloud_account_aws(user=self.user2)
        self.account_user2_azure1 = api_helper.generate_cloud_account_azure(
            user=self.user2
        )
        # Other utility helpers
        self.factory = APIRequestFactory()
        self.faker = faker.Faker()

    def assertResponseHasAccountData(self, response, account):
        """Assert the response has data matching the account object."""
        self.assertEqual(response.data["account_id"], account.id)
        self.assertEqual(response.data["user_id"], account.user_id)

        if isinstance(account, CloudAccount):
            if account.cloud_type == "aws":
                self.assertEqual(
                    response.data["content_object"]["account_arn"],
                    account.content_object.account_arn,
                )
                self.assertEqual(
                    response.data["content_object"]["aws_account_id"],
                    str(account.content_object.aws_account_id),
                )
            elif account.cloud_type == "azure":
                self.assertEqual(
                    response.data["content_object"]["subscription_id"],
                    str(account.content_object.subscription_id),
                )

    def get_cloud_account_ids_from_list_response(self, response):
        """
        Get aws_account_id and azure_subscription_id values from the paginated response.

        If an account's cloud_type or content_object is None, no value will be returned
        from this function for that account.

        Args:
            response (Response): Django response object to inspect

        Returns:
            set[int]: the values found in the response

        """
        aws_account_ids = [
            account.get("content_object", {}).get("aws_account_id")
            for account in response.data["data"]
            if account["cloud_type"] == "aws"
        ]

        azure_subscription_ids = [
            account.get("content_object", {}).get("subscription_id")
            for account in response.data["data"]
            if account["cloud_type"] == "azure"
        ]

        return set(aws_account_ids + azure_subscription_ids)

    def get_account_get_response(self, user, account_id):
        """
        Generate a response for a get-retrieve on the AccountViewSet.

        Args:
            user (User): Django auth user performing the request
            account_id (int): the id of the account to retrieve
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get("/accounts/")
        force_authenticate(request, user=user)
        view = AccountViewSet.as_view(actions={"get": "retrieve"})
        response = view(request, pk=account_id)
        return response

    def get_account_list_response(self, user, data=None):
        """
        Generate a response for a get-list on the AccountViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get("/accounts/", data)
        force_authenticate(request, user=user)
        view = AccountViewSet.as_view(actions={"get": "list"})
        response = view(request)
        return response

    def test_list_accounts_as_user1(self):
        """Assert that user1 sees only its own accounts."""
        expected_cloud_account_ids = {
            str(self.account_user1_aws1.content_object.aws_account_id),
            str(self.account_user1_aws2.content_object.aws_account_id),
            str(self.account_user1_azure1.content_object.subscription_id),
        }
        response = self.get_account_list_response(self.user1)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        actual_accounts = self.get_cloud_account_ids_from_list_response(response)
        self.assertEqual(expected_cloud_account_ids, actual_accounts)

        # The "broken" self.account_user1_aws3 should also be in the data list.
        expected_accounts_count = len(expected_cloud_account_ids) + 1
        self.assertEqual(len(response.data["data"]), expected_accounts_count)

    def test_list_accounts_as_user2(self):
        """Assert that user2 sees only its own accounts."""
        expected_cloud_account_ids = {
            str(self.account_user2_aws1.content_object.aws_account_id),
            str(self.account_user2_aws2.content_object.aws_account_id),
            str(self.account_user2_aws3.content_object.aws_account_id),
            str(self.account_user2_azure1.content_object.subscription_id),
        }
        response = self.get_account_list_response(self.user2)
        actual_accounts = self.get_cloud_account_ids_from_list_response(response)
        self.assertEqual(expected_cloud_account_ids, actual_accounts)

    def test_get_user1s_account_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own accounts."""
        user = self.user1
        account = self.account_user1_aws2  # Account belongs to user1.

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasAccountData(response, account)

    def test_get_user1s_azure_account_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own azure accounts."""
        user = self.user1
        account = self.account_user1_azure1

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasAccountData(response, account)

    def test_get_user1s_account_as_user2_returns_404(self):
        """Assert that user2 cannot get an account belonging to user1."""
        user = self.user2
        account = self.account_user1_aws2  # Account belongs to user1, NOT user2.

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 404)
