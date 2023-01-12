"""Collection of tests for ``util.misc`` module."""
import copy
from datetime import datetime, timedelta
from unittest.mock import patch

import faker
from dateutil import tz
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from api.models import (
    CloudAccount,
    UserTaskLock,
)
from api.tests import helper as api_helper
from util import misc
from util.misc import (
    lock_task_for_user_ids,
    redact_json_dict_secrets,
    redact_secret,
)
from util.tests import helper as util_helper

_faker = faker.Faker()


class RedactSecretsTest(TestCase):
    """Test cases for redact_secret and redact_json_dict_secrets."""

    def test_redact_secret_string(self):
        """Test redacting a secret string value."""
        original = f"{_faker.slug()}-{_faker.slug()}-{_faker.slug()}"
        redacted = redact_secret(original)
        self.assertNotEqual(original, redacted)
        self.assertEqual(original[-2:], redacted[-2:])

    def test_redact_secret_none(self):
        """Test redacting None simply returns None."""
        original = None
        redacted = redact_secret(original)
        self.assertIsNone(redacted)

    def test_redact_secret_not_string_not_none(self):
        """Test redacting a falsy not-string not-None value."""
        original = False
        redacted = redact_secret(original)
        self.assertNotEqual(original, redacted)
        self.assertIsNotNone(redacted)
        self.assertEqual("se", redacted[-2:])

    def test_redact_json_dict_secrets_dict(self):
        """
        Test redacting secrets from a slightly complex JSON-friendly dict.

        We are not using Faker here because it's much simpler to explicitly compare
        against the expected output without dynamically rebuilding the expectations
        around new random values. The example here is a simplified version of a loaded
        cdappconfig.json file from Clowder.
        """
        original = {
            "BOPURL": "http://example",
            "database": {
                "adminPassword": "super secret password!",
                "adminUsername": "postgres",
            },
            "kafka": {
                "brokers": [
                    {
                        "hostname": "kafka-1.svc",
                        "cacert": "HELLOWORLD\n-----END CERTIFICATE-----",
                    },
                    {
                        "hostname": "kafka-2.svc",
                        "cacert": "HOLAMUNDO\nEND CERTIFICATE",
                    },
                ],
            },
        }
        expected = {
            "BOPURL": "http://example",
            "database": {
                "adminPassword": "******************d!",
                "adminUsername": "postgres",
            },
            "kafka": {
                "brokers": [
                    {
                        "hostname": "kafka-1.svc",
                        "cacert": "******************--",
                    },
                    {
                        "hostname": "kafka-2.svc",
                        "cacert": "******************TE",
                    },
                ],
            },
        }
        redacted = copy.deepcopy(original)
        redact_json_dict_secrets(redacted)
        self.assertNotEqual(original, redacted)
        self.assertEqual(expected, redacted)


class UtilMiscTest(TestCase):
    """Misc utility functions test case."""

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
    def test_delete_cloud_account_lock(
        self, mock_notify_sources, mock_delete_cloudtrail
    ):
        """Test that deleting an account inside a lock is successful."""
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
    def test_delete_cloud_account_lock_exception(self, mock_notify_sources):
        """Test that an exception when deleting an account inside a lock rolls back."""
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
