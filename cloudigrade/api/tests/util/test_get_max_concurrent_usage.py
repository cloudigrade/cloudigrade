"""Collection of tests for api.util.get_max_concurrent_usage."""
import datetime

from django.test import TestCase

from api.tests import helper as api_helper
from api.util import get_max_concurrent_usage
from util.tests import helper as util_helper


class GetMaxConcurrentUsageTest(TestCase):
    """Test cases for api.util.get_max_concurrent_usage."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user1account1 = api_helper.generate_cloud_account(user=self.user1)
        self.image_rhel = api_helper.generate_image(rhel_detected=True)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    def test_single_rhel_run_result(self):
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
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        concurrent_usage = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertEqual(concurrent_usage.date, expected_date)
        self.assertEqual(len(concurrent_usage.maximum_counts), 24)
        for single_day_counts in concurrent_usage.maximum_counts:
            self.assertEqual(single_day_counts["instances_count"], expected_instances)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    def test_single_rhel_run_no_result(self):
        """
        Test with a single RHEL instance requesting results in the future.

        We expect None because we refuse to calculate data for future dates.
        Note that the decorated clouditardis date here is older than request_date.
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
        )
        request_date = datetime.date(2019, 5, 4)

        concurrent_usage = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertIsNone(concurrent_usage)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 5, 3, 0, 0, 0))
    def test_calculated_concurent_usage_does_not_exist(self):
        """Test that None is returned if requested usage does not exist."""
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

        concurrent_usage = get_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertIsNone(concurrent_usage)
