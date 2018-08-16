"""Collection of tests for UserViewSet."""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.test import TestCase
from rest_framework.test import APIClient

from account.models import AwsAccount, AwsMachineImage
from account.tests import helper as account_helper
from util.tests import helper as util_helper


class UserViewSetTest(TestCase):
    """UserViewSet test case."""

    def setUp(self):
        """Set up test data."""
        self.user = util_helper.generate_test_user()
        self.super_user = util_helper.generate_test_user(is_superuser=True)

        self.account_one = account_helper.generate_aws_account(user=self.user)
        self.account_two = account_helper.generate_aws_account(user=self.user)
        self.su_account = account_helper.generate_aws_account(
            user=self.super_user)

        self.su_ami_rhel7 = account_helper.generate_aws_image(
            self.su_account, is_rhel=True, ec2_ami_id='su_ami-rhel7',
            rhel_challenged=False)

        self.ami_plain = account_helper.generate_aws_image(
            self.account_one, ec2_ami_id='ami-plain')
        self.ami_rhel7 = account_helper.generate_aws_image(
            self.account_one, is_rhel=True, ec2_ami_id='ami-rhel7',
            rhel_challenged=True)
        self.ami_openshift = account_helper.generate_aws_image(
            self.account_two, is_openshift=True, ec2_ami_id='ami-openshift',
            openshift_challenged=True)
        self.ami_both = account_helper.generate_aws_image(
            self.account_two, is_rhel=True, is_openshift=True,
            ec2_ami_id='ami-both')

        self.client = APIClient()
        self.client.force_authenticate(user=self.super_user)

    def assertUserIsCorrect(self, expected_user, user):
        """Assert the user expected_user matches the expected output."""
        self.assertEqual(expected_user.id, user.get('id'))
        self.assertEqual(expected_user.username, user.get('username'))
        self.assertEqual(expected_user.is_superuser, user.get('is_superuser'))
        self.assertEqual(
            AwsAccount.objects.filter(user=expected_user).count(),
            user.get('accounts'))
        self.assertEqual(
            AwsMachineImage.objects.filter(account__user=expected_user).filter(
                Q(rhel_challenged=True) |
                Q(openshift_challenged=True)).count(),
            user.get('challenged_images'))

    def test_list_users_as_non_super(self):
        """Assert that non-super user gets 403 status_code."""
        url = '/api/v1/user/'
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_list_self_as_non_super(self):
        """Assert that non-super user gets 403 status_code."""
        url = f'/api/v1/user/{self.user.id}/'
        self.client.force_authenticate(user=self.user)
        response = self.client.get(url)
        self.assertEqual(403, response.status_code)

    def test_list_users_as_super(self):
        """Assert that super user can list users."""
        User = get_user_model()

        url = '/api/v1/user/'
        response = self.client.get(url)

        self.assertEqual(200, response.status_code)
        users = response.data
        self.assertEqual(User.objects.all().count(), len(users))
        for user in users:
            self.assertUserIsCorrect(
                User.objects.get(pk=user.get('id')), user)

    def test_get_user_method_with_super(self):
        """Assert super user can get a single user."""
        url = f'/api/v1/user/{self.user.id}/'
        response = self.client.get(url)
        user = response.json()
        self.assertUserIsCorrect(self.user, user)

    def test_get_user_method_with_super_bad_id(self):
        """Assert a super user gets a 404 when id not found."""
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

    def test_options_method_with_anon_allowed(self):
        """Assert anonymous call to OPTIONS is allowed."""
        url = '/api/v1/user/'
        # Grab another client object since we don't want to be authenticated
        temp_client = APIClient()
        response = temp_client.options(url)
        self.assertEqual(200, response.status_code)

    def test_options_method_with_user_allowed(self):
        """Assert user call to OPTIONS is allowed."""
        url = '/api/v1/user/'
        self.client.force_authenticate(user=self.user)
        response = self.client.options(url)
        self.assertEqual(200, response.status_code)

    def test_options_method_with_super_allowed(self):
        """Assert super user call to OPTIONS is allowed."""
        url = '/api/v1/user/'
        response = self.client.options(url)
        self.assertEqual(200, response.status_code)
