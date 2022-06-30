"""Collection of tests for InternalUserViewSet."""
import faker
from django.test import TestCase

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
