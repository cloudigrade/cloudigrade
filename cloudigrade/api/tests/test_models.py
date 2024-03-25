"""Collection of tests for the api.models module."""

import uuid
from unittest.mock import patch

import faker
from django.test import TestCase

from api.models import User
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class CloudAccountTest(TestCase):
    """Test cases for api.models.CloudAccount."""

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_cloud_account_deletes_user(self, mock_notify_sources):
        """Test User is deleted if last cloud account is deleted."""
        user = util_helper.generate_test_user()
        account_number = user.account_number
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        account = api_helper.generate_cloud_account(
            aws_account_id=aws_account_id,
            user=user,
        )

        account.delete()
        self.assertFalse(User.objects.filter(account_number=account_number).exists())

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_cloud_account_doesnt_delete_user_for_two_cloud_accounts(
        self, mock_notify_sources
    ):
        """Test User is not deleted if it has more cloud accounts left."""
        user = util_helper.generate_test_user()
        account_number = user.account_number
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        account = api_helper.generate_cloud_account(
            aws_account_id=aws_account_id,
            user=user,
        )
        aws_account_id2 = util_helper.generate_dummy_aws_account_id()
        api_helper.generate_cloud_account(
            aws_account_id=aws_account_id2,
            user=user,
        )
        account.delete()
        self.assertTrue(User.objects.filter(account_number=account_number).exists())


class UserModelTest(TestCase):
    """UserModel tests not covered indirectly via other tests."""

    def test_user_object_string_representation(self):
        """Test that the string includes the uuid, account_number and org_id."""
        user_uuid = str(uuid.uuid4())
        user_account_number = str(_faker.random_int(min=100000, max=999999))
        user_org_id = str(_faker.random_int(min=100000, max=999999))

        user = User.objects.create(
            uuid=user_uuid, account_number=user_account_number, org_id=user_org_id
        )

        self.assertEqual(
            str(user),
            f"User(id={user.id},"
            f" uuid={user_uuid},"
            f" account_number={user_account_number},"
            f" org_id={user_org_id},"
            f" is_permanent={user.is_permanent},"
            f" date_joined={user.date_joined})",
        )

    def test_create_user_raises_value_error_with_no_account_number_or_org_id(self):
        """Test that we get a ValueError if account_number and org_id are missing."""
        with self.assertRaises(ValueError) as ve:
            User.objects.create_user()

        self.assertEquals(
            "Users must have at least an account_number or org_id", str(ve.exception)
        )

    def test_delete_user_does_not_delete_permanent_users(self):
        """Test that a delete user does not delete permanent users."""
        user_uuid = str(uuid.uuid4())
        user_account_number = str(_faker.random_int(min=100000, max=999999))
        user_org_id = str(_faker.random_int(min=100000, max=999999))

        user = User.objects.create(
            uuid=user_uuid,
            account_number=user_account_number,
            org_id=user_org_id,
            is_permanent=True,
        )

        deleted, __ = user.delete()
        self.assertEqual(deleted, 0)
        self.assertTrue(
            User.objects.filter(account_number=user_account_number).exists()
        )

    def test_delete_user_delete_non_permanent_users(self):
        """Test that a delete user does delete non permanent users."""
        user_uuid = str(uuid.uuid4())
        user_account_number = str(_faker.random_int(min=100000, max=999999))
        user_org_id = str(_faker.random_int(min=100000, max=999999))

        user = User.objects.create(
            uuid=user_uuid,
            account_number=user_account_number,
            org_id=user_org_id,
            is_permanent=False,
        )

        deleted, __ = user.delete()
        self.assertEqual(deleted, 1)
        self.assertFalse(
            User.objects.filter(account_number=user_account_number).exists()
        )

    def test_delete_user_with_force_does_delete_permanent_users(self):
        """Test that a force delete user does delete permanent users."""
        user_uuid = str(uuid.uuid4())
        user_account_number = str(_faker.random_int(min=100000, max=999999))
        user_org_id = str(_faker.random_int(min=100000, max=999999))

        user = User.objects.create(
            uuid=user_uuid,
            account_number=user_account_number,
            org_id=user_org_id,
            is_permanent=True,
        )

        deleted, __ = user.delete(force=True)
        self.assertEqual(deleted, 1)
        self.assertFalse(
            User.objects.filter(account_number=user_account_number).exists()
        )
