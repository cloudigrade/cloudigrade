"""Collection of tests for the api.models module."""
from unittest.mock import patch
from uuid import uuid4

import faker
from django.test import TestCase

from api.models import ConcurrentUsageCalculationTask
from util.tests import helper as util_helper


_faker = faker.Faker()


class ConcurrentUsageCalculationTaskTest(TestCase):
    """Test cases for api.models.ConcurrentUsageCalculationTask."""

    def test_cancel(self):
        """Test that cancel sets status to CANCELED."""
        self.user = util_helper.generate_test_user()

        task_id = uuid4()
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=self.user.id, date=_faker.date(), task_id=task_id
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
