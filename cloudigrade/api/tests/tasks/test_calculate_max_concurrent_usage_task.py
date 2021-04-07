"""Collection of tests for tasks.calculate_max_concurrent_usage_task."""
import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import faker
from celery.exceptions import Retry
from django.test import TestCase

from api.models import ConcurrentUsageCalculationTask
from api.tasks import calculate_max_concurrent_usage_task
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class CalculateMaxConcurrentUsageTaskTest(TestCase):
    """Celery task 'calculate_max_concurrent_usage_task' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()

        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.account = api_helper.generate_cloud_account(
            aws_account_id=self.aws_account_id,
            user=self.user,
            created_at=util_helper.utc_dt(2017, 12, 1, 0, 0, 0),
        )
        api_helper.generate_instance_type_definitions()

    def test_calculate_max_concurrent_usage_task(self):
        """Test ConcurrentUsageCalculationTask is set to complete."""
        calculate_max_concurrent_usage_task.retry = MagicMock(side_effect=Retry)

        task_id = uuid4()
        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=self.user.id, date=request_date, task_id=task_id
        )
        concurrent_task.save()

        calculate_max_concurrent_usage_task.push_request(id=task_id)

        calculate_max_concurrent_usage_task.run(str(request_date), self.user.id)
        self.assertEqual(
            ConcurrentUsageCalculationTask.objects.get(task_id=task_id).status,
            ConcurrentUsageCalculationTask.COMPLETE,
        )

    def test_task_retry_if_another_task_is_running(self):
        """Test that task retries if another task is running with same user and date."""
        calculate_max_concurrent_usage_task.retry = MagicMock(side_effect=Retry)

        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=self.user.id, date=request_date, task_id=uuid4()
        )
        concurrent_task.status = ConcurrentUsageCalculationTask.RUNNING
        concurrent_task.save()

        with self.assertRaises(Retry):
            calculate_max_concurrent_usage_task(str(request_date), self.user.id)

    def test_task_cancel_if_newer_task_is_scheduled(self):
        """Test cancel if newer scheduled task is scheduled with same user and date."""
        task_id = uuid4()
        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=self.user.id, date=request_date, task_id=task_id
        )
        concurrent_task.save()

        newer_task = ConcurrentUsageCalculationTask(
            user_id=self.user.id, date=request_date, task_id=uuid4()
        )
        newer_task.created_at = concurrent_task.created_at + datetime.timedelta(days=1)
        newer_task.save()

        concurrent_task.save = MagicMock()

        with patch.object(ConcurrentUsageCalculationTask, "cancel") as mock_cancel:
            calculate_max_concurrent_usage_task.push_request(id=task_id)
            calculate_max_concurrent_usage_task.run(str(request_date), self.user.id)

        mock_cancel.assert_called()

        newer_task.refresh_from_db()
        self.assertEqual(
            concurrent_task.status, ConcurrentUsageCalculationTask.SCHEDULED
        )
        concurrent_task.save.assert_not_called()

    @patch("api.tasks.schedule_concurrent_calculation_task")
    def test_new_task_if_existing_task_is_missing(self, mock_schedule_task):
        """Test that task spawns a new task with same user and date if missing."""
        task_id = uuid4()
        request_date = datetime.date(2019, 5, 1)
        calculate_max_concurrent_usage_task.push_request(id=task_id)

        with self.assertLogs("api.tasks", level="WARNING") as logging_watcher:
            calculate_max_concurrent_usage_task.run(str(request_date), self.user.id)
            mock_schedule_task.assert_called_with(request_date, self.user.id)
        self.assertIn(
            f'ConcurrentUsageCalculationTask not found for task ID "{task_id}"',
            logging_watcher.output[0],
        )

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_invalid_user(self, mock_calculate_max_concurrent_usage):
        """Test that task exits early if user does not exist."""
        task_id = uuid4()
        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=self.user.id, date=request_date, task_id=task_id
        )
        concurrent_task.save()

        calculate_max_concurrent_usage_task.push_request(id=task_id)

        calculate_max_concurrent_usage_task.run(request_date, _faker.pyint())
        mock_calculate_max_concurrent_usage.assert_not_called()

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_calculate_max_concurrent_usage_exception(
        self, mock_calculate_max_concurrent_usage
    ):
        """Test that task is marked as ERROR if calculate_max_concurrent_usage fails."""
        mock_calculate_max_concurrent_usage.side_effect = Exception()

        task_id = uuid4()
        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=self.user.id, date=request_date, task_id=task_id
        )
        concurrent_task.save()

        calculate_max_concurrent_usage_task.push_request(id=task_id)

        with self.assertRaises(Exception):
            calculate_max_concurrent_usage_task.run(str(request_date), self.user.id)

        self.assertEqual(
            ConcurrentUsageCalculationTask.objects.get(task_id=task_id).status,
            ConcurrentUsageCalculationTask.ERROR,
        )
