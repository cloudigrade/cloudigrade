"""Collection of tests for api.util.calculate_max_concurrent_usage."""
import datetime

from django.test import TestCase

from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage
from util.tests import helper as util_helper


class CalculateMaxConcurrentUsageTest(TestCase):
    """Test cases for api.util.calculate_max_concurrent_usage."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)

        self.user1account1 = api_helper.generate_cloud_account(user=self.user1)
        self.user1account2 = api_helper.generate_cloud_account(user=self.user1)
        self.user2account1 = api_helper.generate_cloud_account(user=self.user2)

        self.syspurpose1 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "Standard",
            "usage": "Development/Test",
        }
        self.syspurpose2 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "Premium",
            "usage": "Development/Test",
        }
        self.syspurpose3 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "",
            "usage": "Development/Test",
        }
        self.syspurpose4 = {
            "role": "Red Hat Enterprise Linux Server Workstation",
            "service_level_agreement": "," * 10485760,  # 10 mb of commas
            "usage": "Development/Test",
        }
        self.syspurpose5 = {
            "role": "The quick brown fox jumps over the lazy dog. " * 3,
            "service_level_agreement": "Self-Support",
            "usage": "Development/Test",
        }

        self.image_rhel1 = api_helper.generate_image(
            owner_aws_account_id=self.user1account1.id,
            rhel_detected=True,
            syspurpose=self.syspurpose1,
            architecture="x86_64",
        )
        self.image_rhel2 = api_helper.generate_image(
            owner_aws_account_id=self.user1account1.id,
            rhel_detected=True,
            syspurpose=self.syspurpose1,
            architecture="arm64",
        )
        self.image_rhel3 = api_helper.generate_image(
            owner_aws_account_id=self.user1account1.id,
            rhel_detected=True,
            syspurpose=self.syspurpose2,
            architecture="x86_64",
        )
        self.image_rhel4 = api_helper.generate_image(
            owner_aws_account_id=self.user1account1.id,
            rhel_detected=True,
            syspurpose=self.syspurpose3,
            architecture="x86_64",
        )
        self.image_rhel5 = api_helper.generate_image(
            owner_aws_account_id=self.user1account1.id,
            rhel_detected=True,
            syspurpose=self.syspurpose4,
            architecture="x86_64",
        )
        self.image_plain = api_helper.generate_image(
            owner_aws_account_id=self.user1account1.id,
            rhel_detected=False,
            syspurpose=self.syspurpose5,
            architecture="PowerPC",
        )

    def assertMaxConcurrentUsage(self, results, date, instances):
        """
        Assert expected calculate_max_concurrent_usage results.

        Note: this only naively assumes there is *all* in maximum_counts have the same
        number of instances.
        """
        self.assertEqual(results.date, date)
        for single_count in results.maximum_counts:
            self.assertEqual(single_count["instances_count"], instances)

    def test_single_rhel_run_within_day(self):
        """Test with a single RHEL instance run within the day."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel1
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

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertEqual(len(usage.maximum_counts), 24)
        self.assertMaxConcurrentUsage(usage, expected_date, expected_instances)

    def test_single_rhel_run_entirely_before_day(self):
        """Test with a RHEL instance run entirely before the day."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel1
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 4, 30, 1, 0, 0),
                util_helper.utc_dt(2019, 4, 30, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, 0)

    def test_single_rhel_run_entirely_after_day(self):
        """Test with a RHEL instance run entirely after the day."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel1
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 2, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, 0)

    def test_single_no_image_run_within_day(self):
        """Test with a single no-image instance run within the day."""
        mystery_instance = api_helper.generate_instance(
            self.user1account1, image=None, no_image=True
        )
        api_helper.generate_single_run(
            mystery_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=None,
            no_image=True,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 0

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertEqual(len(usage.maximum_counts), 0)
        self.assertMaxConcurrentUsage(usage, expected_date, expected_instances)

    def test_single_run_overlapping_day_start(self):
        """Test with a RHEL instance run overlapping the start of the day."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel1
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 4, 30, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, expected_instances)

    def test_single_run_overlapping_day_end(self):
        """Test with a RHEL instance run overlapping the end of the day."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel1
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, expected_instances)

    def test_single_run_overlapping_day_entirely(self):
        """Test with a RHEL instance run overlapping the entire day."""
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel1
        )
        api_helper.generate_single_run(
            rhel_instance,
            (
                util_helper.utc_dt(2019, 4, 30, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=rhel_instance.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, expected_instances)

    def test_single_not_rhel_run_within_day(self):
        """
        Test with a not-RHEL instance run within the day.

        This instance should have zero effect on max calculations.
        """
        rhel_instance = api_helper.generate_instance(
            self.user1account1, image=self.image_plain
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

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, 0)

    def test_overlapping_rhel_runs_within_day(self):
        """
        Test with two overlapping RHEL instances run within the day.

        Because no account filter is applied, both instances are seen.
        """
        rhel_instance1 = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel1
        )
        rhel_instance2 = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel2
        )
        api_helper.generate_single_run(
            rhel_instance1,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance1.machine_image,
        )
        api_helper.generate_single_run(
            rhel_instance2,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 30, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 30, 0),
            ),
            image=rhel_instance2.machine_image,
        )
        expected_date = request_date = datetime.date(2019, 5, 1)

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertEqual(usage.date, expected_date)
        self.assertEqual(len(usage.maximum_counts), 32)

    def test_overlapping_rhel_runs_within_day_with_user_filter(self):
        """
        Test with two overlapping RHEL instances run within the day.

        Because a user filter is applied, only one instance's data is seen.
        """
        rhel_instance1 = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel3
        )
        rhel_instance2 = api_helper.generate_instance(
            self.user2account1, image=self.image_rhel4
        )
        api_helper.generate_single_run(
            rhel_instance1,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance1.machine_image,
        )
        # This second instance run should be filtered away.
        api_helper.generate_single_run(
            rhel_instance2,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 30, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 30, 0),
            ),
            image=rhel_instance2.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, expected_instances)

    def test_non_overlapping_rhel_runs_within_day(self):
        """
        Test with two non-overlapping RHEL instances run within the day.

        Two instances of different size run at different times, and this test
        should see the *larger* of the two matching the max values.
        """
        rhel_instance1 = api_helper.generate_instance(
            self.user1account1, image=self.image_rhel4
        )
        rhel_instance2 = api_helper.generate_instance(
            self.user1account2, image=self.image_rhel5
        )
        api_helper.generate_single_run(
            rhel_instance1,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=rhel_instance1.machine_image,
        )
        api_helper.generate_single_run(
            rhel_instance2,
            (
                util_helper.utc_dt(2019, 5, 1, 3, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 4, 0, 0),
            ),
            image=rhel_instance2.machine_image,
        )
        request_date = datetime.date(2019, 5, 1)
        expected_date = request_date
        expected_instances = 1

        usage = calculate_max_concurrent_usage(request_date, user_id=self.user1.id)
        self.assertMaxConcurrentUsage(usage, expected_date, expected_instances)

    def test_when_user_id_does_not_exist(self):
        """Test when the requested user ID does not exist."""
        request_date = datetime.date(2019, 5, 1)
        user_id = -1  # negative id should never exit
        expected_date = request_date

        usage = calculate_max_concurrent_usage(request_date, user_id=user_id)
        self.assertMaxConcurrentUsage(usage, expected_date, 0)
