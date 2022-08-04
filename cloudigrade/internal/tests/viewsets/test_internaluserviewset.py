"""Collection of tests for InternalUserViewSet."""
import faker
from django.test import TestCase

from api.models import User
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class InternalUserViewSetTest(TestCase):
    """InternalDailyConcurrentUsageViewSet test case."""

    def setUp(self):
        """Set up some test data."""
        self.user1 = util_helper.generate_test_user(org_id=str(_faker.uuid4()))
        self.user2 = util_helper.generate_test_user(org_id=str(_faker.uuid4()))
        self.client = api_helper.SandboxedRestClient(
            api_root="/internal/api/cloudigrade/v1"
        )
        self.client._force_authenticate(self.user1)

    def assertJsonDictMatchesUsersList(self, response_dict, users):
        """Assert that the response dict contains data for exactly the given users."""
        data_list = response_dict["data"]
        self.assertEqual(len(users), len(data_list))
        for index, user in enumerate(users):
            data_item = data_list[index]
            self.assertEqual(user.account_number, data_item["account_number"])
            self.assertEqual(user.org_id, data_item["org_id"])
            self.assertEqual(user.uuid, data_item["uuid"])
            self.assertEqual(user.account_number, data_item["username"])

    def test_list_all_users(self):
        """Assert all users are returned for unfiltered request."""
        response = self.client.get_users()
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [self.user1, self.user2])

    def test_list_users_filter_username(self):
        """Assert using the username filter returns only the matching user."""
        filter_args = {"username": str(self.user1.account_number)}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [self.user1])

    def test_list_users_filter_username_not_found(self):
        """Assert username filter with junk data excludes all users."""
        filter_args = {"username": _faker.slug()}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [])

    def test_list_users_filter_account_number(self):
        """Assert using the account_number filter returns only the matching user."""
        filter_args = {"account_number": str(self.user1.account_number)}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [self.user1])

    def test_list_users_filter_account_number_not_found(self):
        """Assert account_number filter with junk data excludes all users."""
        filter_args = {"account_number": _faker.slug()}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [])

    def test_list_users_filter_org_id(self):
        """Assert using the org_id filter returns only the matching user."""
        filter_args = {"org_id": str(self.user1.org_id)}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [self.user1])

    def test_list_users_filter_org_id_not_found(self):
        """Assert org_id filter with junk data excludes all users."""
        filter_args = {"org_id": _faker.slug()}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [])

    def test_list_users_filter_uuid(self):
        """Assert using the uuid filter returns only the matching user."""
        filter_args = {"uuid": str(self.user1.uuid)}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [self.user1])

    def test_list_users_filter_uuid_not_found(self):
        """Assert uuid filter with junk data excludes all users."""
        filter_args = {"uuid": _faker.slug()}
        response = self.client.get_users(data=filter_args)
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertJsonDictMatchesUsersList(response_dict, [])

    def test_create_user(self):
        """Assert a post creates a new user."""
        user_account_number = _faker.uuid4()
        user_org_id = _faker.uuid4()
        post_args = {"account_number": user_account_number, "org_id": user_org_id}
        response = self.client.post_users(data=post_args)
        self.assertEqual(response.status_code, 201)
        response_dict = response.json()
        self.assertTrue(
            User.objects.filter(account_number=user_account_number).exists()
        )
        user = User.objects.get(id=response_dict["id"])
        self.assertEqual(user.account_number, user_account_number)
        self.assertEqual(user.org_id, user_org_id)

    def test_update_user(self):
        """Assert a put updates the user."""
        user_org_id = str(_faker.uuid4())
        test_user = util_helper.generate_test_user(
            org_id=user_org_id, is_permanent=False
        )
        response = self.client.put_users(test_user.id, data={"is_permanent": True})
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertEqual(response_dict["id"], test_user.id)
        self.assertEqual(response_dict["org_id"], user_org_id)
        self.assertTrue(response_dict["is_permanent"])
        test_user.refresh_from_db()
        self.assertTrue(test_user.is_permanent)

    def test_patch_update_user(self):
        """Assert a patch updates the user."""
        user_org_id = str(_faker.uuid4())
        test_user = util_helper.generate_test_user(
            org_id=user_org_id, is_permanent=True
        )
        response = self.client.patch_users(test_user.id, data={"is_permanent": False})
        self.assertEqual(response.status_code, 200)
        response_dict = response.json()
        self.assertEqual(response_dict["id"], test_user.id)
        self.assertEqual(response_dict["org_id"], user_org_id)
        self.assertFalse(response_dict["is_permanent"])
        test_user.refresh_from_db()
        self.assertFalse(test_user.is_permanent)

    def test_delete_user_succeeds_with_non_permanent_users(self):
        """Assert a delete succeeds with non permanent users."""
        user_org_id = str(_faker.uuid4())
        test_user = util_helper.generate_test_user(
            org_id=user_org_id, is_permanent=False
        )
        response = self.client.delete_users(test_user.id)
        self.assertEqual(response.status_code, 202)
        self.assertFalse(User.objects.filter(org_id=user_org_id).exists())

    def test_delete_user_succeeds_with_permanent_users(self):
        """Assert a delete succeeds with permanent users."""
        user_org_id = str(_faker.uuid4())
        test_user = util_helper.generate_test_user(
            org_id=user_org_id, is_permanent=True
        )
        response = self.client.delete_users(test_user.id)
        self.assertEqual(response.status_code, 202)
        self.assertFalse(User.objects.filter(org_id=user_org_id).exists())

    def test_delete_user_fails_if_user_has_accounts(self):
        """Assert a delete fails for users with accounts."""
        test_user = util_helper.generate_test_user(
            org_id=str(_faker.uuid4()), is_permanent=False
        )
        api_helper.generate_cloud_account_aws(user=test_user)
        response = self.client.delete_users(test_user.id)
        response_dict = response.json()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response_dict["error"],
            f"User id {test_user.id} has related CloudAccounts and cannot be deleted",
        )
