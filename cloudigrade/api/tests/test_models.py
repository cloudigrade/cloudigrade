"""Collection of tests for the api.models module."""
import datetime
from unittest.mock import patch
from uuid import uuid4

import faker
from django.contrib.auth.models import User
from django.test import TestCase

from api.models import ConcurrentUsage, ConcurrentUsageCalculationTask, Run
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage
from util.misc import get_today
from util.tests import helper as util_helper


_faker = faker.Faker()


class ConcurrentUsageCalculationTaskTest(TestCase):
    """Test cases for api.models.ConcurrentUsageCalculationTask."""

    def test_cancel(self):
        """Test that cancel sets status to CANCELED."""
        user = util_helper.generate_test_user()

        task_id = uuid4()
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=user.id, date=_faker.date(), task_id=task_id
        )
        concurrent_task.save()

        self.assertEqual(
            concurrent_task.status, ConcurrentUsageCalculationTask.SCHEDULED
        )
        with patch("celery.current_app") as mock_celery:
            concurrent_task.cancel()
            mock_celery.control.revoke.assert_called_with(task_id)
        self.assertEqual(
            ConcurrentUsageCalculationTask.objects.get(task_id=task_id).status,
            ConcurrentUsageCalculationTask.CANCELED,
        )


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

    @patch("cloudigrade.api.tasks.notify_application_availability_task")
    def test_delete_clount_deletes_user(self, mock_notify_sources):
        """Test User is deleted if last clount is deleted."""
        user = util_helper.generate_test_user()
        username = user.username
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        account = api_helper.generate_cloud_account(
            aws_account_id=aws_account_id,
            user=user,
        )

        account.delete()
        self.assertFalse(User.objects.filter(username=username).exists())

    @patch("cloudigrade.api.tasks.notify_application_availability_task")
    def test_delete_clount_doesnt_delete_user_for_two_clounts(
        self, mock_notify_sources
    ):
        """Test User is not deleted if it has more clounts left."""
        user = util_helper.generate_test_user()
        username = user.username
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
        self.assertTrue(User.objects.filter(username=username).exists())

    @patch("cloudigrade.api.tasks.notify_application_availability_task")
    @patch("api.clouds.aws.util.verify_permissions")
    @patch("api.clouds.aws.tasks.initial_aws_describe_instances")
    def test_concurrent_usage_deleted_when_clount_enables(
        self,
        mock_initial_aws_describe_instances,
        mock_verify_permissions,
        mock_notify_sources,
    ):
        """Test stale ConcurrentUsage is deleted when clount is enabled."""
        user = util_helper.generate_test_user()

        concurrent_usage = ConcurrentUsage(user=user, date=get_today())
        concurrent_usage.save()

        self.assertEqual(1, ConcurrentUsage.objects.filter(user=user).count())
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        account = api_helper.generate_cloud_account(
            aws_account_id=aws_account_id,
            user=user,
        )
        account.enable()
        self.assertEqual(0, ConcurrentUsage.objects.filter(user=user).count())
