"""Collection of tests for ``util.misc`` module."""
from datetime import datetime, timedelta
from unittest.mock import patch

from dateutil import tz
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from api.models import (
    CloudAccount,
    UserTaskLock,
)
from api.tests import helper as api_helper
from util import misc
from util.misc import generate_device_name
from util.misc import lock_task_for_user_ids
from util.tests import helper as util_helper


class UtilMiscTest(TestCase):
    """Misc utility functions test case."""

    def test_generate_device_name_success(self):
        """Assert that names are being properly generated."""
        self.assertEqual(generate_device_name(0), "/dev/xvdba")
        self.assertEqual(generate_device_name(1, "/dev/sd"), "/dev/sdbb")

    def test_truncate_date_return_original(self):
        """Assert we allow values from the past."""
        yesterday = datetime.now(tz=tz.tzutc()) - timedelta(days=1)
        output = misc.truncate_date(yesterday)
        self.assertEqual(output, yesterday)

    def test_truncate_date_return_now(self):
        """Assert we truncate future dates to "now"."""
        now = datetime.now(tz=tz.tzutc())
        tomorrow = now + timedelta(days=1)
        with patch.object(misc, "datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = now
            output = misc.truncate_date(tomorrow)
        self.assertEqual(output, now)


class LockUserTaskTest(TransactionTestCase):
    """Test Cases for the UserTaskLock context manager."""

    def test_lock_task_for_user_ids_create_usertasklock(self):
        """Assert UserTaskLock is created by context manager."""
        user1 = util_helper.generate_test_user()
        user2 = util_helper.generate_test_user()

        with lock_task_for_user_ids([user1.id, user2.id]):
            locks = UserTaskLock.objects.all()
            for lock in locks:
                self.assertEqual(lock.locked, True)
        locks = UserTaskLock.objects.all()
        for lock in locks:
            self.assertEqual(lock.locked, False)

    def test_lock_task_for_user_ids_updates_usertasklock(self):
        """Assert UserTaskLock is updated by context manager."""
        user = util_helper.generate_test_user()
        UserTaskLock.objects.create(user=user)
        with lock_task_for_user_ids([user.id]) as locks:
            for lock in locks:
                self.assertEqual(lock.locked, True)
        lock = UserTaskLock.objects.get(user=user)
        self.assertEqual(lock.locked, False)

    @patch("api.clouds.aws.util.delete_cloudtrail")
    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_clount_lock(self, mock_notify_sources, mock_delete_cloudtrail):
        """Test that deleting an clount inside a lock is successful."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        account = api_helper.generate_cloud_account(
            arn=arn,
            aws_account_id=aws_account_id,
        )

        with lock_task_for_user_ids([account.user.id]):
            CloudAccount.objects.filter(id=account.id).delete()

        self.assertEqual(CloudAccount.objects.all().count(), 0)
        self.assertFalse(UserTaskLock.objects.filter(user=account.user).exists())

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_clount_lock_exception(self, mock_notify_sources):
        """Test that an exception when deleting a clount inside a lock rolls back."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        account = api_helper.generate_cloud_account(
            arn=arn,
            aws_account_id=aws_account_id,
        )
        UserTaskLock.objects.create(user=account.user)
        with self.assertRaises(transaction.TransactionManagementError):
            with lock_task_for_user_ids([account.user.id]):
                CloudAccount.objects.filter(id=account.id).delete()
                raise transaction.TransactionManagementError

        self.assertEqual(CloudAccount.objects.all().count(), 1)
        self.assertFalse(UserTaskLock.objects.get(user=account.user).locked)
