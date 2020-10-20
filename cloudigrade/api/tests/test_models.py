"""Collection of tests for the api.models module."""
import datetime
from unittest.mock import patch
from uuid import uuid4

import faker
from django.test import TestCase

from api.models import ConcurrentUsage, ConcurrentUsageCalculationTask
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage
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
        image.delete()
        self.assertEquals(0, ConcurrentUsage.objects.count())
