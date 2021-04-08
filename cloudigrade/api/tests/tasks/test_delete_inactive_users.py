"""Collection of tests for tasks.delete_inactive_users."""
from datetime import timedelta
from unittest.mock import patch

import faker
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from api import tasks
from api.models import CloudAccount, ConcurrentUsage, ConcurrentUsageCalculationTask
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
            user = User.objects.create_user(account_number, date_joined=old_date)
            ConcurrentUsage.objects.create(
                date=old_date, user_id=user.id, maximum_counts=[]
            )
            ConcurrentUsageCalculationTask.objects.create(
                user_id=user.id, date=old_date, task_id=f"{_faker.uuid4()}"
            )
        self.assertEqual(User.objects.count(), USERS_COUNT)
        self.assertEqual(ConcurrentUsage.objects.count(), USERS_COUNT)
        self.assertEqual(ConcurrentUsageCalculationTask.objects.count(), USERS_COUNT)
        with patch.object(ConcurrentUsageCalculationTask, "_revoke") as mock_revoke:
            tasks.delete_inactive_users()
        mock_revoke.assert_called()
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(ConcurrentUsage.objects.count(), 0)
        self.assertEqual(ConcurrentUsageCalculationTask.objects.count(), 0)

    def test_delete_inactive_users_ignores_users_with_cloudaccount(self):
        """Test delete_inactive_users ignores Users having any CloudAccount."""
        age = settings.DELETE_INACTIVE_USERS_MIN_AGE + 10
        old_date = misc.get_now() - timedelta(seconds=age)
        for account_number in range(1, USERS_COUNT + 1):
            user = User.objects.create_user(account_number, date_joined=old_date)
            api_helper.generate_cloud_account(user=user)
        self.assertEqual(User.objects.count(), USERS_COUNT)
        self.assertEqual(CloudAccount.objects.count(), USERS_COUNT)
        tasks.delete_inactive_users()
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
        tasks.delete_inactive_users()
        self.assertEqual(User.objects.count(), USERS_COUNT)

    def test_delete_inactive_users_ignores_new_users(self):
        """Test delete_inactive_users ignores new users."""
        for account_number in range(1, USERS_COUNT + 1):
            User.objects.create_user(account_number)
        self.assertEqual(User.objects.count(), USERS_COUNT)
        tasks.delete_inactive_users()
        self.assertEqual(User.objects.count(), USERS_COUNT)
