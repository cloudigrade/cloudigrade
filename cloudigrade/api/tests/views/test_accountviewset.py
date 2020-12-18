"""Collection of tests for AccountViewSet."""

import faker
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.models import CloudAccount
from api.tests import helper as api_helper
from api.views import AccountViewSet
from util.tests import helper as util_helper


class AccountViewSetTest(TransactionTestCase):
    """AccountViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.account1 = api_helper.generate_cloud_account(user=self.user1)
        self.account2 = api_helper.generate_cloud_account(user=self.user1)
        self.account3 = api_helper.generate_cloud_account(user=self.user2)
        self.account4 = api_helper.generate_cloud_account(user=self.user2)
        self.account5 = api_helper.generate_cloud_account(
            user=self.user2, name="unique"
        )
        self.azure_account1 = api_helper.generate_cloud_account(
            user=self.user1, cloud_type="azure"
        )
        self.azure_account2 = api_helper.generate_cloud_account(
            user=self.user2, cloud_type="azure"
        )

        self.factory = APIRequestFactory()
        self.faker = faker.Faker()

    def assertResponseHasAccountData(self, response, account):
        """Assert the response has data matching the account object."""
        self.assertEqual(response.data["account_id"], account.id)
        self.assertEqual(response.data["user_id"], account.user_id)
        self.assertEqual(response.data["name"], account.name)

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
                self.assertEqual(
                    response.data["content_object"]["tenant_id"],
                    str(account.content_object.tenant_id),
                )

    def get_account_ids_from_list_response(self, response):
        """
        Get the aws_account_id and azure_tenant_id from the paginated response.

        Args:
            response (Response): Django response object to inspect

        Returns:
            set[int]: the aws_account_id values found in the response

        """
        aws_account_ids = [
            account["content_object"]["aws_account_id"]
            for account in response.data["data"]
            if account["cloud_type"] == "aws"
        ]

        azure_tenant_ids = [
            account["content_object"]["tenant_id"]
            for account in response.data["data"]
            if account["cloud_type"] == "azure"
        ]

        return set(aws_account_ids + azure_tenant_ids)

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
        expected_accounts = {
            str(self.account1.content_object.aws_account_id),
            str(self.account2.content_object.aws_account_id),
            str(self.azure_account1.content_object.tenant_id),
        }
        response = self.get_account_list_response(self.user1)
        actual_accounts = self.get_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_list_accounts_as_user2(self):
        """Assert that user2 sees only its own accounts."""
        expected_accounts = {
            str(self.account3.content_object.aws_account_id),
            str(self.account4.content_object.aws_account_id),
            str(self.account5.content_object.aws_account_id),
            str(self.azure_account2.content_object.tenant_id),
        }
        response = self.get_account_list_response(self.user2)
        actual_accounts = self.get_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_get_user1s_account_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own accounts."""
        user = self.user1
        account = self.account2  # Account belongs to user1.

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasAccountData(response, account)

    def test_get_user1s_azure_account_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own azure accounts."""
        user = self.user1
        account = self.azure_account1

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasAccountData(response, account)

    def test_get_user1s_account_as_user2_returns_404(self):
        """Assert that user2 cannot get an account belonging to user1."""
        user = self.user2
        account = self.account2  # Account belongs to user1, NOT user2.

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 404)
