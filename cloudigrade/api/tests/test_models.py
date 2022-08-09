"""Collection of tests for the api.models module."""
import datetime
import uuid
from unittest.mock import patch

import faker
from django.test import TestCase, TransactionTestCase, override_settings

from api import AWS_PROVIDER_STRING
from api.models import (
    CloudAccount,
    ConcurrentUsage,
    MachineImage,
    Run,
    SyntheticDataRequest,
)
from api.models import User
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage
from util.tests import helper as util_helper

_faker = faker.Faker()


class MachineImageTest(TestCase):
    """Test cases for api.models.MachineImage."""

    def test_save_with_concurrent_usages(self):
        """Test that save deletes the related concurrent_usages."""
        user = util_helper.generate_test_user()
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        account = api_helper.generate_cloud_account(
            aws_account_id=aws_account_id,
            user=user,
        )
        image = api_helper.generate_image(
            owner_aws_account_id=aws_account_id,
            rhel_detected=True,
        )
        instance = api_helper.generate_instance(account, image=image)
        api_helper.generate_single_run(
            instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=instance.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        calculate_max_concurrent_usage(request_date, user_id=user.id)

        self.assertEquals(1, ConcurrentUsage.objects.count())
        image.rhel_detected_by_tag = True
        image.save()
        self.assertEquals(0, ConcurrentUsage.objects.count())


class RunTest(TestCase):
    """Test cases for api.models.Run."""

    def test_new_run_deletes_concurrent_usage(self):
        """
        Test that creating a new run deletes the right ConcurrentUsage.

        When a run is saved that is related to ConcurrentUsage through
        the potentially_related_runs field, ensure those ConcurrentUsages
        are deleted. Creating a new Run should not remove ConcurrentUsages
        with no related runs.

        """
        user = util_helper.generate_test_user()
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        account = api_helper.generate_cloud_account(
            aws_account_id=aws_account_id,
            user=user,
        )
        image = api_helper.generate_image(
            owner_aws_account_id=aws_account_id,
            rhel_detected=True,
        )
        instance = api_helper.generate_instance(account, image=image)
        instance_type = util_helper.get_random_instance_type()

        start_time = util_helper.utc_dt(2019, 5, 1, 1, 0, 0)
        end_time = util_helper.utc_dt(2019, 5, 1, 2, 0, 0)

        request_date = datetime.date(2019, 5, 1)

        # Calculating maximum usage for no runs generates one concurrent usage
        # with empty counts
        calculate_max_concurrent_usage(request_date, user_id=user.id)
        self.assertEqual(1, ConcurrentUsage.objects.all().count())
        self.assertEqual("[]", ConcurrentUsage.objects.all()[0]._maximum_counts)

        # Create a run
        run = Run.objects.create(
            start_time=start_time,
            end_time=end_time,
            instance=instance,
            machineimage=image,
            instance_type=instance_type,
            vcpu=util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]["vcpu"],
            memory=util_helper.SOME_EC2_INSTANCE_TYPES[instance_type]["memory"],
        )
        # Creating a run should not delete the empty concurrent usage
        # since that concurrent usage isn't related to this run
        self.assertEqual(1, ConcurrentUsage.objects.all().count())
        self.assertEqual("[]", ConcurrentUsage.objects.all()[0]._maximum_counts)

        # recalculating the maximum concurrent usage results in a nonempty
        # ConcurrentUsage maximum_counts
        calculate_max_concurrent_usage(request_date, user_id=user.id)
        self.assertNotEqual("[]", ConcurrentUsage.objects.all()[0]._maximum_counts)

        # Re-saving the run should remove the related the concurrent usage.
        run.save()
        self.assertEqual(0, ConcurrentUsage.objects.all().count())


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


class SyntheticDataRequestModelTest(TestCase, api_helper.ModelStrTestMixin):
    """SyntheticDataRequest tests."""

    def setUp(self):
        """Set up basic SyntheticDataRequest."""
        self.request = SyntheticDataRequest.objects.create()

    def test_synthetic_data_request_str(self):
        """Test that the SyntheticDataRequest str and repr are valid."""
        self.assertTypicalStrOutput(
            self.request, exclude_field_names=("machine_images",)
        )

    def test_synthetic_data_request_pre_delete_callback(self):
        """Test the SyntheticDataRequest pre-delete callback deletes images."""
        image = api_helper.generate_image_aws()
        self.request.machine_images.add(image)
        self.request.delete()
        with self.assertRaises(MachineImage.DoesNotExist):
            image.refresh_from_db()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class SyntheticDataRequestModelTransactionTest(TransactionTestCase):
    """SyntheticDataRequest tests that require transaction.on_commit handling."""

    def setUp(self):
        """Set up basic SyntheticDataRequest."""
        self.request = SyntheticDataRequest.objects.create(
            cloud_type=AWS_PROVIDER_STRING
        )

    def test_synthetic_data_request_post_delete_callback(self):
        """Test the SyntheticDataRequest post-delete callback deletes accounts."""
        self.request.refresh_from_db()  # because user is assigned during post_create
        user_id = self.request.user_id
        self.assertTrue(CloudAccount.objects.filter(user_id=user_id).exists())
        self.request.delete()
        self.assertFalse(CloudAccount.objects.filter(user_id=user_id).exists())


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
