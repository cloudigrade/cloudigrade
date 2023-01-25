"""Collection of tests for tasks.maintenance.delete_inactive_users."""
from datetime import timedelta

import faker
from django.conf import settings
from django.test import TestCase

from api.models import CloudAccount
from api.models import User
from api.tasks import maintenance
from api.tests import helper as api_helper
from util import misc

_faker = faker.Faker()
USERS_COUNT = 10


class DeleteInactiveUsersTest(TestCase):
    """Celery task 'delete_inactive_users' test cases."""

    def test_delete_inactive_users(self):
        """Test delete_inactive_users deletes inactive Users and related objects."""
        age = settings.DELETE_INACTIVE_USERS_MIN_AGE + 10
        old_date = misc.get_now() - timedelta(seconds=age)
        for account_number in range(1, USERS_COUNT + 1):
            User.objects.create_user(account_number, date_joined=old_date)
        self.assertEqual(User.objects.count(), USERS_COUNT)
        maintenance.delete_inactive_users()
        self.assertEqual(User.objects.count(), 0)

    def test_delete_inactive_users_ignores_users_with_cloudaccount(self):
        """Test delete_inactive_users ignores Users having any CloudAccount."""
        age = settings.DELETE_INACTIVE_USERS_MIN_AGE + 10
        old_date = misc.get_now() - timedelta(seconds=age)
        for account_number in range(1, USERS_COUNT + 1):
            user = User.objects.create_user(account_number, date_joined=old_date)
            api_helper.generate_cloud_account(user=user)
        self.assertEqual(User.objects.count(), USERS_COUNT)
        self.assertEqual(CloudAccount.objects.count(), USERS_COUNT)
        maintenance.delete_inactive_users()
        self.assertEqual(User.objects.count(), USERS_COUNT)

    def test_delete_inactive_users_ignores_superusers(self):
        """Test delete_inactive_users ignores superusers."""
        age = settings.DELETE_INACTIVE_USERS_MIN_AGE + 10
        old_date = misc.get_now() - timedelta(seconds=age)
        for account_number in range(1, USERS_COUNT + 1):
            User.objects.create_user(
                account_number, date_joined=old_date, is_superuser=True
            )
        self.assertEqual(User.objects.count(), USERS_COUNT)
        maintenance.delete_inactive_users()
        self.assertEqual(User.objects.count(), USERS_COUNT)

    def test_delete_inactive_users_ignores_new_users(self):
        """Test delete_inactive_users ignores new users."""
        for account_number in range(1, USERS_COUNT + 1):
            User.objects.create_user(account_number)
        self.assertEqual(User.objects.count(), USERS_COUNT)
        maintenance.delete_inactive_users()
        self.assertEqual(User.objects.count(), USERS_COUNT)
