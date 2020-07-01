"""Collection of tests for api.util.get_max_concurrent_usage."""
import datetime

from django.test import TestCase

from api import models
from api.tests import helper as api_helper
from api.util import get_max_concurrent_usage
from util.tests import helper as util_helper


class GetMaxConcurrentUsageTest(TestCase):
    """Test cases for api.util.get_max_concurrent_usage."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user1account1 = api_helper.generate_aws_account(user=self.user1)
        self.image_rhel = api_helper.generate_aws_image(rhel_detected=True)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    def test_single_rhel_run_result(self):
        """Test with a single RHEL instance run within the day."""
        rhel_instance = api_helper.generate_aws_instance(
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
        concurrent_usage = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertEqual(
            models.ConcurrentUsage.objects.filter(
                date=request_date, user_id=self.user1.id
            ).count(),
            1,
        )
        self.assertEqual(concurrent_usage.date, expected_date)
        self.assertEqual(len(concurrent_usage.maximum_counts), 4)
        for single_day_counts in concurrent_usage.maximum_counts:
            self.assertEqual(single_day_counts["instances_count"], expected_instances)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    def test_single_rhel_run_no_result(self):
        """
        Test with a single RHEL instance requesting results in futures.

        Also assert that no ConcurrentUsage is saved to the database because the
        requested date is in the future, and we cannot know that data yet.
        """
        rhel_instance = api_helper.generate_aws_instance(
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
        rhel_instance = api_helper.generate_aws_instance(
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
        self.assertEqual(len(concurrent_usage.maximum_counts), 4)
        for single_day_counts in concurrent_usage.maximum_counts:
            self.assertEqual(single_day_counts["instances_count"], expected_instances)
