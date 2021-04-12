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

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_calculate_max_concurrent_usage_task(
        self, mock_calculate_max_concurrent_usage
    ):
        """
        Test happy path behavior.

        The calculation function should be called and the task is set to complete.
        """
        calculate_max_concurrent_usage_task.retry = MagicMock(side_effect=Retry)

        task_id = uuid4()
        user_id = self.user.id
        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=user_id, date=request_date, task_id=task_id
        )
        concurrent_task.save()
        calculate_max_concurrent_usage_task.push_request(id=task_id)
        calculate_max_concurrent_usage_task.run(str(request_date), user_id)

        mock_calculate_max_concurrent_usage.assert_called_with(request_date, user_id)
        self.assertEqual(
            ConcurrentUsageCalculationTask.objects.get(task_id=task_id).status,
            ConcurrentUsageCalculationTask.COMPLETE,
        )

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_return_if_user_does_not_exist(self, mock_calculate_max_concurrent_usage):
        """
        Test that the task returns early if user does not exist.

        The calculate function should not be called.
        """
        task_id = uuid4()
        request_date = datetime.date(2019, 5, 1)
        calculate_max_concurrent_usage_task.push_request(id=task_id)
        calculate_max_concurrent_usage_task.run(str(request_date), _faker.pyint())
        mock_calculate_max_concurrent_usage.assert_not_called()

    @patch("api.tasks.calculate_max_concurrent_usage")
    @patch("api.tasks.schedule_concurrent_calculation_task")
    def test_new_task_if_existing_task_is_missing(
        self, mock_schedule_task, mock_calculate_max_concurrent_usage
    ):
        """
        Test that the task schedules a new task with same user and date if missing.

        The calculate function should not be called.
        """
        task_id = uuid4()
        user_id = self.user.id
        request_date = datetime.date(2019, 5, 1)
        calculate_max_concurrent_usage_task.push_request(id=task_id)

        with self.assertLogs("api.tasks", level="WARNING") as logging_watcher:
            calculate_max_concurrent_usage_task.run(str(request_date), user_id)

        mock_schedule_task.assert_called_with(request_date, user_id)
        mock_calculate_max_concurrent_usage.assert_not_called()
        self.assertIn(
            f"ConcurrentUsageCalculationTask not found for task ID {task_id}",
            logging_watcher.output[0],
        )

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_early_return_on_unexpected_status(
        self, mock_calculate_max_concurrent_usage
    ):
        """Test early return if task status is not SCHEDULED."""
        task_id = uuid4()
        user_id = self.user.id
        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=user_id,
            date=request_date,
            task_id=task_id,
            status=ConcurrentUsageCalculationTask.COMPLETE,
        )
        concurrent_task.save()

        calculate_max_concurrent_usage_task.push_request(id=task_id)
        mock_calculate_max_concurrent_usage.assert_not_called()

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_calculate_max_concurrent_usage_exception(
        self, mock_calculate_max_concurrent_usage
    ):
        """
        Test that task is marked as ERROR if calculate_max_concurrent_usage fails.

        The calculate function is called here, but we force it to raise an exception.
        Also verify that we logged the underlying exception.
        """
        error_message = "it is a mystery"
        mock_calculate_max_concurrent_usage.side_effect = Exception(error_message)

        task_id = uuid4()
        user_id = self.user.id
        request_date = datetime.date(2019, 5, 1)
        concurrent_task = ConcurrentUsageCalculationTask(
            user_id=user_id, date=request_date, task_id=task_id
        )
        concurrent_task.save()

        calculate_max_concurrent_usage_task.push_request(id=task_id)

        with self.assertRaises(Exception), self.assertLogs(
            "api.tasks", level="WARNING"
        ) as logging_watcher:
            calculate_max_concurrent_usage_task.run(str(request_date), user_id)

        self.assertIn(error_message, logging_watcher.output[0])
        self.assertEqual(
            ConcurrentUsageCalculationTask.objects.get(task_id=task_id).status,
            ConcurrentUsageCalculationTask.ERROR,
        )
        mock_calculate_max_concurrent_usage.assert_called_with(request_date, user_id)
