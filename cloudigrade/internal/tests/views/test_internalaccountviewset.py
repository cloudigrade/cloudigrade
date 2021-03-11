"""
Collection of tests for InternalAccountViewSet.

Historical note: most of this code used to live in AccountViewSetTest, but when we
moved the "writable" API methods from the public API to the internal API, we also
moved those tests here and updated them as necessary.
"""

from unittest.mock import patch

import faker
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api import serializers
from api.clouds.aws import util
from api.models import CloudAccount
from api.tests import helper as api_helper
from internal.views import InternalAccountViewSet
from util.tests import helper as util_helper


class InternalAccountViewSetTest(TransactionTestCase):
    """InternalAccountViewSet test case."""

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

        # APIRequestFactory calls require a path, but its value doesn't really matter
        # since we explicitly instantiate the ViewSet that will be used. Regardless,
        # this is what a normal path for incoming requests would look like.
        self.path = "/internal/api/cloudigrade/v1/accounts/"

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
        Generate a response for a get-retrieve on the InternalAccountViewSet.

        Args:
            user (User): Django auth user performing the request
            account_id (int): the id of the account to retrieve
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get(self.path)
        force_authenticate(request, user=user)
        view = InternalAccountViewSet.as_view(actions={"get": "retrieve"})
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
        request = self.factory.get(self.path, data)
        force_authenticate(request, user=user)
        view = InternalAccountViewSet.as_view(actions={"get": "list"})
        response = view(request)
        return response

    def get_account_delete_response(self, user, account_id):
        """
        Generate a response for a delete-destroy on the InternalAccountViewSet.

        Args:
            user (User): Django auth user performing the request
            account_id (int): the id of the account to retrieve

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.delete(self.path)
        force_authenticate(request, user=user)
        view = InternalAccountViewSet.as_view(actions={"delete": "destroy"})
        response = view(request, pk=account_id)
        return response

    def test_list_accounts(self):
        """Assert that unauthenticated request sees all accounts."""
        expected_accounts = {
            str(self.account1.content_object.aws_account_id),
            str(self.account2.content_object.aws_account_id),
            str(self.account3.content_object.aws_account_id),
            str(self.account4.content_object.aws_account_id),
            str(self.account5.content_object.aws_account_id),
            str(self.azure_account1.content_object.tenant_id),
            str(self.azure_account2.content_object.tenant_id),
        }
        response = self.get_account_list_response(None)
        actual_accounts = self.get_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_get_account(self):
        """Assert that unauthenticated request gets an account."""
        account = self.account2  # just any account
        response = self.get_account_get_response(None, account.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasAccountData(response, account)

    @patch("internal.views.tasks.delete_cloud_account")
    def test_delete_account(self, mock_delete):
        """
        Assert that http deleting an account delays an async task to do it.

        Note that we assert HTTP status code 202 in the response, not 204. Although 204
        is the typical status code for a delete, since the result of this action spawns
        an async task to do the delete but the CloudAccount still exists until then, the
        "202 Accepted" status is more accurate. See also the definition at:
        https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/202
        """
        account = self.account2  # just any account
        response = self.get_account_delete_response(None, account.id)
        self.assertEqual(response.status_code, 202)
        mock_delete.delay.assert_called_with(account.id)
        self.account2.refresh_from_db()
        self.assertIsNotNone(self.account2)

    @patch.object(CloudAccount, "enable")
    def test_create_account_with_name_success(self, mock_enable):
        """Test create account with a name succeeds."""
        data = util_helper.generate_dummy_aws_cloud_account_post_data()

        request = self.factory.post("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"post": "create"})

        response = view(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["content_object"]["account_arn"], data["account_arn"]
        )
        self.assertEqual(response.data["name"], data["name"])
        self.assertIsNotNone(response.data["name"])
        self.assertEqual(response.data["is_enabled"], True)  # True by default
        mock_enable.assert_called()

    @patch.object(CloudAccount, "enable")
    def test_create_azure_account_with_name_success(self, mock_enable):
        """Test creating an azure account succeeds."""
        data = util_helper.generate_dummy_azure_cloud_account_post_data()

        request = self.factory.post("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"post": "create"})

        response = view(request)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.data["content_object"]["tenant_id"], str(data["tenant_id"])
        )
        self.assertEqual(response.data["name"], data["name"])
        self.assertIsNotNone(response.data["name"])
        self.assertEqual(response.data["is_enabled"], True)  # True by default
        mock_enable.assert_called()

    @patch.object(util, "aws")
    @patch("api.clouds.aws.tasks.initial_aws_describe_instances")
    def test_create_account_with_duplicate_name_fail(self, mock_aws, mock_task):
        """Test create account with a duplicate name fails."""
        mock_aws.verify_account_access.return_value = True, []

        data = util_helper.generate_dummy_aws_cloud_account_post_data()
        data["name"] = "unique"  # should collide with self.account5

        request = self.factory.post("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"post": "create"})
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)
        mock_task.delay.assert_not_called()

    def test_create_account_without_name_fail(self):
        """Test create account without a name fails."""
        data = util_helper.generate_dummy_aws_cloud_account_post_data()
        del data["name"]

        request = self.factory.post("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"post": "create"})
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_update_account_patch_name_success(self):
        """Test updating an account with a name succeeds."""
        data = {
            "cloud_type": "aws",
            "name": self.faker.bs()[:256],
        }

        account_id = self.account4.id
        request = self.factory.patch("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"patch": "partial_update"})
        response = view(request, pk=account_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["name"], response.data["name"])

    def test_update_account_patch_duplicate_name_fail(self):
        """Test updating an account with a duplicate name fails."""
        data = {
            "cloud_type": "aws",
            "name": "unique",
        }

        account_id = self.account3.id
        request = self.factory.patch("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"patch": "partial_update"})
        response = view(request, pk=account_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_update_account_patch_arn_fails(self):
        """Test that updating to change the arn fails."""
        data = {
            "cloud_type": "aws",
            "account_arn": util_helper.generate_dummy_arn(),
        }

        account_id = self.account4.id
        request = self.factory.patch("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"patch": "partial_update"})
        response = view(request, pk=account_id)

        self.assertEqual(response.status_code, 400)

    def test_create_with_malformed_arn_fails(self):
        """Test create account with malformed arn returns validation error."""
        data = util_helper.generate_dummy_aws_cloud_account_post_data()
        data["account_arn"] = self.faker.bs()

        request = self.factory.post("/accounts/", data=data)
        force_authenticate(request, user=self.user2)

        view = InternalAccountViewSet.as_view(actions={"post": "create"})
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn("account_arn", response.data)

    def test_update_cloudtype_fails(self):
        """Test updating cloud_type returns validation error."""

        class MockCloudAccountSerializer(serializers.CloudAccountSerializer):
            cloud_type = serializers.ChoiceField(
                choices=["aws", "bad_cloud"], required=True
            )

        with patch(
            "internal.views.InternalAccountViewSet.get_serializer_class"
        ) as mock_viewset_serializer:
            mock_viewset_serializer.return_value = MockCloudAccountSerializer
            data = {
                "cloud_type": "bad_cloud",
                "name": self.faker.bs()[:256],
            }

            account_id = self.account4.id
            request = self.factory.patch("/accounts/", data=data)
            force_authenticate(request, user=self.user2)

            view = InternalAccountViewSet.as_view(actions={"patch": "partial_update"})

            response = view(request, pk=account_id)
            expected_error = "You cannot update field cloud_type."

            self.assertEqual(response.status_code, 400)
            self.assertEqual(expected_error, response.data["cloud_type"][0])
