"""Collection of tests for UserViewSet."""
from django.test import TestCase
from rest_framework.test import APIClient

from util.tests import helper as util_helper


class UserViewSetTest(TestCase):
    """UserViewSet test case."""

    def setUp(self):
        """Set up test data."""
        self.super_user = util_helper.generate_test_user(is_superuser=True)
        self.client = APIClient()
        self.client.force_authenticate(user=self.super_user)

    def test_list_users_as_non_super(self):
        """Assert that non-super user gets 403 status_code."""
        url = '/api/v1/user/'
        user = util_helper.generate_test_user()
        self.client.force_authenticate(user=user)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_list_users_as_super(self):
        """Assert that super user can list users."""
        other_super = util_helper.generate_test_user(is_superuser=True)
        other = util_helper.generate_test_user()

        expected_results = {
            self.super_user.id: self.super_user,
            other_super.id: other_super,
            other.id: other
        }

        url = '/api/v1/user/'
        response = self.client.get(url)

        self.assertEqual(200, response.status_code)
        users = response.data
        self.assertEqual(3, len(users))
        for user in users:
            expected_user = expected_results.get(user.get('id'))
            self.assertEqual(expected_user.id,
                             user.get('id'))
            self.assertEqual(expected_user.username,
                             user.get('username'))
            self.assertEqual(expected_user.is_superuser,
                             user.get('is_superuser'))

    def test_get_user_method_with_super(self):
        """Assert super user can get a single user."""
        url = '/api/v1/user/1/'
        response = self.client.get(url)
        user = response.json()
        expected_user = self.super_user
        self.assertEqual(str(expected_user.id),
                         user.get('id'))
        self.assertEqual(expected_user.username,
                         user.get('username'))
        self.assertEqual(expected_user.is_superuser,
                         user.get('is_superuser'))

    def test_get_user_method_with_super_bad_id(self):
        """Assert super user can gets a 404 when id not found."""
        url = '/api/v1/user/1234567890/'
        response = self.client.get(url)
        self.assertEqual(404, response.status_code)

    def test_get_user_method_with_nonsuper(self):
        """Assert regular user cannot get a single user."""
        url = '/api/v1/user/1/'
        user = util_helper.generate_test_user()
        self.client.force_authenticate(user=user)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_put_user_method_not_allowed(self):
        """Assert API to update a single user disabled."""
        url = '/api/v1/user/1/'
        response = self.client.put(url)
        self.assertEqual(405, response.status_code)

    def test_patch_user_method_not_allowed(self):
        """Assert API to patch a single user disabled."""
        url = '/api/v1/user/1/'
        response = self.client.patch(url)
        self.assertEqual(405, response.status_code)

    def test_delete_user_method_not_allowed(self):
        """Assert API to delete a single user disabled."""
        url = '/api/v1/user/1/'
        response = self.client.delete(url)
        self.assertEqual(405, response.status_code)

    def test_post_user_method_not_allowed(self):
        """Assert API to create a user disabled."""
        url = '/api/v1/user/'
        response = self.client.post(url)
        self.assertEqual(405, response.status_code)
