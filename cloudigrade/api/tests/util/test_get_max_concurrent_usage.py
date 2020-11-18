"""Collection of tests for api.util.get_max_concurrent_usage."""
import datetime
from unittest.mock import patch

from django.test import TestCase

from api import models
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage, get_max_concurrent_usage
from util.exceptions import ResultsUnavailable
from util.tests import helper as util_helper


class GetMaxConcurrentUsageTest(TestCase):
    """Test cases for api.util.get_max_concurrent_usage."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user1account1 = api_helper.generate_cloud_account(user=self.user1)
        self.image_rhel = api_helper.generate_image(rhel_detected=True)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    @patch("api.util.schedule_concurrent_calculation_task")
    def test_single_rhel_run_result(self, mock_schedule_concurrent_calc):
        """Test with a single RHEL instance run within the day."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            calculate_concurrent_usage=False,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        self.assertEqual(
            models.ConcurrentUsage.objects.filter(
                date=request_date, user_id=self.user1.id
            ).count(),
            0,
        )

        with self.assertRaises(ResultsUnavailable):
            get_max_concurrent_usage(request_date, user_id=self.user1.id)

        calculate_max_concurrent_usage(request_date, self.user1.id)
        concurrent_usage = models.ConcurrentUsage.objects.get(
            date=request_date, user_id=self.user1.id
        )

        self.assertEqual(
            models.ConcurrentUsage.objects.filter(
                date=request_date, user_id=self.user1.id
            ).count(),
            1,
        )
        self.assertEqual(concurrent_usage.date, expected_date)
        self.assertEqual(len(concurrent_usage.maximum_counts), 24)
        for single_day_counts in concurrent_usage.maximum_counts:
            self.assertEqual(single_day_counts["instances_count"], expected_instances)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    def test_single_rhel_run_no_result(self):
        """
        Test with a single RHEL instance requesting results in futures.

        Also assert that no ConcurrentUsage is saved to the database because the
        requested date is in the future, and we cannot know that data yet.
        """
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            calculate_concurrent_usage=False,
        )
        request_date = datetime.date(2019, 5, 4)
        expected_date = request_date

        self.assertEqual(
            models.ConcurrentUsage.objects.filter(
                date=request_date, user_id=self.user1.id
            ).count(),
            0,
        )
        concurrent_usage = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertEqual(
            models.ConcurrentUsage.objects.filter(
                date=request_date, user_id=self.user1.id
            ).count(),
            0,
        )
        self.assertEqual(concurrent_usage.date, expected_date)
        self.assertEqual(len(concurrent_usage.maximum_counts), 0)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    def test_multiple_requests_use_precalculated_data(self):
        """Test multiple requests use the same saved pre-calculated data."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        concurrent_usage = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        concurrent_usage_2 = get_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
        concurrent_usage_3 = get_max_concurrent_usage(
            request_date, user_id=self.user1.id
        )
        self.assertEqual(concurrent_usage, concurrent_usage_2)
        self.assertEqual(concurrent_usage, concurrent_usage_3)
        self.assertEqual(concurrent_usage.date, expected_date)
        self.assertEqual(len(concurrent_usage.maximum_counts), 24)
        for single_day_counts in concurrent_usage.maximum_counts:
            self.assertEqual(single_day_counts["instances_count"], expected_instances)

    @patch("api.util.schedule_concurrent_calculation_task")
    def test_calculation_in_progress(self, mock_schedule_concurrent_task):
        """Test exception is raised if calculation is currently running."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
            calculate_concurrent_usage=False,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        self.assertEqual(
            models.ConcurrentUsage.objects.filter(
                date=request_date, user_id=self.user1.id
            ).count(),
            0,
        )

        concurrent_task = models.ConcurrentUsageCalculationTask(
            date=request_date, user_id=self.user1.id, task_id="test123"
        )
        concurrent_task.status = models.ConcurrentUsageCalculationTask.RUNNING
        concurrent_task.save()

        with self.assertRaises(ResultsUnavailable):
            get_max_concurrent_usage(request_date, user_id=self.user1.id)

        # now actually calculate concurrent usage
        calculate_max_concurrent_usage(request_date, self.user1.id)
        concurrent_usage = get_max_concurrent_usage(request_date, user_id=self.user1.id)

        self.assertEqual(
            models.ConcurrentUsage.objects.filter(
                date=request_date, user_id=self.user1.id
            ).count(),
            1,
        )
        self.assertEqual(concurrent_usage.date, expected_date)
        self.assertEqual(len(concurrent_usage.maximum_counts), 24)
        for single_day_counts in concurrent_usage.maximum_counts:
            self.assertEqual(single_day_counts["instances_count"], expected_instances)
